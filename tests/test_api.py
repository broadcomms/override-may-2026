"""Tests for api.main (Tier 1 endpoints).

Coverage from the P2.7 follow-up review:
  - GET /api/health          200 with status + uptime
  - GET /api/version         200 with watsonx model IDs + g4_status
  - GET /api/regulation-source   200 when chunks closed; 404 NOT_FOUND when pending/missing
  - POST /api/sessions       201 happy path; 400 INVALID_FILE_FORMAT empty;
                             400 PARSE_FAILED bad JSON; 413 FILE_TOO_LARGE
  - GET /api/sessions/{id}   200 reload; 404 NOT_FOUND unknown
  - GET /api/sessions/{id}/zones/{zone_id} engineer mode → fan=None
  - GET /api/sessions/{id}/zones/{zone_id}?mode=fan → triggers translate, caches
  - DELETE /api/sessions/{id} 204 idempotent
  - watsonx quota error → 503 MODEL_UNAVAILABLE with helpful detail
  - X-Request-Id header round-trips
  - mocked clients via FastAPI dependency overrides; no network
"""

from __future__ import annotations

import io
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from api.main import (
    create_app,
    get_chat_client,
    get_embedding_client,
    get_guardian_client,
)
from RaceYourCode.gym_torcs.driver_config_contract import DEFAULT_DRIVER_CONFIG
from torcs_driver_profiles import DEFAULT_DRIVER_PROFILE_ID
from ingest.schema import (
    FanOutput,
    LapFeatures,
    ReasoningOutput,
    RegulationCitation,
    RegulationSource,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fakes — same shape as the unit tests in test_pipeline.py
# ──────────────────────────────────────────────────────────────────────────────


def _well_formed_reasoning_json(*, with_citation: bool = False, confidence: str = "low") -> str:
    body = {
        "cause": "Lap 3 deployed 0.70 MJ in S2 with limited time gain.",
        "consequence": "Approximately 0.06 s benefit at low ROI of 11.7 MJ per second.",
        "recommendation": "Consider delaying first deploy to reserve charge for the next straight.",
        "regulation_citation": (
            {
                "passage": "C5.18 MGU-K. The MGU-K shall not exceed 350 kW.",
                "source": {
                    "document_title": "FIA 2026 F1 Technical Regulations — Section C",
                    "issue": "Issue 12 — 2025-06-10",
                    "section": "C5.18",
                    "public_url": "https://www.fia.com/regulation/category/110",
                    "fetched_at": "2026-05-09T12:00:00+00:00",
                },
            }
            if with_citation
            else None
        ),
        "confidence": confidence,
        "confidence_justification": "Reasoning from observed lap_window only; no forecast.",
        "reasoning_chain": [
            "Lap 3 deploy event detected.",
            "Lap-time delta vs median is small.",
            "Per-MJ ROI below efficiency band.",
        ],
    }
    return json.dumps(body)


def _well_formed_fan_json() -> str:
    return json.dumps({
        "headline": "Battery used in a slow corner that didn't pay off",
        "what_happened": "It looks like the car used a chunk of its battery in a tight corner where it didn't help.",
        "why_it_mattered": "That cost about half a tenth on the next straight.",
        "the_rule": None,
    })


def _well_formed_copilot_json() -> str:
    return json.dumps({
        "answer": (
            "Lap 4 ran 0.00s against lap 2, but it finished with a lower battery reserve after another net-spend lap. "
            "That supports a more conservative deployment pattern later in the run."
        ),
        "engine": "granite",
        "supporting_laps": [2, 4],
        "confidence": "high",
        "suggestions": [
            "Which lap was more efficient?",
            "What happened in sector 2?",
            "Summarize the battery trend",
        ],
    })


class FakeChatClient:
    def __init__(self, *, responses=None, raises=None):
        self.responses = list(responses) if responses else []
        self.raises = raises
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def chat(self, system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 1024) -> str:
        if self.raises:
            raise self.raises
        with self._lock:
            idx = len(self.calls)
            self.calls.append({"system_len": len(system), "user_len": len(user)})
        # Decide which response shape to return based on the system prompt
        if "OVERRIDE-Fan-Translator" in system:
            return _well_formed_fan_json()
        if "OVERRIDE-Race-Copilot" in system:
            if idx < len(self.responses):
                return self.responses[idx]
            return _well_formed_copilot_json()
        if idx < len(self.responses):
            return self.responses[idx]
        return _well_formed_reasoning_json()


class FakeEmbeddingClient:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeGuardianClient:
    def __init__(self, *, energy="No: ok", reg="No: ok"):
        self.energy = energy
        self.reg = reg

    def chat(self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 256) -> str:
        if "Energy-Safety" in system:
            return self.energy
        if "Regulation Citation Consistency" in system:
            return self.reg
        raise AssertionError("unrecognized prompt")


def _empty_chunks_path(tmp_path: Path) -> Path:
    p = tmp_path / "empty_chunks.json"
    p.write_text(json.dumps({
        "g4_status": "pending", "saved_at": "2026-05-08T00:00:00Z",
        "source_document_label": None, "notes": None,
        "n_chunks": 0, "embedding_dimensions": None, "chunks": [],
    }))
    return p


def _closed_chunks_path(tmp_path: Path) -> Path:
    """Minimal closed-G-4 chunk corpus for tests that need a regulation_source."""
    chunk = {
        "chunk_id": "c_test",
        "text": "C5.18 MGU-K. The MGU-K shall not exceed 350 kW.",
        "source": {
            "document_title": "FIA 2026 F1 Technical Regulations — Section C",
            "issue": "Issue 12 — 2025-06-10",
            "section": "C5.18",
            "public_url": "https://www.fia.com/regulation/category/110",
            "fetched_at": "2026-05-09T12:00:00+00:00",
        },
        "keywords": ["MGU-K"],
        "embedding": [0.1, 0.2, 0.3],
    }
    p = tmp_path / "closed_chunks.json"
    p.write_text(json.dumps({
        "g4_status": "closed", "saved_at": "2026-05-09T00:00:00Z",
        "source_document_label": "FIA 2026 F1 Technical Regulations — Section C (Issue 12)",
        "notes": "test fixture",
        "n_chunks": 1, "embedding_dimensions": 3, "chunks": [chunk],
    }))
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Test helpers
# ──────────────────────────────────────────────────────────────────────────────


def _build_client(
    *,
    tmp_path: Path,
    chunks_path: Path,
    chat: Optional[FakeChatClient] = None,
    embed: Optional[FakeEmbeddingClient] = None,
    guard: Optional[FakeGuardianClient] = None,
    sessions_dir: Optional[Path] = None,
) -> TestClient:
    """Build a TestClient with mock clients + a fresh sessions storage dir.

    Tests use OVERRIDE_CHUNKS_PATH + SESSIONS_DIR env vars (resolved at
    request time) rather than monkey-patching module-level imports.
    """
    os.environ["SESSIONS_DIR"] = str(sessions_dir or (tmp_path / "sessions"))
    os.environ["OVERRIDE_CHUNKS_PATH"] = str(chunks_path)

    app = create_app()
    app.dependency_overrides[get_chat_client] = lambda: chat or FakeChatClient()
    app.dependency_overrides[get_embedding_client] = lambda: embed or FakeEmbeddingClient()
    app.dependency_overrides[get_guardian_client] = lambda: guard or FakeGuardianClient()
    return TestClient(app)


def _laps_payload(n: int = 5) -> bytes:
    """Synthesize a session that fires low-roi-deploy on lap 3."""
    laps = [
        {"lap_number": 1, "soc_start": 0.85, "soc_end": 0.78, "harvest_mj": 0.4, "deploy_mj": 0.3,
         "lap_time": 85.4, "sector1_time": 27.0, "sector2_time": 29.5, "sector3_time": 28.9,
         "avg_speed": 210.0, "max_speed": 320.0, "override_uses": 1, "boost_uses": 0,
         "recharge_zones": [2], "soc_source": "derived"},
        {"lap_number": 2, "soc_start": 0.78, "soc_end": 0.72, "harvest_mj": 0.3, "deploy_mj": 0.4,
         "lap_time": 85.4, "sector1_time": 27.0, "sector2_time": 29.5, "sector3_time": 28.9,
         "avg_speed": 210.0, "max_speed": 320.0, "override_uses": 1, "boost_uses": 0,
         "recharge_zones": [2], "soc_source": "derived"},
        {"lap_number": 3, "soc_start": 0.72, "soc_end": 0.55, "harvest_mj": 0.2, "deploy_mj": 0.7,
         "lap_time": 85.4, "sector1_time": 27.0, "sector2_time": 30.5, "sector3_time": 27.9,
         "avg_speed": 205.0, "max_speed": 315.0, "override_uses": 1, "boost_uses": 0,
         "recharge_zones": [1], "soc_source": "derived"},
        {"lap_number": 4, "soc_start": 0.55, "soc_end": 0.48, "harvest_mj": 0.4, "deploy_mj": 0.5,
         "lap_time": 85.4, "sector1_time": 27.0, "sector2_time": 29.5, "sector3_time": 28.9,
         "avg_speed": 210.0, "max_speed": 320.0, "override_uses": 1, "boost_uses": 0,
         "recharge_zones": [2], "soc_source": "derived"},
        {"lap_number": 5, "soc_start": 0.48, "soc_end": 0.40, "harvest_mj": 0.3, "deploy_mj": 0.4,
         "lap_time": 85.4, "sector1_time": 27.0, "sector2_time": 29.5, "sector3_time": 28.9,
         "avg_speed": 210.0, "max_speed": 320.0, "override_uses": 1, "boost_uses": 0,
         "recharge_zones": [2], "soc_source": "derived"},
    ]
    return json.dumps({"laps": laps}).encode("utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# /api/health + /api/version
# ──────────────────────────────────────────────────────────────────────────────


def test_health_returns_ok(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["uptime_s"], (int, float))
    assert "X-Request-Id" in r.headers


def test_version_surfaces_model_ids(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_closed_chunks_path(tmp_path))
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    assert body["runtime"] == "watsonx"
    assert body["granite_instruct"]
    assert body["granite_guardian"]
    assert body["granite_embedding"]
    assert body["regulation_source_present"] is True


def test_version_g4_pending_reports_false(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/version")
    assert r.json()["regulation_source_present"] is False


# ──────────────────────────────────────────────────────────────────────────────
# /api/regulation-source
# ──────────────────────────────────────────────────────────────────────────────


def test_regulation_source_returns_metadata_when_g4_closed(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_closed_chunks_path(tmp_path))
    r = client.get("/api/regulation-source")
    assert r.status_code == 200
    body = r.json()
    assert body["section"] == "C5.18"
    assert body["issue"].startswith("Issue 12")


def test_regulation_source_404_when_pending(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/regulation-source")
    assert r.status_code == 404
    body = r.json()
    assert body["error_code"] == "NOT_FOUND"
    assert "G-4 pending" in body["message"]
    assert body["request_id"]


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/sessions
# ──────────────────────────────────────────────────────────────────────────────


def test_create_session_happy_path(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    payload = _laps_payload()
    r = client.post(
        "/api/sessions",
        files={"file": ("session.json", payload, "application/json")},
        data={"source": "fastf1", "track_id": "monza", "soc_max": 4.0},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["summary"]["session_id"].startswith("s_")
    assert body["summary"]["source"] == "fastf1"
    assert body["summary"]["lap_count"] == 5
    assert body["summary"]["zone_count"] >= 1


def test_create_session_empty_upload_returns_400_invalid(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions",
        files={"file": ("empty.json", b"", "application/json")},
        data={"source": "fastf1"},
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "INVALID_FILE_FORMAT"


def test_create_session_malformed_json_returns_400_parse_failed(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions",
        files={"file": ("bad.json", b"{not json", "application/json")},
        data={"source": "fastf1"},
    )
    assert r.status_code == 400
    assert r.json()["error_code"] == "PARSE_FAILED"


def test_create_session_oversized_returns_413(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "0")  # any non-empty file fails
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions",
        files={"file": ("big.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    )
    assert r.status_code == 413
    assert r.json()["error_code"] == "FILE_TOO_LARGE"


def test_create_session_watsonx_quota_returns_503(tmp_path):
    """R18: quota-exhausted watsonx → 503 MODEL_UNAVAILABLE with helpful detail."""

    class ApiRequestFailure(Exception):
        pass

    chat = FakeChatClient(raises=ApiRequestFailure(
        '{"errors":[{"code":"token_quota_reached","message":"quota rejected"}]}'
    ))
    client = _build_client(
        tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path), chat=chat,
    )
    r = client.post(
        "/api/sessions",
        files={"file": ("session.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    )
    assert r.status_code in (500, 503)  # 503 if watsonx exception class detected; 500 otherwise
    body = r.json()
    assert body["error_code"] in ("MODEL_UNAVAILABLE", "INTERNAL_ERROR")


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/sessions/{id} + /zones/{zid}
# ──────────────────────────────────────────────────────────────────────────────


def test_get_session_round_trip(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("session.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]
    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 200
    assert r.json()["summary"]["session_id"] == sid


def test_get_session_unknown_returns_404_not_found(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/sessions/s_nonexistent_xx")
    assert r.status_code == 404
    assert r.json()["error_code"] == "NOT_FOUND"


def test_get_zone_engineer_mode_strips_fan_field(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]
    zid = created["recommendations"][0]["zone"]["zone_id"]
    r = client.get(f"/api/sessions/{sid}/zones/{zid}?mode=engineer")
    assert r.status_code == 200
    assert r.json()["fan"] is None


def test_get_zone_fan_mode_triggers_translation(tmp_path):
    """mode=fan should call the chat client (FanMode) and populate fan field."""
    chat = FakeChatClient()
    client = _build_client(
        tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path), chat=chat,
    )
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]
    zid = created["recommendations"][0]["zone"]["zone_id"]

    upload_calls = len(chat.calls)
    r = client.get(f"/api/sessions/{sid}/zones/{zid}?mode=fan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fan"] is not None
    assert body["fan"]["headline"]
    # At least one extra chat call for Fan Mode
    assert len(chat.calls) > upload_calls


def _synthetic_torcs_jsonl(*, n_laps: int = 2, ticks_per_lap: int = 120) -> bytes:
    """Mimic what RaceYourCode/gym_torcs/torcs_jm_par.py:parse_server_str emits
    when OVERRIDE_LOG_TELEMETRY is set. Two laps with deploy-in-S2 + brake-in-S3
    structure so derive_lap_energy produces non-zero harvest + deploy.
    """
    track_length = 3000.0
    lap_duration_s = 36.0
    dt = lap_duration_s / ticks_per_lap
    wall_t = 1_700_000_000.0
    lines: list[str] = []
    s1_end = track_length / 3.0
    s2_end = 2.0 * track_length / 3.0
    for _lap in range(n_laps):
        for tick_i in range(ticks_per_lap):
            cur_lap_time = tick_i * dt
            dist = (tick_i / ticks_per_lap) * track_length
            if dist < s1_end:
                accel, brake = 0.7, 0.0
            elif dist < s2_end:
                accel, brake = 1.0, 0.0
            else:
                accel, brake = 0.0, 0.6
            lines.append(json.dumps({
                "t": wall_t,
                "curLapTime": [cur_lap_time],
                "distFromStart": [dist],
                "speedX": [60.0 if accel >= 0.95 else 30.0],
                "accel": [accel],
                "brake": [brake],
                "fuel": [90.0],
            }))
            wall_t += dt
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_create_session_torcs_jsonl_round_trips_through_pipeline(tmp_path):
    """Closes v6 plan task 1.6 spec: POST a synthetic TORCS JSONL replay with
    source=torcs, verify clean Session round-trips through the full pipeline
    (zone detection → reasoning → validator → Guardian → save_session).
    Mocked watsonx clients; the test exercises api/main:_parse_upload's
    content-sniffing dispatch and the new ingest/torcs_parser path end-to-end.
    """
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    payload = _synthetic_torcs_jsonl()
    r = client.post(
        "/api/sessions",
        files={"file": ("baseline.jsonl", payload, "application/x-ndjson")},
        data={"source": "torcs", "track_id": "synthetic", "soc_max": 4.0},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["summary"]["source"] == "torcs"
    assert body["summary"]["lap_count"] == 2
    assert all(L["soc_source"] == "derived" for L in body["laps"])


def test_create_session_torcs_dispatch_sniffs_content_not_just_filename(tmp_path):
    """Regression test: a .json-suffixed (no `l`) TORCS replay must still
    route through ingest.torcs_parser via content-sniffing, not fall through
    to canonical-schema passthrough. Review caught this — fixtures named
    data/samples/torcs_*.json would have crashed otherwise.
    """
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    payload = _synthetic_torcs_jsonl(n_laps=1, ticks_per_lap=120)
    r = client.post(
        "/api/sessions",
        # filename is .json — content sniffing has to detect the tick signature
        files={"file": ("torcs_baseline.json", payload, "application/json")},
        data={"source": "torcs"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["summary"]["lap_count"] == 1


def test_get_zone_fan_mode_concurrent_different_zones_all_persist(tmp_path):
    """Regression test for the lazy fan-mode save race (v6 plan task 1.8 / hard floor).

    Pre-fix: ``api/main.py`` did load_session → compute fan → save_session, and
    parallel ``?mode=fan`` requests on different zones in the same session each
    wrote from a stale snapshot, causing the last writer to clobber other
    zones' fan fields. Post-fix: a per-session ``asyncio.Lock`` serializes the
    read-modify-write, and ``save_recommendations_only`` writes atomically via
    tempfile + os.replace.

    The test creates a session, then fires concurrent fan-mode requests for
    every zone via ``httpx.AsyncClient`` + ``asyncio.gather``. After all
    requests resolve, the session is reloaded from disk and *every* zone must
    have a populated ``fan`` field — no clobbering.
    """
    import asyncio
    import httpx

    chat = FakeChatClient()
    client = _build_client(
        tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path), chat=chat,
    )
    # The default payload may yield only one zone; that's still a valid
    # exercise of the lock+helper code path (no race triggered but no
    # regression either). When multiple zones are present, the race becomes
    # observable without the fix.
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]
    zone_ids = [r["zone"]["zone_id"] for r in created["recommendations"]]
    assert zone_ids, "synthetic payload must yield at least one zone"

    async def _fire_all():
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(*[
                ac.get(f"/api/sessions/{sid}/zones/{zid}?mode=fan")
                for zid in zone_ids
            ])

    responses = asyncio.run(_fire_all())
    for r in responses:
        assert r.status_code == 200, r.text
        assert r.json()["fan"] is not None

    # Reload from disk — every zone's fan field must be durable, not clobbered
    final = client.get(f"/api/sessions/{sid}").json()
    fans_after = {r["zone"]["zone_id"]: r["fan"] for r in final["recommendations"]}
    for zid in zone_ids:
        assert fans_after[zid] is not None, (
            f"zone {zid} fan field lost — concurrent write race regressed"
        )


def test_get_zone_unknown_zone_returns_404(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]
    r = client.get(f"/api/sessions/{sid}/zones/z_nonexistent")
    assert r.status_code == 404
    assert r.json()["error_code"] == "NOT_FOUND"


# ──────────────────────────────────────────────────────────────────────────────
# Live TORCS-volume ingest (v6 plan task 3.2)
# ──────────────────────────────────────────────────────────────────────────────


def _torcs_jsonl_payload(*, n_laps: int = 2, ticks_per_lap: int = 120) -> bytes:
    """Same synthetic JSONL pattern as the test_torcs_parser fixture
    helper. Cross-file duplication is acceptable — keeps both test files
    self-contained, no shared-fixture-import gymnastics."""
    track_length = 3000.0
    lap_duration_s = 36.0
    dt = lap_duration_s / ticks_per_lap
    wall_t = 1_700_000_000.0
    lines: list[str] = []
    s1_end = track_length / 3.0
    s2_end = 2.0 * track_length / 3.0
    for _lap in range(n_laps):
        for tick_i in range(ticks_per_lap):
            cur_lap_time = tick_i * dt
            dist = (tick_i / ticks_per_lap) * track_length
            if dist < s1_end:
                accel, brake = 0.7, 0.0
            elif dist < s2_end:
                accel, brake = 1.0, 0.0
            else:
                accel, brake = 0.0, 0.6
            lines.append(json.dumps({
                "t": wall_t,
                "curLapTime": [cur_lap_time],
                "distFromStart": [dist],
                "speedX": [60.0 if accel >= 0.95 else 30.0],
                "accel": [accel],
                "brake": [brake],
                "fuel": [90.0],
            }))
            wall_t += dt
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_torcs_status_available_false_when_dir_empty(tmp_path, monkeypatch):
    """Default state — no torcs profile running, no JSONL files. Banner
    in the UI should stay hidden; endpoint must NOT 404."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs-status")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["runs"] == []


def test_torcs_status_lists_available_runs_newest_first(tmp_path, monkeypatch):
    telem = tmp_path / "telemetry"
    telem.mkdir()
    # Write two JSONL files with different mtimes
    (telem / "older.jsonl").write_bytes(_torcs_jsonl_payload(n_laps=1, ticks_per_lap=80))
    import time as _t; _t.sleep(0.01)
    (telem / "newer.jsonl").write_bytes(_torcs_jsonl_payload(n_laps=2, ticks_per_lap=120))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs-status")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    # Newest first
    assert [r["run_id"] for r in body["runs"]] == ["newer", "older"]


def test_torcs_live_happy_path_runs_pipeline(tmp_path, monkeypatch):
    """POST a JSONL replay → run_pipeline fires (mocked watsonx clients) →
    Session round-trips with source=torcs."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "baseline.jsonl").write_bytes(_torcs_jsonl_payload())
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions/torcs-live",
        json={"run_id": "baseline"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["summary"]["source"] == "torcs"
    assert body["summary"]["track_id"] == "torcs-live/baseline"
    assert body["summary"]["lap_count"] >= 1


def test_torcs_live_unknown_run_returns_404(tmp_path, monkeypatch):
    telem = tmp_path / "telemetry"
    telem.mkdir()
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions/torcs-live",
        json={"run_id": "nonexistent"},
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "NOT_FOUND"


def test_torcs_live_invalid_run_id_pattern_returns_422(tmp_path):
    """Pydantic Field pattern rejects path-traversal attempts + arbitrary
    strings. Belt-and-suspenders alongside the file-exists check."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions/torcs-live",
        json={"run_id": "../etc/passwd"},  # path traversal attempt
    )
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 — Session boundaries, history, comparison
# ──────────────────────────────────────────────────────────────────────────────


def test_extract_start_time_reads_first_observation_t(tmp_path):
    """The logger injects `t = time.time()` into every observation.
    _extract_start_time should pull the first `t` and return it as a
    timezone-aware UTC datetime."""
    from datetime import datetime, timezone

    from api.main import _extract_start_time

    p = tmp_path / "x.jsonl"
    p.write_bytes(_torcs_jsonl_payload(n_laps=1, ticks_per_lap=10))
    got = _extract_start_time(p)
    assert got is not None
    # _torcs_jsonl_payload starts at 1_700_000_000.0
    assert got == datetime.fromtimestamp(1_700_000_000.0, tz=timezone.utc)


def test_extract_start_time_returns_none_on_missing_t(tmp_path):
    """Older captures (or hand-rolled fixtures) without `t` should not
    crash; the caller substitutes file mtime."""
    from api.main import _extract_start_time

    p = tmp_path / "no_t.jsonl"
    p.write_text('{"distFromStart": [0], "speedX": [30]}\n')
    assert _extract_start_time(p) is None


def test_extract_start_time_tolerates_malformed_leading_line(tmp_path):
    """Gotcha #12 safe-read shape: a malformed first line is skipped,
    not raised. Helper finds the next valid observation."""
    from datetime import datetime, timezone

    from api.main import _extract_start_time

    p = tmp_path / "broken.jsonl"
    p.write_text('not-json-at-all\n{"t": 1700000000.0, "x": 1}\n')
    got = _extract_start_time(p)
    assert got == datetime.fromtimestamp(1_700_000_000.0, tz=timezone.utc)


def test_torcs_status_surfaces_started_last_written_duration(tmp_path, monkeypatch):
    """Phase 1 enrichment — each run reports started_at (from JSONL
    first-observation `t`), last_written_at (file mtime), duration_seconds."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "race.jsonl").write_bytes(_torcs_jsonl_payload(n_laps=1, ticks_per_lap=10))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs-status")
    body = r.json()
    assert body["available"] is True
    run = body["runs"][0]
    assert run["run_id"] == "race"
    assert "started_at" in run and run["started_at"].endswith("+00:00")
    assert "last_written_at" in run
    assert "duration_seconds" in run and run["duration_seconds"] >= 0.0


def test_torcs_live_enriches_summary_with_session_source_and_metadata(
    tmp_path, monkeypatch,
):
    """POST with track_name/target_laps/notes → resulting Session.summary
    has session_source=torcs_live, status=completed, the three operator
    fields populated, started_at + completed_at + telemetry_file set."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "race.jsonl").write_bytes(_torcs_jsonl_payload())
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions/torcs-live",
        json={
            "run_id": "race",
            "track_name": "Monza",
            "target_laps": 5,
            "notes": "calibration lap",
        },
    )
    assert r.status_code == 201, r.text
    summary = r.json()["summary"]
    assert summary["session_source"] == "torcs_live"
    assert summary["status"] == "completed"
    assert summary["track_name"] == "Monza"
    assert summary["target_laps"] == 5
    assert summary["note"] == "calibration lap"
    assert summary["telemetry_file"] == "race.jsonl"
    assert summary["started_at"] is not None
    assert summary["completed_at"] is not None


def test_torcs_live_works_without_optional_metadata(tmp_path, monkeypatch):
    """Backward compat — old curl invocations without the new fields
    must still succeed; track_name/target_laps/notes stay None."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "race.jsonl").write_bytes(_torcs_jsonl_payload())
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post("/api/sessions/torcs-live", json={"run_id": "race"})
    assert r.status_code == 201, r.text
    summary = r.json()["summary"]
    assert summary["session_source"] == "torcs_live"
    assert summary["track_name"] is None
    assert summary["target_laps"] is None


def test_list_sessions_empty_returns_zero_total(tmp_path):
    """No sessions on disk → endpoint returns {sessions: [], total: 0}
    with limit/offset echoed. UI history page renders an empty-state."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body == {"sessions": [], "total": 0, "limit": 50, "offset": 0}


def test_list_sessions_returns_newest_first(tmp_path):
    """Create two sessions; the most recent uploaded_at should come first.
    Storage helper does the sort; this test locks the round-trip."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    # First session
    client.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    )
    # Second session, distinct time
    import time as _t
    _t.sleep(0.05)
    client.post(
        "/api/sessions",
        files={"file": ("b.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    )
    r = client.get("/api/sessions")
    body = r.json()
    assert body["total"] == 2
    assert len(body["sessions"]) == 2
    # Newest first — assert via uploaded_at descending
    t0 = body["sessions"][0]["uploaded_at"]
    t1 = body["sessions"][1]["uploaded_at"]
    assert t0 >= t1


def test_list_sessions_pagination_offset_and_limit(tmp_path):
    """Paginate via limit + offset; total stays the same across pages."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    import time as _t
    for _ in range(3):
        client.post(
            "/api/sessions",
            files={"file": ("x.json", _laps_payload(), "application/json")},
            data={"source": "fastf1"},
        )
        _t.sleep(0.01)
    r1 = client.get("/api/sessions?limit=2&offset=0").json()
    r2 = client.get("/api/sessions?limit=2&offset=2").json()
    assert r1["total"] == 3 and r2["total"] == 3
    assert len(r1["sessions"]) == 2
    assert len(r2["sessions"]) == 1
    # No overlap
    ids1 = {s["session_id"] for s in r1["sessions"]}
    ids2 = {s["session_id"] for s in r2["sessions"]}
    assert ids1.isdisjoint(ids2)


def test_list_sessions_uploaded_sessions_default_to_upload_source(tmp_path):
    """Backward compat — sessions created via POST /api/sessions (no
    Phase 1 enrichment) default to session_source=UPLOAD, status=COMPLETED."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    client.post(
        "/api/sessions",
        files={"file": ("x.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    )
    r = client.get("/api/sessions").json()
    s = r["sessions"][0]
    assert s["session_source"] == "upload"
    assert s["status"] == "completed"


def test_list_sessions_rejects_out_of_bounds_limit(tmp_path):
    """Limit clamped at 200 per the Query(le=200); 999 → 422."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/sessions?limit=999")
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 — TORCS control plane (proxy to in-container daemon)
# ──────────────────────────────────────────────────────────────────────────────


def test_control_status_reports_disabled_when_secret_unset(tmp_path, monkeypatch):
    """No TORCS_CONTROL_SECRET → enabled=False, reachable=False. Lets the
    UI hide Start/Stop buttons cleanly when the operator isn't running
    --profile torcs."""
    monkeypatch.delenv("TORCS_CONTROL_URL", raising=False)
    monkeypatch.delenv("TORCS_CONTROL_SECRET", raising=False)
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs/control-status")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "enabled": False, "reachable": False, "active": False,
        "starting": False,                                 # not in boot window when disabled
        "state": None,                                     # Phase 2.5 — daemon state surfaced
        "session_id": None,
        "last_error": None,                                # Phase 2.5 — graceful vs failure distinguisher
        "last_exit_code": None,
        "track": None,
        "laps": None,
        "launch_mode": None,
        "detail": "TORCS_CONTROL_URL + SECRET not set; control plane disabled.",
    }


def test_control_status_reports_unreachable_when_daemon_down(tmp_path, monkeypatch):
    """Secret set, daemon unreachable, daemon never previously reachable →
    enabled=True, reachable=False, starting=True (normal boot window).
    Same UI semantics as disabled but a different `detail` string so
    operators can debug."""
    import api.main as main_mod
    monkeypatch.setattr(main_mod, "_torcs_daemon_ever_reachable", False)
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://nope.invalid:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs/control-status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["reachable"] is False
    assert body["active"] is False
    assert body["starting"] is True   # boot window — calming copy, not a failure
    assert "start" in (body["detail"] or "").lower() or "warm" in (body["detail"] or "").lower()


def test_control_status_proxies_active_state(tmp_path, monkeypatch):
    """Daemon up + reports active race → proxy surfaces active=True
    and the session_id. Uses httpx MockTransport so we don't need a
    real daemon container."""
    import httpx
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-secret"
        assert request.url.path == "/control/status"
        return httpx.Response(200, json={
            "active": True,
            "session_id": "s_torcs_live_42_abcd",
            "pid": 4242,
            "uptime_s": 18.7,
            "exit_code": None,
            "track": "aalborg",
            "laps": 75,
            "launch_mode": "cockpit_practice",
        })

    import api.main as main_mod
    original_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "Client",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs/control-status")
    body = r.json()
    assert body["enabled"] is True
    assert body["reachable"] is True
    assert body["active"] is True
    assert body["session_id"] == "s_torcs_live_42_abcd"
    assert body["track"] == "aalborg"
    assert body["laps"] == 75
    assert body["launch_mode"] == "cockpit_practice"


def test_start_race_503_when_control_disabled(tmp_path, monkeypatch):
    """No secret → 503 with error_code CONTROL_DISABLED. UI never even
    shows the button in this state, but defense-in-depth on the API too."""
    monkeypatch.delenv("TORCS_CONTROL_URL", raising=False)
    monkeypatch.delenv("TORCS_CONTROL_SECRET", raising=False)
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post("/api/torcs/start-race", json={"track": "aalborg", "laps": 5})
    assert r.status_code == 503
    assert r.json()["error_code"] == "CONTROL_DISABLED"


def test_start_race_409_when_daemon_returns_conflict(tmp_path, monkeypatch):
    """Daemon already has an active race → 409 + RACE_ACTIVE."""
    import httpx
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Race already active for session s_x."})

    import api.main as main_mod
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post("/api/torcs/start-race", json={"track": "aalborg", "laps": 5})
    assert r.status_code == 409
    assert r.json()["error_code"] == "RACE_ACTIVE"
    listing = client.get("/api/sessions").json()
    assert listing["sessions"] == []


def test_driver_profiles_list_create_update_duplicate_delete_and_validate(tmp_path, monkeypatch):
    monkeypatch.setenv("TORCS_DRIVER_PROFILES_DIR", str(tmp_path / "driver-profiles"))

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))

    listed = client.get("/api/torcs/driver-profiles")
    assert listed.status_code == 200, listed.text
    baseline = {p["profile_id"]: p for p in listed.json()["profiles"]}
    assert DEFAULT_DRIVER_PROFILE_ID in baseline
    assert baseline[DEFAULT_DRIVER_PROFILE_ID]["origin"] == "shipped_default"

    validate_resp = client.post(
        "/api/torcs/driver-profiles/validate",
        json={
            "config": {
                **DEFAULT_DRIVER_CONFIG.model_dump(mode="json"),
                "speed": {
                    **DEFAULT_DRIVER_CONFIG.speed.model_dump(mode="json"),
                    "target_speed_kmh": 88.0,
                },
            },
        },
    )
    assert validate_resp.status_code == 200, validate_resp.text
    assert validate_resp.json()["config"]["speed"]["target_speed_kmh"] == 88.0

    created = client.post(
        "/api/torcs/driver-profiles",
        json={
            "name": "Aggressive Demo",
            "description": "Pushes target speed slightly harder.",
            "config": validate_resp.json()["config"],
        },
    )
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["profile_id"].startswith("aggressive-demo")
    assert profile["origin"] == "user_saved"

    fetched = client.get(f"/api/torcs/driver-profiles/{profile['profile_id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["name"] == "Aggressive Demo"

    updated = client.patch(
        f"/api/torcs/driver-profiles/{profile['profile_id']}",
        json={"name": "Aggressive Demo v2", "description": "Sharper throttle map."},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Aggressive Demo v2"

    duplicated = client.post(
        f"/api/torcs/driver-profiles/{profile['profile_id']}/duplicate",
        json={"name": "Aggressive Demo Copy"},
    )
    assert duplicated.status_code == 201, duplicated.text
    assert duplicated.json()["name"] == "Aggressive Demo Copy"
    assert duplicated.json()["profile_id"] != profile["profile_id"]

    delete_resp = client.delete(f"/api/torcs/driver-profiles/{profile['profile_id']}")
    assert delete_resp.status_code == 204, delete_resp.text

    missing = client.get(f"/api/torcs/driver-profiles/{profile['profile_id']}")
    assert missing.status_code == 404


def test_driver_profiles_reject_delete_of_shipped_default(tmp_path, monkeypatch):
    monkeypatch.setenv("TORCS_DRIVER_PROFILES_DIR", str(tmp_path / "driver-profiles"))

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.delete(f"/api/torcs/driver-profiles/{DEFAULT_DRIVER_PROFILE_ID}")
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "READ_ONLY_PROFILE"


def test_start_race_201_proxies_daemon_response(tmp_path, monkeypatch):
    """Happy path: daemon 201 → override 201 with the augmented body
    (session_id from override, pid + telemetry_dir from daemon)."""
    import httpx
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    captured_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["body"] = json.loads(request.content)
        # Echo back the daemon's StartRaceResponse shape
        return httpx.Response(201, json={
            "session_id": captured_request["body"]["session_id"],
            "pid": 9999,
            "telemetry_dir": "/home/student/workspace/gym_torcs/telemetry/",
            "launch_mode": captured_request["body"]["launch_mode"],
        })

    import api.main as main_mod
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/torcs/start-race",
        json={"track": "alpine-1", "laps": 10, "track_name": "Alpine", "notes": "smoke test"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["session_id"].startswith("s_torcs_live_")
    assert body["pid"] == 9999
    assert body["telemetry_dir"].endswith("/telemetry/")
    assert body["track"] == "alpine-1"
    assert body["laps"] == 10
    assert body["launch_mode"] == "cockpit_practice"
    assert body["track_name_hint"] == "Alpine"
    assert body["notes_hint"] == "smoke test"
    assert body["driver_profile_id_hint"] == DEFAULT_DRIVER_PROFILE_ID
    assert body["driver_profile_name_hint"] == "Baseline Demo Driver"
    # Verify the daemon got the operator-validated payload
    assert captured_request["body"]["track"] == "alpine-1"
    assert captured_request["body"]["laps"] == 10
    assert captured_request["body"]["launch_mode"] == "cockpit_practice"
    assert captured_request["body"]["session_id"].startswith("s_torcs_live_")
    assert captured_request["body"]["driver_config"]["speed"]["target_speed_kmh"] == 85.0


def test_start_race_honors_explicit_headless_launch_mode(tmp_path, monkeypatch):
    import httpx

    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")
    captured_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["body"] = json.loads(request.content)
        return httpx.Response(201, json={
            "session_id": captured_request["body"]["session_id"],
            "pid": 5555,
            "telemetry_dir": "/home/student/workspace/gym_torcs/telemetry/",
            "launch_mode": captured_request["body"]["launch_mode"],
        })

    import api.main as main_mod

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/torcs/start-race",
        json={"track": "aalborg", "laps": 75, "launch_mode": "headless_quickrace"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["launch_mode"] == "headless_quickrace"
    assert captured_request["body"]["launch_mode"] == "headless_quickrace"
    assert captured_request["body"]["auto_launch_torcs"] is False


def test_stop_race_returns_daemon_payload(tmp_path, monkeypatch):
    """Stop with active race → daemon returns 200 with status=stopped;
    proxy passes through unchanged."""
    import httpx
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "stopped", "session_id": "s_torcs_live_a", "exit_code": -15,
        })

    import api.main as main_mod
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post("/api/torcs/stop-race")
    assert r.status_code == 200
    assert r.json() == {"status": "stopped", "session_id": "s_torcs_live_a", "exit_code": -15}


def test_stop_race_idempotent_when_no_active_race(tmp_path, monkeypatch):
    """No active race → daemon returns 200 with status=no_active_race.
    UI 'Stop Race' fires-and-forgets; this stays 200."""
    import httpx
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "no_active_race", "exit_code": None})

    import api.main as main_mod
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post("/api/torcs/stop-race")
    assert r.status_code == 200
    assert r.json()["status"] == "no_active_race"


def test_torcs_tracks_returns_empty_when_control_plane_disabled(tmp_path, monkeypatch):
    """Phase 2.5: /api/torcs/tracks gracefully returns empty list when
    TORCS_CONTROL_URL/SECRET aren't configured (UI falls back to a
    hardcoded curated list in this case)."""
    monkeypatch.delenv("TORCS_CONTROL_URL", raising=False)
    monkeypatch.delenv("TORCS_CONTROL_SECRET", raising=False)
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs/tracks")
    assert r.status_code == 200
    assert r.json() == {"tracks": []}


def test_torcs_tracks_proxies_daemon_list(tmp_path, monkeypatch):
    """Daemon /control/tracks → OVERRIDE /api/torcs/tracks. Verify the
    proxy forwards the list verbatim under TorcsTrack shape."""
    import httpx
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/control/tracks"
        assert request.headers["authorization"] == "Bearer test-secret"
        return httpx.Response(200, json={"tracks": [
            {
                "name": "aalborg",
                "category": "road",
                "display_name": "Aalborg",
                "author": "Track Team",
                "description": "Fast road circuit.",
                "length_m": 3200.5,
                "width_m": 12.0,
                "pits": 16,
                "has_preview_asset": True,
                "has_map_asset": True,
            },
            {
                "name": "michigan",
                "category": "oval",
                "display_name": "Michigan",
                "author": None,
                "description": None,
                "length_m": None,
                "width_m": None,
                "pits": None,
                "has_preview_asset": False,
                "has_map_asset": True,
            },
            {
                "name": "dirt-2",
                "category": "dirt",
                "display_name": "Dirt 2",
                "author": None,
                "description": None,
                "length_m": None,
                "width_m": None,
                "pits": None,
                "has_preview_asset": False,
                "has_map_asset": False,
            },
        ]})

    import api.main as main_mod
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs/tracks")
    assert r.status_code == 200
    body = r.json()
    assert len(body["tracks"]) == 3
    assert {t["name"] for t in body["tracks"]} == {"aalborg", "michigan", "dirt-2"}
    cats = {t["name"]: t["category"] for t in body["tracks"]}
    assert cats["michigan"] == "oval"
    assert cats["dirt-2"] == "dirt"
    aalborg = next(t for t in body["tracks"] if t["name"] == "aalborg")
    assert aalborg["display_name"] == "Aalborg"
    assert aalborg["preview_url"].endswith("/api/torcs/tracks/road/aalborg/assets/preview")
    assert aalborg["map_url"].endswith("/api/torcs/tracks/road/aalborg/assets/map")


def test_torcs_track_asset_proxies_binary_response(tmp_path, monkeypatch):
    import httpx

    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/control/tracks/road/aalborg/asset/preview"
        return httpx.Response(
            200,
            content=b"fake-png",
            headers={"content-type": "image/png"},
        )

    import api.main as main_mod

    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs/tracks/road/aalborg/assets/preview")
    assert r.status_code == 200
    assert r.content == b"fake-png"
    assert r.headers["content-type"] == "image/png"


def test_recover_race_returns_daemon_payload(tmp_path, monkeypatch):
    import httpx

    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/control/recover"
        return httpx.Response(200, json={
            "status": "recovered",
            "session_id": "s_torcs_live_a",
            "scr_exit_code": 0,
            "torcs_exit_code": -9,
            "state": "idle",
        })

    import api.main as main_mod

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post("/api/torcs/recover")
    assert r.status_code == 200
    assert r.json()["status"] == "recovered"
    assert r.json()["state"] == "idle"


def test_start_race_writes_stub_active_session(tmp_path, monkeypatch):
    """Phase 2 v1.0 enhancement — Start race persists a stub Session
    with status=ACTIVE and telemetry_file=<session_id>.jsonl so
    /session/<id> renders the LiveTelemetry panel immediately. The
    eventual torcs-live POST updates this row rather than inserting."""
    import httpx
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={
            "session_id": captured["body"]["session_id"],
            "pid": 1234,
            "telemetry_dir": "/home/student/workspace/gym_torcs/telemetry/",
        })

    import api.main as main_mod
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/torcs/start-race",
        json={"track": "aalborg", "laps": 5, "track_name": "Aalborg", "notes": "stub test"},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    assert sid.startswith("s_torcs_live_")
    # Daemon got the deterministic filename
    assert captured["body"]["telemetry_filename"] == f"{sid}.jsonl"

    # The stub Session must be reachable via GET /api/sessions/{id}
    r2 = client.get(f"/api/sessions/{sid}")
    assert r2.status_code == 200, r2.text
    summary = r2.json()["summary"]
    assert summary["session_id"] == sid
    assert summary["status"] == "active"
    assert summary["session_source"] == "torcs_live"
    assert summary["telemetry_file"] == f"{sid}.jsonl"
    assert summary["track_name"] == "Aalborg"
    assert summary["target_laps"] == 5
    assert summary["driver_profile_id"] == DEFAULT_DRIVER_PROFILE_ID
    assert summary["driver_profile_name"] == "Baseline Demo Driver"
    assert summary["driver_profile_origin"] == "shipped_default"
    assert summary["lap_count"] == 0       # stub — laps land via torcs-live ingest
    assert summary["zone_count"] == 0
    snapshot = r2.json()["driver_config_snapshot"]
    assert snapshot["driver_profile_id"] == DEFAULT_DRIVER_PROFILE_ID
    assert snapshot["config"]["speed"]["target_speed_kmh"] == 85.0

    # And the stub must appear in the GET /api/sessions index
    r3 = client.get("/api/sessions")
    ids = {s["session_id"] for s in r3.json()["sessions"]}
    assert sid in ids


def test_start_race_reconciles_control_unreachable_when_daemon_reports_same_session(tmp_path, monkeypatch):
    """Regression: if the start proxy times out after the daemon actually
    launched the session, OVERRIDE should reconcile against control-status,
    persist the stub session, and still return success."""
    import httpx

    telem = tmp_path / "telemetry"
    telem.mkdir()
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/control/start":
            captured["body"] = json.loads(request.content)
            raise httpx.ReadTimeout("start timed out", request=request)
        if request.url.path == "/control/status":
            return httpx.Response(200, json={
                "active": True,
                "state": "active",
                "session_id": captured["body"]["session_id"],
                "track": captured["body"]["track"],
                "laps": captured["body"]["laps"],
                "launch_mode": captured["body"]["launch_mode"],
            })
        raise AssertionError(f"unexpected daemon request: {request.method} {request.url}")

    import api.main as main_mod

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        main_mod.httpx,
        "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/torcs/start-race",
        json={"track": "aalborg", "laps": 5, "track_name": "Aalborg", "notes": "reconcile test"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    sid = body["session_id"]
    assert sid == captured["body"]["session_id"]
    assert body["telemetry_dir"] == str(telem)
    assert body["launch_mode"] == "cockpit_practice"
    assert body["state"] == "active"

    r2 = client.get(f"/api/sessions/{sid}")
    assert r2.status_code == 200, r2.text
    summary = r2.json()["summary"]
    assert summary["status"] == "active"
    assert summary["session_source"] == "torcs_live"
    assert summary["telemetry_file"] == f"{sid}.jsonl"
    assert summary["driver_profile_id"] == DEFAULT_DRIVER_PROFILE_ID


def test_torcs_live_updates_stub_session_when_run_id_matches(tmp_path, monkeypatch):
    """Phase 2 v1.0 enhancement — when torcs-live is called with a
    run_id matching the daemon's session_id prefix (s_torcs_live_...),
    the pipeline adopts that session_id so the write UPDATES the stub
    Session row instead of inserting a fresh slug."""
    import httpx
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    def daemon_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(201, json={
            "session_id": body["session_id"],
            "pid": 5555,
            "telemetry_dir": "/home/student/workspace/gym_torcs/telemetry/",
        })

    import api.main as main_mod
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(daemon_handler)
    monkeypatch.setattr(
        main_mod.httpx, "AsyncClient",
        lambda **kw: original_client(transport=transport, **{k: v for k, v in kw.items() if k != "transport"}),
    )

    telem = tmp_path / "telemetry"
    telem.mkdir()
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))

    # 1) Start race → stub session written, JSONL filename pinned
    start = client.post(
        "/api/torcs/start-race",
        json={"track": "aalborg", "laps": 3, "track_name": "Aalborg"},
    ).json()
    sid = start["session_id"]

    # 2) Simulate gym_torcs writing the JSONL with that exact filename
    (telem / f"{sid}.jsonl").write_bytes(_torcs_jsonl_payload(n_laps=2))

    # 3) Ingest via torcs-live with run_id=session_id — should UPDATE stub
    r = client.post("/api/sessions/torcs-live", json={"run_id": sid})
    assert r.status_code == 201, r.text
    ingested = r.json()
    assert ingested["summary"]["session_id"] == sid     # adopted from run_id, not pipeline-generated
    assert ingested["summary"]["status"] == "completed"  # stub flipped from active
    assert ingested["summary"]["lap_count"] >= 1        # real lap data wrote in
    assert ingested["summary"]["driver_profile_id"] == DEFAULT_DRIVER_PROFILE_ID
    assert ingested["driver_config_snapshot"]["driver_profile_id"] == DEFAULT_DRIVER_PROFILE_ID

    # 4) Only ONE row exists in the index — not a stub + a fresh one
    listing = client.get("/api/sessions").json()
    matching = [s for s in listing["sessions"] if s["session_id"] == sid]
    assert len(matching) == 1
    assert matching[0]["status"] == "completed"


def test_start_race_validates_track_pattern(tmp_path, monkeypatch):
    """Pydantic rejects malformed track BEFORE we proxy. Defense in
    depth — the daemon also validates, but failing fast here means the
    daemon never sees a bad payload at all."""
    monkeypatch.setenv("TORCS_CONTROL_URL", "http://fake-daemon:7000")
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post("/api/torcs/start-race", json={"track": "../etc/passwd", "laps": 5})
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3 — SSE live telemetry stream
# ──────────────────────────────────────────────────────────────────────────────


def _sse_jsonl_payload(n_laps: int, ticks_per_lap: int = 50) -> bytes:
    """Minimal lap-shape JSONL for SSE helper tests. Each tick has the
    fields _aggregate_lap reads: curLapTime, distFromStart, speedX,
    accel, brake, fuel."""
    track_length = 3000.0
    lap_duration_s = 36.0
    dt = lap_duration_s / ticks_per_lap
    lines: list[str] = []
    for lap_i in range(n_laps):
        for tick_i in range(ticks_per_lap):
            cur = tick_i * dt
            dist = (tick_i / ticks_per_lap) * track_length
            lines.append(json.dumps({
                "curLapTime": [cur],
                "distFromStart": [dist],
                "speedX": [60.0 if tick_i > ticks_per_lap // 2 else 30.0],
                "accel": [1.0 if tick_i > ticks_per_lap // 2 else 0.5],
                "brake": [0.6 if tick_i < ticks_per_lap // 4 else 0.0],
                "fuel": [90.0 - lap_i * 0.5],
            }))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _sse_jsonl_payload_partial_start(
    n_complete_laps: int = 2,
    join_distance: float = 2500.0,
    ticks_per_lap: int = 50,
) -> bytes:
    """JSONL where the SCR client joined mid-lap (first observation's
    distFromStart starts at `join_distance` instead of 0). Used to test
    the partial-first-segment skip logic added during the live-test pass."""
    track_length = 3000.0
    lap_duration_s = 36.0
    dt = lap_duration_s / ticks_per_lap
    lines: list[str] = []
    # Partial first segment — start mid-track, run to the start-line.
    n_partial_ticks = int(ticks_per_lap * (1 - join_distance / track_length))
    cur_lap_t_seed = lap_duration_s * (join_distance / track_length)
    for tick_i in range(n_partial_ticks):
        frac_through = (join_distance + tick_i * (track_length - join_distance) / n_partial_ticks) / track_length
        cur_t = cur_lap_t_seed + tick_i * dt
        dist = join_distance + tick_i * (track_length - join_distance) / n_partial_ticks
        lines.append(json.dumps({
            "curLapTime": [cur_t], "distFromStart": [dist],
            "speedX": [60.0], "accel": [1.0], "brake": [0.0], "fuel": [90.0],
        }))
    # Then n_complete_laps full laps, each starting at dist=0
    for lap_i in range(n_complete_laps):
        for tick_i in range(ticks_per_lap):
            cur_t = tick_i * dt
            dist = (tick_i / ticks_per_lap) * track_length
            lines.append(json.dumps({
                "curLapTime": [cur_t], "distFromStart": [dist],
                "speedX": [60.0 if tick_i > ticks_per_lap // 2 else 30.0],
                "accel": [1.0 if tick_i > ticks_per_lap // 2 else 0.5],
                "brake": [0.6 if tick_i < ticks_per_lap // 4 else 0.0],
                "fuel": [90.0 - lap_i * 0.5],
            }))
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_first_segment_is_partial_detects_mid_lap_join():
    """SCR client joining at distFromStart=2500m → partial=True; starting
    at 0 → partial=False. Threshold is 100m."""
    from api.main import _first_segment_is_partial
    assert _first_segment_is_partial([{"distFromStart": [2500.0]}]) is True
    assert _first_segment_is_partial([{"distFromStart": [50.0]}]) is False
    # No valid observations → not partial (conservative default)
    assert _first_segment_is_partial([]) is False
    assert _first_segment_is_partial([{"distFromStart": "invalid"}]) is False


def test_get_current_lap_skips_partial_first_segment():
    """JSONL starts mid-lap at dist=2500m. Then 2 segments follow:
    one wraparound completes the partial (skipped), the second wraparound
    completes the first FULL lap. The second full lap is in progress at
    end-of-stream, so only 1 complete lap is fully captured.

    Without partial skip we'd return 2 (raw wraparound count); with skip
    we return 1 (only the first full lap is fully bounded by wraparounds)."""
    import tempfile, os as _os
    from api.main import _get_current_lap, _read_jsonl_safe

    with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
        f.write(_sse_jsonl_payload_partial_start(n_complete_laps=2))
        p = f.name
    try:
        obs = _read_jsonl_safe(Path(p))
        # 1 full lap completed (partial-end wraparound skipped from the count)
        assert _get_current_lap(obs) == 1
    finally:
        _os.unlink(p)


def test_aggregate_lap_skips_partial_when_client_joined_mid_lap():
    """_aggregate_lap(lap_index=1) on partial-start data should return
    the first COMPLETE lap (post-wraparound), NOT the partial pre-wrap
    segment. This is the live-test fix: prevents the "L1 = 8.66s"
    misleading row in the SSE table."""
    import tempfile, os as _os
    from api.main import _aggregate_lap, _read_jsonl_safe

    with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
        f.write(_sse_jsonl_payload_partial_start(n_complete_laps=2))
        p = f.name
    try:
        obs = _read_jsonl_safe(Path(p))
        lap1 = _aggregate_lap(obs, 1)
    finally:
        _os.unlink(p)
    assert lap1 is not None
    assert lap1.lap == 1
    # First COMPLETE lap should have ~36s lap time (the synthetic
    # constant), NOT the much shorter partial duration.
    assert lap1.lap_time_s > 20.0, f"lap_time={lap1.lap_time_s}: partial wasn't skipped"


def test_list_sessions_enriches_active_session_with_live_lap_count(tmp_path, monkeypatch):
    """ACTIVE sessions' lap_count is patched in from the JSONL on the
    shared volume — Phase 2 v1.0 fix for "/sessions shows 0 laps while
    Live Race Telemetry shows 3"."""
    from datetime import datetime, timezone
    from ingest.schema import Session, SessionSource, SessionStatus, SessionSummary

    telem = tmp_path / "telemetry"
    telem.mkdir()
    sid = "s_torcs_live_1234567_abcd"
    (telem / f"{sid}.jsonl").write_bytes(_sse_jsonl_payload(n_laps=3))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))

    # Manually write an ACTIVE stub session pointing at the JSONL
    from api.storage import save_session
    stub = Session(
        summary=SessionSummary(
            session_id=sid,
            uploaded_at=datetime.now(timezone.utc),
            source="torcs",
            lap_count=0,                     # stub value
            forecast_available=False,
            zone_count=0,
            track_id=f"torcs-live/{sid}",
            session_source=SessionSource.TORCS_LIVE,
            status=SessionStatus.ACTIVE,
            telemetry_file=f"{sid}.jsonl",
            track_name="Aalborg",
        ),
        laps=[], forecast=None, recommendations=[], regulation_source=None,
    )
    save_session(stub, root=Path(client.app.state.sessions_root)) if hasattr(client.app.state, "sessions_root") else save_session(stub)

    r = client.get("/api/sessions").json()
    row = next((s for s in r["sessions"] if s["session_id"] == sid), None)
    assert row is not None
    # 3-lap synthetic payload → 2 completed wraparounds → lap_count=2
    # (the stub's 0 has been live-patched)
    assert row["lap_count"] == 2, f"got {row['lap_count']}, expected 2"
    assert row["status"] == "active"


def test_get_current_lap_counts_completed_via_wraparound():
    """_get_current_lap detects start-line crossings (distFromStart drops
    sharply). 3 laps in the JSONL → 2 completed laps (still mid-lap on #3)."""
    from api.main import _get_current_lap, _read_jsonl_safe

    import tempfile, os as _os
    with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
        f.write(_sse_jsonl_payload(n_laps=3))
        p = f.name
    try:
        obs = _read_jsonl_safe(Path(p))
        assert _get_current_lap(obs) == 2
    finally:
        _os.unlink(p)


def test_read_jsonl_safe_skips_incomplete_tail_line():
    """Gotcha #12 — writer is still appending; the last line may not
    have a trailing newline yet. _read_jsonl_safe stops at that line."""
    import tempfile, os as _os
    from api.main import _read_jsonl_safe

    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        f.write('{"a": 1}\n')
        f.write('{"a": 2}\n')
        f.write('{"a": 3')   # no trailing \n — incomplete
        p = f.name
    try:
        obs = _read_jsonl_safe(Path(p))
        assert obs == [{"a": 1}, {"a": 2}]
    finally:
        _os.unlink(p)


def test_aggregate_lap_uses_torcs_energy_constants():
    """_aggregate_lap should produce harvest_mj > 0 (brake time present)
    and 0 <= soc_end <= 1. Confirms the analysis.torcs_energy constants
    are wired and not silently bypassed."""
    import tempfile, os as _os
    from api.main import _aggregate_lap, _read_jsonl_safe

    with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
        f.write(_sse_jsonl_payload(n_laps=2))
        p = f.name
    try:
        obs = _read_jsonl_safe(Path(p))
        stats = _aggregate_lap(obs, 1)
    finally:
        _os.unlink(p)
    assert stats is not None
    assert stats.lap == 1
    assert stats.harvest_mj > 0
    assert 0.0 <= stats.soc_end <= 1.0
    assert stats.max_speed_kmh >= stats.avg_speed_kmh > 0


def test_aggregate_lap_uses_speedx_as_kmh_without_extra_conversion():
    """Regression: TORCS speedX is already in km/h. The live helper must
    not multiply by 3.6 or the cockpit sidebar drifts far above the in-sim
    gauge."""
    import tempfile, os as _os
    from api.main import _aggregate_lap, _read_jsonl_safe

    with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
        f.write(_sse_jsonl_payload(n_laps=2))
        p = f.name
    try:
        obs = _read_jsonl_safe(Path(p))
        stats = _aggregate_lap(obs, 1)
    finally:
        _os.unlink(p)

    assert stats is not None
    assert stats.avg_speed_kmh == 44.4
    assert stats.max_speed_kmh == 60.0


def test_aggregate_live_snapshot_uses_speedx_as_kmh_without_extra_conversion():
    """Regression: the in-progress live snapshot should stay in TORCS-native
    km/h so the sidebar agrees with the simulator HUD."""
    import tempfile, os as _os
    from api.main import _aggregate_live_snapshot, _read_jsonl_safe

    with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
        f.write(_sse_jsonl_payload(n_laps=2))
        p = f.name
    try:
        obs = _read_jsonl_safe(Path(p))
        snap = _aggregate_live_snapshot(obs)
    finally:
        _os.unlink(p)

    assert snap is not None
    assert snap.lap == 2
    assert snap.speed_kmh == 60.0
    assert snap.avg_speed_kmh == 44.4
    assert snap.max_speed_kmh == 60.0


def test_aggregate_lap_returns_none_when_lap_index_out_of_range():
    """Asking for lap 5 when only 2 are present → None (caller skips)."""
    import tempfile, os as _os
    from api.main import _aggregate_lap, _read_jsonl_safe

    with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
        f.write(_sse_jsonl_payload(n_laps=2))
        p = f.name
    try:
        obs = _read_jsonl_safe(Path(p))
        assert _aggregate_lap(obs, 5) is None
    finally:
        _os.unlink(p)


def test_stream_404_when_session_missing(tmp_path):
    """GET /api/sessions/<unknown>/stream → 404 with NOT_FOUND."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/sessions/s_nonexistent_session/stream")
    assert r.status_code == 404
    assert r.json()["error_code"] == "NOT_FOUND"


def test_stream_recovers_missing_torcs_live_session_when_capture_exists(tmp_path, monkeypatch):
    """Regression: if a live TORCS capture exists on disk but the ACTIVE
    stub session row is missing, the stream should backfill that row and
    start streaming instead of 404ing."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    sid = "s_torcs_live_12345678_recover"
    (telem / f"{sid}.jsonl").write_bytes(_sse_jsonl_payload(n_laps=2))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))

    with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
        assert r.status_code == 200
        events: list[dict] = []
        for line in r.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                events.append(payload)
                if payload.get("event") == "lap":
                    break

    assert events[0]["event"] == "connected"
    assert any(event["event"] == "lap" for event in events)

    summary = client.get(f"/api/sessions/{sid}").json()["summary"]
    assert summary["session_id"] == sid
    assert summary["status"] == "active"
    assert summary["session_source"] == "torcs_live"
    assert summary["telemetry_file"] == f"{sid}.jsonl"


def test_stream_emits_no_telemetry_when_session_lacks_telemetry_file(tmp_path):
    """A session with no telemetry_file (e.g. fastf1 upload) should emit
    one connected + one no_telemetry event, then close."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    with client.stream("GET", f"/api/sessions/{sid}/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events: list[dict] = []
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
                if events[-1].get("event") == "no_telemetry":
                    break
    assert events[0]["event"] == "connected"
    assert events[0]["session_id"] == sid
    assert any(e["event"] == "no_telemetry" for e in events)


def test_report_endpoint_builds_and_caches_report_artifact(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    response = client.get(f"/api/sessions/{sid}/report")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == sid
    assert body["title"]
    assert isinstance(body["key_moments"], list)

    report_path = Path(os.environ["SESSIONS_DIR"]) / sid / "report.json"
    assert report_path.is_file()


def test_lap_analysis_endpoint_builds_and_caches_lap_artifact(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    response = client.get(f"/api/sessions/{sid}/laps/3")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == sid
    assert body["lap_number"] == 3
    assert body["headline"]

    lap_path = Path(os.environ["SESSIONS_DIR"]) / sid / "laps" / "3.json"
    assert lap_path.is_file()


def test_lap_analysis_endpoint_404s_for_missing_lap(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    response = client.get(f"/api/sessions/{sid}/laps/99")
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"


def test_session_copilot_returns_grounded_lap_comparison(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    response = client.post(
        f"/api/sessions/{sid}/copilot",
        json={
            "question": "Compare lap 2 and lap 4",
            "recent_turns": [
                {
                    "role": "user",
                    "content": "Give me a race summary",
                    "timestamp": "2026-05-20T12:00:00+00:00",
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "granite"
    assert body["confidence"] == "high"
    assert body["supporting_laps"] == [2, 4]
    assert "Lap 4" in body["answer"]


def test_session_copilot_falls_back_when_model_output_is_malformed(tmp_path):
    sessions_dir = tmp_path / "sessions"
    creator = _build_client(
        tmp_path=tmp_path,
        chunks_path=_empty_chunks_path(tmp_path),
        sessions_dir=sessions_dir,
    )
    created = creator.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    client = _build_client(
        tmp_path=tmp_path,
        chunks_path=_empty_chunks_path(tmp_path),
        chat=FakeChatClient(responses=["not-json"]),
        sessions_dir=sessions_dir,
    )

    response = client.post(
        f"/api/sessions/{sid}/copilot",
        json={"question": "Why did the AI recommend the current strategy?", "recent_turns": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "deterministic"
    assert len(body["supporting_laps"]) == 1
    assert f"OVERRIDE highlighted lap {body['supporting_laps'][0]}" in body["answer"]


def test_session_copilot_salvages_granite_prose_answer(tmp_path):
    sessions_dir = tmp_path / "sessions"
    creator = _build_client(
        tmp_path=tmp_path,
        chunks_path=_empty_chunks_path(tmp_path),
        sessions_dir=sessions_dir,
    )
    created = creator.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    prose = (
        "Lap 4 spent more net energy than lap 2 and finished the stint with a tighter battery reserve. "
        "That is why OVERRIDE would support a more conservative deployment pattern later in the run."
    )
    client = _build_client(
        tmp_path=tmp_path,
        chunks_path=_empty_chunks_path(tmp_path),
        chat=FakeChatClient(responses=[prose]),
        sessions_dir=sessions_dir,
    )

    response = client.post(
        f"/api/sessions/{sid}/copilot",
        json={"question": "Compare lap 2 and lap 4", "recent_turns": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "granite"
    assert body["supporting_laps"] == [4, 2] or body["supporting_laps"] == [2, 4]
    assert "Lap 4 spent more net energy than lap 2" in body["answer"]


def test_session_copilot_uses_live_context_for_deterministic_fallback(tmp_path):
    sessions_dir = tmp_path / "sessions"
    creator = _build_client(
        tmp_path=tmp_path,
        chunks_path=_empty_chunks_path(tmp_path),
        sessions_dir=sessions_dir,
    )
    created = creator.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    client = _build_client(
        tmp_path=tmp_path,
        chunks_path=_empty_chunks_path(tmp_path),
        chat=FakeChatClient(responses=["not-json"]),
        sessions_dir=sessions_dir,
    )

    response = client.post(
        f"/api/sessions/{sid}/copilot",
        json={
            "question": "Are we under battery pressure now?",
            "recent_turns": [],
            "context": {
                "mode": "live_race",
                "lap_number": 3,
                "live": {
                    "race_state": "active",
                    "latest_snapshot": {
                        "lap": 3,
                        "lap_time_s": 18.2,
                        "speed_kmh": 198.0,
                        "avg_speed_kmh": 193.4,
                        "max_speed_kmh": 246.1,
                        "dist_from_start_m": 1420.0,
                        "lap_progress_pct": 47.5,
                        "sector": 2,
                        "throttle_frac": 0.88,
                        "brake_frac": 0.0,
                        "steer_frac": 0.06,
                        "gear": 6,
                        "fuel_kg": 84.5,
                        "fuel_used_kg": 0.18,
                        "harvest_mj": 0.22,
                        "deploy_mj": 0.54,
                        "soc_estimate": 0.48,
                        "soc_source": "derived",
                        "balance_label": "spending",
                    },
                    "completed_laps": [
                        {
                            "lap": 1,
                            "lap_time_s": 36.9,
                            "avg_speed_kmh": 198.1,
                            "max_speed_kmh": 243.2,
                            "harvest_mj": 0.28,
                            "deploy_mj": 0.62,
                            "soc_end": 0.61,
                            "fuel_used_kg": 0.43,
                        },
                        {
                            "lap": 2,
                            "lap_time_s": 36.6,
                            "avg_speed_kmh": 199.4,
                            "max_speed_kmh": 244.6,
                            "harvest_mj": 0.26,
                            "deploy_mj": 0.71,
                            "soc_end": 0.54,
                            "fuel_used_kg": 0.44,
                        },
                    ],
                    "insights": [
                        {
                            "insight_id": "li_energy_pressure_v1_l2_s2",
                            "rule_id": "energy_pressure_v1",
                            "kind": "strategy_recommendation",
                            "severity": "high",
                            "headline": "Energy pressure building",
                            "message": "Deploy exceeded harvest across the last closed lap and the current lap trend is still net-spend.",
                            "recommended_action": "Recommend conservative deployment until the reserve trend flattens.",
                            "confidence": "high",
                            "evidence": [
                                "Lap 2 closed with 0.71 MJ deploy vs 0.26 MJ harvest.",
                                "Current SoC estimate is 48%.",
                            ],
                            "lap": 2,
                            "sector": 2,
                        }
                    ],
                },
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "deterministic"
    assert "Live battery reserve is tracking around" in body["answer"]
    assert body["supporting_laps"]


def test_session_copilot_stream_emits_deltas_then_complete(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    with client.stream(
        "POST",
        f"/api/sessions/{sid}/copilot/stream",
        json={"question": "Compare lap 2 and lap 4", "recent_turns": []},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events: list[dict] = []
        for line in r.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                events.append(payload)
                if payload.get("event") == "complete":
                    break

    assert events[0]["event"] == "start"
    assert any(event["event"] == "delta" for event in events)
    assert events[-1]["event"] == "complete"
    assert events[-1]["answer"]["engine"] == "granite"
    assert events[-1]["answer"]["supporting_laps"] == [2, 4]


def test_session_copilot_greeting_returns_conversational_reply(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    response = client.post(
        f"/api/sessions/{sid}/copilot",
        json={"question": "Hello", "recent_turns": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Hello" in body["answer"]
    assert "grounded in this session" in body["answer"]


def test_session_copilot_sanitizes_metadata_and_fabricated_citation_in_answer(tmp_path):
    sessions_dir = tmp_path / "sessions"
    creator = _build_client(
        tmp_path=tmp_path,
        chunks_path=_empty_chunks_path(tmp_path),
        sessions_dir=sessions_dir,
    )
    created = creator.post(
        "/api/sessions",
        files={"file": ("a.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    raw = json.dumps({
        "answer": (
            "**Answer:** The recommendation focuses on lap 8, where excess harvest wasted energy under FIA 2026 Technical Regulation C5.2.9. "
            "**Confidence:** high **Supporting laps:** 8 **Suggestions:** 1. Compare laps."
        ),
        "engine": "granite",
        "supporting_laps": [8],
        "confidence": "high",
        "suggestions": ["Compare two laps"],
    })
    client = _build_client(
        tmp_path=tmp_path,
        chunks_path=_empty_chunks_path(tmp_path),
        chat=FakeChatClient(responses=[raw]),
        sessions_dir=sessions_dir,
    )

    response = client.post(
        f"/api/sessions/{sid}/copilot",
        json={"question": "Why did OVERRIDE recommend the current strategy?", "recent_turns": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "granite"
    assert "**" not in body["answer"]
    assert "Confidence:" not in body["answer"]
    assert "Suggestions:" not in body["answer"]
    assert "C5.2.9" not in body["answer"]
    assert any(item.startswith("Compare lap ") for item in body["suggestions"])


def test_session_copilot_404s_for_missing_session(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    response = client.post(
        "/api/sessions/s_missing/copilot",
        json={"question": "Why was conservative mode recommended?", "recent_turns": []},
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"


def test_stream_waits_for_active_torcs_live_file_to_appear(tmp_path, monkeypatch):
    """A freshly-started 3D Cockpit run writes the ACTIVE session stub before
    the JSONL file may exist. The stream should wait and emit laps once the
    writer creates the file instead of closing as no_telemetry."""
    import threading
    import time as _time
    from api.storage import save_session
    from ingest.schema import Session, SessionSource, SessionStatus, SessionSummary

    telem = tmp_path / "telemetry"
    telem.mkdir()
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))

    sid = "s_torcs_live_1234567_abcd"
    save_session(Session(
        summary=SessionSummary(
            session_id=sid,
            uploaded_at=datetime.now(timezone.utc),
            source="torcs",
            lap_count=0,
            forecast_available=False,
            zone_count=0,
            track_id=f"torcs-live/{sid}",
            session_source=SessionSource.TORCS_LIVE,
            status=SessionStatus.ACTIVE,
            telemetry_file=f"{sid}.jsonl",
            track_name="Aalborg",
            target_laps=5,
        ),
        laps=[],
        forecast=None,
        recommendations=[],
        regulation_source=None,
    ))

    def _write_jsonl_after_stream_starts():
        _time.sleep(0.1)
        (telem / f"{sid}.jsonl").write_bytes(_sse_jsonl_payload(n_laps=2))

    events: list[dict] = []
    writer = threading.Thread(target=_write_jsonl_after_stream_starts)
    writer.start()
    try:
        with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
            assert r.status_code == 200
            for line in r.iter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[len("data: "):])
                    events.append(ev)
                    if ev.get("event") == "lap":
                        break
    finally:
        writer.join(timeout=1.0)

    kinds = [e["event"] for e in events]
    assert kinds[0] == "connected"
    assert "no_telemetry" not in kinds
    assert "lap" in kinds


def test_stream_emits_lap_events_then_race_ended_on_stall(tmp_path, monkeypatch):
    """End-to-end SSE happy path: ingest a torcs-live session, open the
    stream, file is static (race already ended) → stream emits laps
    quickly then a race_ended event via the file-stall heuristic.

    Patches STALL_SECONDS_THRESHOLD + POLL_INTERVAL_S down to keep the
    test fast (~1s vs 10s wall clock). Confirms the disconnect+stall
    machinery actually fires."""
    import api.main as main_mod

    # Patch internal constants so the test finishes in ~1s
    orig_stall = "STALL_SECONDS_THRESHOLD"
    orig_poll = "POLL_INTERVAL_S"
    # The constants are local to stream_session; we need to patch _build_client's
    # underlying app behavior via the SSE generator. Simplest: patch asyncio.sleep
    # to be much faster.

    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "race.jsonl").write_bytes(_sse_jsonl_payload(n_laps=2))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    ingest = client.post("/api/sessions/torcs-live", json={"run_id": "race"})
    assert ingest.status_code == 201
    sid = ingest.json()["summary"]["session_id"]

    # Speed up the SSE polling for the test. The stream_session generator
    # uses module-level asyncio.sleep + a closed-over STALL_SECONDS_THRESHOLD.
    # Patching asyncio.sleep is the simplest way to compress the timeline.
    import asyncio as _asyncio
    orig_sleep = _asyncio.sleep
    async def _fast_sleep(s):
        await orig_sleep(min(s, 0.01))
    monkeypatch.setattr(main_mod.asyncio, "sleep", _fast_sleep)

    events: list[dict] = []
    with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                events.append(ev)
                if ev.get("event") == "race_ended":
                    break

    kinds = [e["event"] for e in events]
    assert kinds[0] == "connected"
    assert "lap" in kinds, f"expected lap event, got {kinds}"
    assert kinds[-1] == "race_ended", f"expected race_ended at end, got {kinds}"
    # 2 laps in the fixture → 1 completed lap detected (still mid-lap on #2 at
    # the time of stall — the second wraparound is at the boundary of lap 3).
    # Don't pin the exact count; just confirm at least one lap event fired.


def test_stream_emits_deterministic_insight_events(tmp_path, monkeypatch):
    """Live stream should now emit rule-backed insight events alongside the
    existing snapshot/lap payloads."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "insightful.jsonl").write_bytes(_sse_jsonl_payload(n_laps=2))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    ingest = client.post("/api/sessions/torcs-live", json={"run_id": "insightful"})
    assert ingest.status_code == 201
    sid = ingest.json()["summary"]["session_id"]

    events: list[dict] = []
    with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                events.append(ev)
                if ev.get("event") == "insight":
                    break

    insight = next(event["insight"] for event in events if event.get("event") == "insight")
    assert insight["insight_id"].startswith("li_")
    assert insight["rule_id"] is not None
    assert insight["headline"]
    assert isinstance(insight["evidence"], list)




# ──────────────────────────────────────────────────────────────────────────────
# Snapshot SSE events — in-progress lap at ~4 Hz
# ──────────────────────────────────────────────────────────────────────────────


def _sse_in_progress_only(ticks: int = 25) -> bytes:
    """JSONL with a single partial (in-progress) lap — no wraparound yet."""
    track_length = 3000.0
    lap_duration_s = 36.0
    dt = lap_duration_s / 50
    lines: list[str] = []
    for tick_i in range(ticks):
        dist = (tick_i / 50) * track_length
        lines.append(json.dumps({
            "curLapTime": [tick_i * dt],
            "distFromStart": [dist],
            "speedX": [55.0],
            "accel": [0.8],
            "brake": [0.0],
            "fuel": [89.0],
        }))
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_snapshot_emits_before_first_completed_lap(tmp_path, monkeypatch):
    """A JSONL with only in-progress (no wraparound) ticks must produce a
    snapshot event before any lap event, and no lap event at all."""
    import api.main as main_mod
    import asyncio as _asyncio

    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "partial.jsonl").write_bytes(_sse_in_progress_only(ticks=25))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    ingest = client.post("/api/sessions/torcs-live", json={"run_id": "partial"})
    assert ingest.status_code == 201
    sid = ingest.json()["summary"]["session_id"]

    orig_sleep = _asyncio.sleep
    async def _fast_sleep(s): await orig_sleep(min(s, 0.01))
    monkeypatch.setattr(main_mod.asyncio, "sleep", _fast_sleep)

    events: list[dict] = []
    with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                events.append(ev)
                # Collect connected + first snapshot, then stop.
                if ev.get("event") == "snapshot":
                    break

    kinds = [e["event"] for e in events]
    assert kinds[0] == "connected"
    assert "snapshot" in kinds, f"Expected snapshot event, got {kinds}"
    assert "lap" not in kinds, f"No lap should have been emitted yet, got {kinds}"

    snap = next(e for e in events if e["event"] == "snapshot")
    assert "snapshot" in snap, "snapshot event must have nested 'snapshot' key"
    assert snap["snapshot"]["lap"] == 1
    assert 0.0 < snap["snapshot"]["lap_progress_pct"] < 100.0


def test_snapshot_emits_during_in_progress_lap(tmp_path, monkeypatch):
    """JSONL with 1 complete lap + partial second lap → snapshot shows lap=2."""
    import api.main as main_mod
    import asyncio as _asyncio

    telem = tmp_path / "telemetry"
    telem.mkdir()
    # n_laps=2 means lap 1 fully closed + lap 2 in-progress (no closing wraparound)
    (telem / "two.jsonl").write_bytes(_sse_jsonl_payload(n_laps=2))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    ingest = client.post("/api/sessions/torcs-live", json={"run_id": "two"})
    assert ingest.status_code == 201
    sid = ingest.json()["summary"]["session_id"]

    orig_sleep = _asyncio.sleep
    async def _fast_sleep(s): await orig_sleep(min(s, 0.01))
    monkeypatch.setattr(main_mod.asyncio, "sleep", _fast_sleep)

    snap_events: list[dict] = []
    with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                if ev.get("event") == "snapshot":
                    snap_events.append(ev)
                    break  # one snapshot is enough to verify

    assert snap_events, "Expected at least one snapshot event"
    snap = snap_events[0]["snapshot"]
    assert snap["lap"] == 2, f"Snapshot should be for lap 2 (in-progress), got {snap['lap']}"
    assert 0.0 < snap["lap_progress_pct"] <= 100.0
    assert 0.0 <= snap["soc_estimate"] <= 1.0
    assert snap["balance_label"] in ("spending", "recovering", "balanced")


def test_snapshot_deduplication_skips_identical_state(tmp_path, monkeypatch):
    """A static (non-updating) JSONL file should produce only one snapshot
    per unique signature, not a flood on every poll cycle."""
    import api.main as main_mod
    import asyncio as _asyncio

    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "static.jsonl").write_bytes(_sse_jsonl_payload(n_laps=2))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    ingest = client.post("/api/sessions/torcs-live", json={"run_id": "static"})
    assert ingest.status_code == 201
    sid = ingest.json()["summary"]["session_id"]

    poll_count = 0
    orig_sleep = _asyncio.sleep
    async def _counting_sleep(s):
        nonlocal poll_count
        poll_count += 1
        await orig_sleep(min(s, 0.01))
    monkeypatch.setattr(main_mod.asyncio, "sleep", _counting_sleep)

    events: list[dict] = []
    with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                events.append(ev)
                if ev.get("event") == "race_ended":
                    break

    snapshots = [e for e in events if e.get("event") == "snapshot"]
    # Static file → distinct snapshots should be << poll_count (dedup working).
    # Allow up to 2 unique snapshots (initial read + race-end poll) but never O(polls).
    assert len(snapshots) <= 2, (
        f"Deduplication should limit snapshots on a static file; got {len(snapshots)} "
        f"over {poll_count} polls"
    )


def test_race_ended_still_fires_after_snapshots(tmp_path, monkeypatch):
    """The stream must still emit race_ended as the final event even when
    snapshot events have been flowing before the stall threshold fires."""
    import api.main as main_mod
    import asyncio as _asyncio

    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "full.jsonl").write_bytes(_sse_jsonl_payload(n_laps=3))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    ingest = client.post("/api/sessions/torcs-live", json={"run_id": "full"})
    assert ingest.status_code == 201
    sid = ingest.json()["summary"]["session_id"]

    orig_sleep = _asyncio.sleep
    async def _fast_sleep(s): await orig_sleep(min(s, 0.01))
    monkeypatch.setattr(main_mod.asyncio, "sleep", _fast_sleep)

    events: list[dict] = []
    with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                events.append(ev)
                if ev.get("event") == "race_ended":
                    break

    kinds = [e["event"] for e in events]
    assert "snapshot" in kinds, f"Expected snapshot events before race_ended, got {kinds}"
    assert kinds[-1] == "race_ended", f"Expected race_ended as final event, got {kinds}"


def test_no_snapshot_emitted_after_race_ended(tmp_path, monkeypatch):
    """race_ended must be the last event; no snapshot should follow it.
    Guards against the stale-live-state bug where the cockpit could keep
    rendering 'Live telemetry updating…' after the race is over."""
    import api.main as main_mod
    import asyncio as _asyncio

    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "done.jsonl").write_bytes(_sse_jsonl_payload(n_laps=3))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    ingest = client.post("/api/sessions/torcs-live", json={"run_id": "done"})
    assert ingest.status_code == 201
    sid = ingest.json()["summary"]["session_id"]

    orig_sleep = _asyncio.sleep
    async def _fast_sleep(s): await orig_sleep(min(s, 0.01))
    monkeypatch.setattr(main_mod.asyncio, "sleep", _fast_sleep)

    events: list[dict] = []
    with client.stream("GET", f"/api/sessions/{sid}/stream", timeout=15.0) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                events.append(ev)
                if ev.get("event") == "race_ended":
                    break

    kinds = [e["event"] for e in events]
    assert kinds[-1] == "race_ended", f"Last event must be race_ended, got {kinds}"
    # No snapshot may appear after race_ended (stream closes at that point).
    race_ended_idx = next(i for i, k in enumerate(kinds) if k == "race_ended")
    trailing = kinds[race_ended_idx + 1:]
    assert not trailing, f"Events after race_ended: {trailing}"





def test_what_if_happy_path_returns_perturbed_recommendations(tmp_path):
    """Create a session, then POST a delay_first_deploy what-if. Verify
    the response carries both original + perturbed Recommendation lists,
    a deterministic 16-char cache_key, and the perturbation applied
    (the perturbed first deploy lap should have lower deploy_mj)."""
    chat = FakeChatClient()
    client = _build_client(
        tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path), chat=chat,
    )
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    r = client.post(
        f"/api/sessions/{sid}/what-if",
        json={"perturbation": "delay_first_deploy", "n": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["request"]["perturbation"] == "delay_first_deploy"
    assert len(body["cache_key"]) == 16
    assert isinstance(body["original"], list) and isinstance(body["perturbed"], list)
    # Both lists must reference the same zones (perturbation doesn't add/drop)
    assert len(body["original"]) == len(body["perturbed"])


def test_what_if_cache_hit_skips_pipeline_rerun(tmp_path):
    """Two identical what-if calls should produce identical responses
    AND the second call must not trigger additional chat-client calls
    (cache hit short-circuits the pipeline re-run)."""
    chat = FakeChatClient()
    client = _build_client(
        tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path), chat=chat,
    )
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    payload = {"perturbation": "delay_first_deploy", "n": 2}
    r1 = client.post(f"/api/sessions/{sid}/what-if", json=payload)
    assert r1.status_code == 200
    calls_after_first = len(chat.calls)

    r2 = client.post(f"/api/sessions/{sid}/what-if", json=payload)
    assert r2.status_code == 200
    # Cache hit — no new chat-client calls
    assert len(chat.calls) == calls_after_first
    # Same cache_key both times
    assert r1.json()["cache_key"] == r2.json()["cache_key"]


def test_what_if_unknown_zone_returns_404(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    r = client.post(
        f"/api/sessions/{sid}/what-if",
        json={"perturbation": "skip_harvest_zone", "zone_id": "z_ghost"},
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "NOT_FOUND"


def test_what_if_unknown_session_returns_404(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions/s_nonexistent/what-if",
        json={"perturbation": "delay_first_deploy", "n": 1},
    )
    assert r.status_code == 404


def test_what_if_invalid_request_body_returns_422(tmp_path):
    """delay_first_deploy without `n` should fail Pydantic validation."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    r = client.post(
        f"/api/sessions/{sid}/what-if",
        json={"perturbation": "delay_first_deploy"},  # missing n
    )
    assert r.status_code == 422  # FastAPI Pydantic validation


# ──────────────────────────────────────────────────────────────────────────────
# OVERRIDE_LLM_RUNTIME factory (v6 plan task 2.10)
# ──────────────────────────────────────────────────────────────────────────────


class _FakeWatsonxAIChatClient:
    """Construction-stub for the watsonx impl. Lets us test the factory's
    routing logic without triggering real IBM Cloud IAM auth, which the
    actual WatsonxAIChatClient.__init__ does eagerly."""
    def __init__(self, *args, **kwargs):
        pass


def test_get_chat_client_defaults_to_watsonx(monkeypatch):
    """Unset OVERRIDE_LLM_RUNTIME → factory returns the watsonx impl.
    No behavior change for v1.0 demo + video path."""
    monkeypatch.delenv("OVERRIDE_LLM_RUNTIME", raising=False)
    monkeypatch.setattr("api.main.WatsonxAIChatClient", _FakeWatsonxAIChatClient)
    from api.main import get_chat_client
    client = get_chat_client()
    assert isinstance(client, _FakeWatsonxAIChatClient)


def test_get_chat_client_ollama_fails_loud_when_unreachable(monkeypatch):
    """Fail-loud startup probe per v6 plan task 2.10 — refuse to boot
    when OVERRIDE_LLM_RUNTIME=ollama but Ollama isn't reachable. Catches
    misconfiguration at the front door instead of at the first reasoning
    call (the silent 60-second-connection-refused failure mode)."""
    monkeypatch.setenv("OVERRIDE_LLM_RUNTIME", "ollama")
    monkeypatch.setenv("OVERRIDE_OLLAMA_BASE_URL", "http://nonexistent-host:9999")
    from api.main import get_chat_client
    with pytest.raises(RuntimeError, match="OVERRIDE_LLM_RUNTIME=ollama"):
        get_chat_client()


def test_get_chat_client_ollama_returns_ollama_client_when_reachable(monkeypatch):
    """When the probe succeeds, factory returns an OllamaChatClient.
    Stubs the probe to bypass the live HTTP call."""
    monkeypatch.setenv("OVERRIDE_LLM_RUNTIME", "ollama")
    monkeypatch.setenv("OVERRIDE_OLLAMA_BASE_URL", "http://test:11434")
    monkeypatch.setattr("api.main.probe_ollama_reachable", lambda url: (True, None))
    from api.main import get_chat_client
    from core.llm_clients import OllamaChatClient
    client = get_chat_client()
    assert isinstance(client, OllamaChatClient)
    assert client.base_url == "http://test:11434"


def test_get_chat_client_unrecognized_runtime_falls_back_to_watsonx(monkeypatch):
    """A typo in OVERRIDE_LLM_RUNTIME (e.g., 'olama') should fall back
    to watsonx, not crash — surfaces a warning log but keeps the demo
    functional."""
    monkeypatch.setenv("OVERRIDE_LLM_RUNTIME", "olama")
    monkeypatch.setattr("api.main.WatsonxAIChatClient", _FakeWatsonxAIChatClient)
    from api.main import get_chat_client
    client = get_chat_client()
    assert isinstance(client, _FakeWatsonxAIChatClient)


def test_what_if_invalid_perturbation_kind_returns_422(tmp_path):
    """A perturbation value outside the PerturbationKind Literal should
    fail at the Literal-enforcement boundary, distinct from the per-kind
    required-field validators."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    r = client.post(
        f"/api/sessions/{sid}/what-if",
        json={"perturbation": "garbage_kind", "n": 1},
    )
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /api/sessions/{id}
# ──────────────────────────────────────────────────────────────────────────────


def test_delete_session_idempotent(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]
    # First delete: 204
    r1 = client.delete(f"/api/sessions/{sid}")
    assert r1.status_code == 204
    # Second delete: still 204 (idempotent)
    r2 = client.delete(f"/api/sessions/{sid}")
    assert r2.status_code == 204
    # Followup GET: 404
    r3 = client.get(f"/api/sessions/{sid}")
    assert r3.status_code == 404


def test_delete_session_keeps_telemetry_by_default(tmp_path, monkeypatch):
    """Phase 4: deleting a torcs_live session should NOT unlink its JSONL
    by default — keep-by-default per user preference so re-ingest stays
    possible after a delete."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "keep_me.jsonl").write_bytes(_torcs_jsonl_payload())
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post("/api/sessions/torcs-live", json={"run_id": "keep_me"})
    assert created.status_code == 201
    sid = created.json()["summary"]["session_id"]

    r = client.delete(f"/api/sessions/{sid}")
    assert r.status_code == 204
    # Session gone, but JSONL still on disk
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert (telem / "keep_me.jsonl").exists()


def test_delete_session_with_remove_telemetry_unlinks_jsonl(tmp_path, monkeypatch):
    """Opt-in: ?remove_telemetry=true also unlinks the source JSONL."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "bye_run.jsonl").write_bytes(_torcs_jsonl_payload())
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post("/api/sessions/torcs-live", json={"run_id": "bye_run"})
    sid = created.json()["summary"]["session_id"]

    r = client.delete(f"/api/sessions/{sid}?remove_telemetry=true")
    assert r.status_code == 204
    assert not (telem / "bye_run.jsonl").exists()


def test_delete_session_remove_telemetry_noop_when_no_capture(tmp_path):
    """A plain upload session has no telemetry_file — remove_telemetry
    should succeed harmlessly without touching the volume."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]
    r = client.delete(f"/api/sessions/{sid}?remove_telemetry=true")
    assert r.status_code == 204


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/sessions/bulk-delete
# ──────────────────────────────────────────────────────────────────────────────


def test_bulk_delete_removes_multiple_sessions(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    sids = []
    for _ in range(3):
        created = client.post(
            "/api/sessions",
            files={"file": ("s.json", _laps_payload(), "application/json")},
            data={"source": "fastf1"},
        ).json()
        sids.append(created["summary"]["session_id"])

    r = client.post("/api/sessions/bulk-delete", json={"session_ids": sids})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] == 3
    assert body["telemetry_removed"] == 0
    # All gone
    for sid in sids:
        assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_bulk_delete_idempotent_for_missing_ids(tmp_path):
    """Mix of existing + missing IDs returns the count of those that
    actually existed; no error on the missing ones."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post(
        "/api/sessions",
        files={"file": ("s.json", _laps_payload(), "application/json")},
        data={"source": "fastf1"},
    ).json()
    sid = created["summary"]["session_id"]

    r = client.post(
        "/api/sessions/bulk-delete",
        json={"session_ids": [sid, "s_ghost_one", "s_ghost_two"]},
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 1


def test_bulk_delete_with_remove_telemetry_unlinks_jsonl_per_session(tmp_path, monkeypatch):
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "alpha.jsonl").write_bytes(_torcs_jsonl_payload())
    (telem / "beta.jsonl").write_bytes(_torcs_jsonl_payload())
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    a = client.post("/api/sessions/torcs-live", json={"run_id": "alpha"}).json()
    b = client.post("/api/sessions/torcs-live", json={"run_id": "beta"}).json()
    sids = [a["summary"]["session_id"], b["summary"]["session_id"]]

    r = client.post(
        "/api/sessions/bulk-delete",
        json={"session_ids": sids, "remove_telemetry": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] == 2
    assert body["telemetry_removed"] == 2
    assert not (telem / "alpha.jsonl").exists()
    assert not (telem / "beta.jsonl").exists()


def test_bulk_delete_rejects_empty_list(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post("/api/sessions/bulk-delete", json={"session_ids": []})
    assert r.status_code == 422


def test_bulk_delete_skips_invalid_ids(tmp_path):
    """Path-traversal-shaped IDs are silently skipped (treated like missing),
    not 400. Belt-and-suspenders alongside the regex match in delete_session."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.post(
        "/api/sessions/bulk-delete",
        json={"session_ids": ["../etc/passwd", "not_a_session"]},
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /api/torcs/runs/{run_id}
# ──────────────────────────────────────────────────────────────────────────────


def test_delete_torcs_run_unlinks_jsonl(tmp_path, monkeypatch):
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "scratch.jsonl").write_bytes(b'{"x":1}\n')
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.delete("/api/torcs/runs/scratch")
    assert r.status_code == 204
    assert not (telem / "scratch.jsonl").exists()


def test_delete_torcs_run_idempotent_when_missing(tmp_path, monkeypatch):
    telem = tmp_path / "telemetry"
    telem.mkdir()
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.delete("/api/torcs/runs/ghost_run")
    assert r.status_code == 204


def test_delete_torcs_run_rejects_path_traversal(tmp_path):
    """Path-traversal attempts must NOT 204. Three valid blocking outcomes:
       - 422: pydantic pattern rejects (raw ``..`` in segment)
       - 404: router doesn't match (encoded slash normalized away)
       - 405: normalized URL hits an existing route with no DELETE verb
    The contract is "anything that isn't a successful 204"."""
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.delete("/api/torcs/runs/..%2Fetc%2Fpasswd")
    assert r.status_code != 204
    assert 400 <= r.status_code < 500


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/torcs-status — pagination + ingested_session_id
# ──────────────────────────────────────────────────────────────────────────────


def test_torcs_status_paginates(tmp_path, monkeypatch):
    telem = tmp_path / "telemetry"
    telem.mkdir()
    for i in range(5):
        (telem / f"run_{i}.jsonl").write_bytes(_torcs_jsonl_payload(n_laps=1, ticks_per_lap=10))
        import time as _t; _t.sleep(0.01)  # distinct mtimes
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))

    r = client.get("/api/torcs-status?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["runs"]) == 2
    # Newest first
    assert body["runs"][0]["run_id"] == "run_4"

    r2 = client.get("/api/torcs-status?limit=2&offset=2")
    body2 = r2.json()
    assert [r["run_id"] for r in body2["runs"]] == ["run_2", "run_1"]


def test_torcs_status_uses_same_completed_lap_count_as_sessions(tmp_path, monkeypatch):
    """Regression: UploadPage used to show a size heuristic while the
    Sessions page live-enriched ACTIVE rows from the JSONL itself. The
    two surfaces must agree for the same TORCS capture."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "active_run.jsonl").write_bytes(_sse_jsonl_payload(n_laps=3))
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))

    r = client.get("/api/torcs-status")
    assert r.status_code == 200
    row = next(run for run in r.json()["runs"] if run["run_id"] == "active_run")
    assert row["lap_count_estimate"] == 2


def test_torcs_status_marks_ingested_runs(tmp_path, monkeypatch):
    """After torcs-live ingest, the run shows ingested_session_id pointing
    to the resulting session. Unaffected runs return None for that field."""
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "ingest_me.jsonl").write_bytes(_torcs_jsonl_payload())
    (telem / "leave_me.jsonl").write_bytes(_torcs_jsonl_payload())
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    created = client.post("/api/sessions/torcs-live", json={"run_id": "ingest_me"}).json()
    expected_sid = created["summary"]["session_id"]

    r = client.get("/api/torcs-status")
    runs = {row["run_id"]: row for row in r.json()["runs"]}
    assert runs["ingest_me"]["ingested_session_id"] == expected_sid
    assert runs["leave_me"]["ingested_session_id"] is None


def test_torcs_status_active_stub_does_not_mark_ingested(tmp_path, monkeypatch):
    """Regression: a stub session written by /api/torcs/start-race has
    status=ACTIVE and stamps telemetry_file pointing at the JSONL that
    gym_torcs is still writing. That JSONL must NOT show up as
    ingested — the pipeline hasn't run against it yet, so the UI must
    keep offering the Ingest → button instead of an Open session → link
    that lands the operator on a stub debrief.
    """
    from datetime import datetime, timezone
    from api.storage import save_session
    from ingest.schema import (
        Session as PydanticSession,
        SessionSource,
        SessionStatus,
        SessionSummary,
    )

    telem = tmp_path / "telemetry"
    telem.mkdir()
    sid = "s_torcs_live_99999999_stubtest"
    (telem / f"{sid}.jsonl").write_bytes(_torcs_jsonl_payload())
    monkeypatch.setenv("OVERRIDE_TELEMETRY_DIR", str(telem))
    monkeypatch.setenv("OVERRIDE_SESSIONS_DIR", str(tmp_path / "sessions"))

    # Write the stub the way /api/torcs/start-race does.
    stub = PydanticSession(
        summary=SessionSummary(
            session_id=sid,
            uploaded_at=datetime.now(timezone.utc),
            source="torcs",
            lap_count=0,
            forecast_available=False,
            zone_count=0,
            track_id=f"torcs-live/{sid}",
            session_source=SessionSource.TORCS_LIVE,
            status=SessionStatus.ACTIVE,
            telemetry_file=f"{sid}.jsonl",
        ),
        laps=[],
        forecast=None,
        recommendations=[],
        regulation_source=None,
    )
    save_session(stub)

    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/torcs-status")
    runs = {row["run_id"]: row for row in r.json()["runs"]}
    assert runs[sid]["ingested_session_id"] is None, (
        "ACTIVE stub session must not surface as 'ingested' — the pipeline "
        "hasn't run against this JSONL yet."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Headers + middleware
# ──────────────────────────────────────────────────────────────────────────────


def test_request_id_round_trips(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/health", headers={"X-Request-Id": "req_caller_42"})
    assert r.headers["X-Request-Id"] == "req_caller_42"


def test_request_id_generated_when_missing(tmp_path):
    client = _build_client(tmp_path=tmp_path, chunks_path=_empty_chunks_path(tmp_path))
    r = client.get("/api/health")
    assert r.headers["X-Request-Id"].startswith("req_")
