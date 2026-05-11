"""Local-disk persistence for sessions per `docs/04-api.md §7`.

Layout under `data/sessions/`:
  data/sessions/_index.json                 — `[SessionSummary, ...]`
  data/sessions/{session_id}/summary.json   — `SessionSummary`
  data/sessions/{session_id}/laps.parquet   — `LapFeatures` rows
  data/sessions/{session_id}/forecast.json  — `Forecast` (optional)
  data/sessions/{session_id}/recommendations.json — list[Recommendation]
  data/sessions/{session_id}/regulation_source.json — RegulationSource (optional)

No DB. Sessions are keyed by their `session_id` slug. Original uploaded
files are NOT retained after parsing — only derived artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

from ingest.schema import (
    Forecast,
    LapFeatures,
    Recommendation,
    RegulationSource,
    Session,
    SessionSummary,
)

logger = logging.getLogger(__name__)


def _sessions_root() -> Path:
    """Resolve the sessions storage directory. Honors `SESSIONS_DIR` env."""
    raw = os.environ.get("SESSIONS_DIR")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent / "data" / "sessions"


# ──────────────────────────────────────────────────────────────────────────────
# Session writes
# ──────────────────────────────────────────────────────────────────────────────


def save_session(session: Session, *, root: Optional[Path] = None) -> Path:
    """Persist a complete `Session` to disk and update the index."""
    base = (root or _sessions_root()) / session.summary.session_id
    base.mkdir(parents=True, exist_ok=True)

    (base / "summary.json").write_text(
        json.dumps(session.summary.model_dump(mode="json"), indent=2)
    )

    # Laps as parquet (smaller + faster to read for chart endpoints)
    if session.laps:
        df = pd.DataFrame([L.model_dump(mode="json") for L in session.laps])
        df.to_parquet(base / "laps.parquet", index=False)

    if session.forecast is not None:
        (base / "forecast.json").write_text(
            json.dumps(session.forecast.model_dump(mode="json"), indent=2)
        )

    (base / "recommendations.json").write_text(
        json.dumps(
            [r.model_dump(mode="json") for r in session.recommendations],
            indent=2,
        )
    )

    if session.regulation_source is not None:
        (base / "regulation_source.json").write_text(
            json.dumps(session.regulation_source.model_dump(mode="json"), indent=2)
        )

    _update_index(session.summary, root=root)
    logger.info("save_session: wrote %s → %s", session.summary.session_id, base)
    return base


def save_recommendations_only(
    session_id: str,
    recommendations: list[Recommendation],
    *,
    root: Optional[Path] = None,
) -> Path:
    """Atomically rewrite *only* ``recommendations.json`` for a session.

    Used by the lazy fan-mode write-back path in ``api/main.py``. Writes to a
    sibling tempfile in the same directory then ``os.replace`` so concurrent
    readers either see the old recommendations or the new ones, never a
    partial file. Index, summary, laps, forecast, and regulation_source are
    not touched — those are session-creation invariants.

    The caller is responsible for serializing read-modify-write cycles per
    session via an ``asyncio.Lock`` to avoid the lost-update race where two
    concurrent fan-mode requests on different zones each compute against a
    stale snapshot and clobber each other on the way back.
    """
    base = (root or _sessions_root()) / session_id
    if not base.exists():
        raise FileNotFoundError(f"session {session_id!r} does not exist at {base}")
    target = base / "recommendations.json"
    # mkstemp on the same dir guarantees same filesystem → os.replace is atomic.
    fd, tmp_path = tempfile.mkstemp(prefix=".recs-", suffix=".json.tmp", dir=base)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(
                [r.model_dump(mode="json") for r in recommendations],
                f,
                indent=2,
            )
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise
    logger.debug("save_recommendations_only: wrote %s (%d recs)", target, len(recommendations))
    return target


# ──────────────────────────────────────────────────────────────────────────────
# Session reads
# ──────────────────────────────────────────────────────────────────────────────


def load_session(session_id: str, *, root: Optional[Path] = None) -> Optional[Session]:
    """Reconstruct a `Session` from disk; return None when not found."""
    base = (root or _sessions_root()) / session_id
    summary_path = base / "summary.json"
    if not summary_path.exists():
        return None

    summary = SessionSummary.model_validate_json(summary_path.read_text())

    laps_path = base / "laps.parquet"
    laps: list[LapFeatures] = []
    if laps_path.exists():
        df = pd.read_parquet(laps_path)
        laps = [LapFeatures.model_validate(row) for row in df.to_dict(orient="records")]

    forecast: Optional[Forecast] = None
    if (base / "forecast.json").exists():
        forecast = Forecast.model_validate_json((base / "forecast.json").read_text())

    recs_path = base / "recommendations.json"
    recommendations: list[Recommendation] = []
    if recs_path.exists():
        recommendations = [
            Recommendation.model_validate(obj)
            for obj in json.loads(recs_path.read_text())
        ]

    regulation_source: Optional[RegulationSource] = None
    rs_path = base / "regulation_source.json"
    if rs_path.exists():
        regulation_source = RegulationSource.model_validate_json(rs_path.read_text())

    return Session(
        summary=summary,
        laps=laps,
        forecast=forecast,
        recommendations=recommendations,
        regulation_source=regulation_source,
    )


def delete_session(session_id: str, *, root: Optional[Path] = None) -> bool:
    """Remove a session's directory and its index entry. Idempotent."""
    base = (root or _sessions_root()) / session_id
    existed = base.exists()
    if existed:
        shutil.rmtree(base)
    _remove_from_index(session_id, root=root)
    return existed


# ──────────────────────────────────────────────────────────────────────────────
# Index — single JSON file with the per-session summaries
# ──────────────────────────────────────────────────────────────────────────────


def _index_path(*, root: Optional[Path] = None) -> Path:
    return (root or _sessions_root()) / "_index.json"


def _read_index(*, root: Optional[Path] = None) -> list[dict]:
    p = _index_path(root=root)
    if not p.exists():
        return []
    return json.loads(p.read_text())


def _write_index(entries: list[dict], *, root: Optional[Path] = None) -> None:
    p = _index_path(root=root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, indent=2))


def _update_index(summary: SessionSummary, *, root: Optional[Path] = None) -> None:
    entries = [e for e in _read_index(root=root) if e.get("session_id") != summary.session_id]
    entries.append(summary.model_dump(mode="json"))
    # Sort newest first by uploaded_at
    entries.sort(key=lambda e: e.get("uploaded_at", ""), reverse=True)
    _write_index(entries, root=root)


def _remove_from_index(session_id: str, *, root: Optional[Path] = None) -> None:
    entries = [e for e in _read_index(root=root) if e.get("session_id") != session_id]
    _write_index(entries, root=root)


def list_sessions(
    *,
    limit: int = 20,
    offset: int = 0,
    root: Optional[Path] = None,
) -> tuple[list[SessionSummary], int]:
    """Return (page, total). Newest first."""
    entries = _read_index(root=root)
    total = len(entries)
    page = entries[offset : offset + limit]
    return [SessionSummary.model_validate(e) for e in page], total


__all__ = [
    "save_session",
    "save_recommendations_only",
    "load_session",
    "delete_session",
    "list_sessions",
]
