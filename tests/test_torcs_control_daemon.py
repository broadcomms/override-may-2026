from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("TORCS_CONTROL_SECRET", "test-secret")

import RaceYourCode.gym_torcs.control_daemon as daemon
from RaceYourCode.gym_torcs.driver_config_contract import DEFAULT_DRIVER_CONFIG


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-secret"}


def test_write_practice_config_patches_track_laps_and_scr_server(tmp_path, monkeypatch):
    template = tmp_path / "practice.xml"
    template.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE params SYSTEM "params.dtd">
<params name="Practice">
  <section name="Tracks">
    <section name="1">
      <attstr name="name" val="michigan"/>
      <attstr name="category" val="oval"/>
    </section>
  </section>
  <section name="Practice">
    <attnum name="laps" val="20"/>
    <attstr name="display mode" val="results only"/>
    <attnum name="distance" unit="km" val="12"/>
  </section>
  <section name="Drivers">
    <attnum name="maximum number" val="4"/>
    <attstr name="focused module" val="inferno"/>
    <attnum name="focused idx" val="3"/>
    <section name="1">
      <attnum name="idx" val="2"/>
      <attstr name="module" val="inferno"/>
    </section>
  </section>
</params>
"""
    )
    monkeypatch.setattr(daemon, "TORCS_STOCK_PRACTICE", str(template))
    monkeypatch.setattr(daemon, "PRACTICE_TEMPLATE_FALLBACK", str(template))
    monkeypatch.setattr(daemon, "TORCS_RACEMAN_DIR", str(tmp_path / "raceman"))
    monkeypatch.setattr(daemon, "TORCS_USER_HOME", str(tmp_path))
    monkeypatch.setattr(daemon, "_TRACK_CATEGORY_CACHE", {"aalborg": "road"})

    out = Path(daemon._write_practice_config("aalborg", 75))
    text = out.read_text()
    assert 'name="name" val="aalborg"' in text
    assert 'name="category" val="road"' in text
    assert 'name="laps" val="75"' in text
    assert 'name="display mode" val="normal"' in text
    assert 'name="focused module" val="scr_server"' in text
    assert 'name="module" val="scr_server"' in text


def test_load_track_metadata_reads_attrs_and_assets(tmp_path, monkeypatch):
    base = tmp_path / "tracks" / "road" / "aalborg"
    base.mkdir(parents=True)
    (base / "aalborg.xml").write_text(
        """
<params name="Track">
  <section name="Header">
    <attstr name="name" val="Aalborg"/>
    <attstr name="description" val="Fast road circuit"/>
    <attstr name="author" val="Track Team"/>
    <attnum name="length" unit="m" val="3200.5"/>
    <attnum name="width" unit="m" val="12.0"/>
    <attnum name="pits" val="16"/>
  </section>
</params>
"""
    )
    (base / "background.png").write_bytes(b"preview")
    (base / "raceline.png").write_bytes(b"map")

    monkeypatch.setattr(daemon, "TORCS_TRACKS_DIR", str(tmp_path / "tracks"))
    daemon._TRACK_CATEGORY_CACHE.clear()
    daemon._TRACK_METADATA_CACHE = None

    tracks = daemon._load_track_metadata()
    assert len(tracks) == 1
    track = tracks[0]
    assert track.name == "aalborg"
    assert track.category == "road"
    assert track.display_name == "Aalborg"
    assert track.description == "Fast road circuit"
    assert track.author == "Track Team"
    assert track.length_m == 3200.5
    assert track.width_m == 12.0
    assert track.pits == 16
    assert track.has_preview_asset is True
    assert track.has_map_asset is True


def test_control_recover_resets_active_state(monkeypatch):
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")
    calls: list[str] = []

    async def fake_terminate_proc(_proc, label):
        return 0 if label == "scr-client" else -9

    async def fake_wait_for_torcs_gui(timeout_s=daemon.GUI_READY_TIMEOUT_S):
        return True

    monkeypatch.setattr(daemon, "_terminate_proc", fake_terminate_proc)
    monkeypatch.setattr(daemon, "_resume_kiosk_loop", lambda: calls.append("resume"))
    monkeypatch.setattr(daemon, "_restart_torcs_kiosk_surface", lambda: calls.append("restart"))
    monkeypatch.setattr(daemon, "_ensure_xfwm4", lambda: None)
    monkeypatch.setattr(daemon, "_wait_for_torcs_gui", fake_wait_for_torcs_gui)
    daemon._race = daemon.ActiveRace(
        session_id="s_torcs_live_42",
        state=daemon.RaceState.ACTIVE,
        track="aalborg",
        laps=75,
        launch_mode="cockpit_practice",
    )

    client = TestClient(daemon.app)
    r = client.post("/control/recover", headers=_auth_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "recovered"
    assert body["session_id"] == "s_torcs_live_42"
    assert body["state"] == "idle"
    assert calls == ["resume", "restart"]
    assert daemon._race.state == daemon.RaceState.IDLE
    assert daemon._race.session_id == ""


def test_control_start_cockpit_practice_uses_visible_gui_bridge(monkeypatch):
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    class FakeProc:
        def __init__(self, pid: int):
            self.pid = pid

        def poll(self):
            return None

    async def fake_wait_for_scr_port(proc=None, timeout_s=daemon.LAUNCH_TIMEOUT_S):
        assert proc is None
        return True

    launch_calls: list[tuple[str, int]] = []
    scr_proc = FakeProc(222)

    async def fake_launch_visible_practice(track, laps):
        launch_calls.append((track, laps))

    monkeypatch.setattr(daemon, "_launch_visible_practice", fake_launch_visible_practice)
    monkeypatch.setattr(daemon, "_wait_for_scr_port", fake_wait_for_scr_port)
    monkeypatch.setattr(
        daemon,
        "_launch_scr_client",
        lambda session_id, track, laps, telemetry_filename, driver_config_path: scr_proc,
    )
    daemon._race = daemon._fresh_idle_race()

    client = TestClient(daemon.app)
    r = client.post(
        "/control/start",
        headers=_auth_headers(),
        json={
            "session_id": "s_torcs_live_99",
            "track": "aalborg",
            "laps": 75,
            "launch_mode": "cockpit_practice",
        },
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["launch_mode"] == "cockpit_practice"
    assert body["torcs_pid"] is None
    assert body["pid"] == 222
    assert launch_calls == [("aalborg", 75)]
    assert daemon._race.state == daemon.RaceState.ACTIVE
    assert daemon._race.torcs_proc is None
    assert daemon._race.scr_proc is scr_proc


def test_control_stop_cockpit_practice_keeps_simulator_closed(monkeypatch):
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")
    calls: list[str] = []

    async def fake_terminate_proc(_proc, label):
        calls.append(f"terminate:{label}")
        return 0 if label == "scr-client" else None

    monkeypatch.setattr(daemon, "_terminate_proc", fake_terminate_proc)
    monkeypatch.setattr(daemon, "_kill_managed_torcs_for_mode", lambda launch_mode: None)
    monkeypatch.setattr(daemon, "_pause_kiosk_loop", lambda: calls.append("pause"))
    monkeypatch.setattr(daemon, "_kill_stale_torcs", lambda: calls.append("close-gui"))
    monkeypatch.setattr(daemon, "_resume_kiosk_loop", lambda: calls.append("resume"))

    daemon._race = daemon.ActiveRace(
        session_id="s_torcs_live_stop_42",
        state=daemon.RaceState.ACTIVE,
        track="aalborg",
        laps=75,
        launch_mode="cockpit_practice",
    )

    client = TestClient(daemon.app)
    r = client.post("/control/stop", headers=_auth_headers())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "stopped"
    assert body["session_id"] == "s_torcs_live_stop_42"
    assert daemon._race.state == daemon.RaceState.IDLE
    assert daemon._race.scr_proc is None
    assert daemon._race.torcs_proc is None
    assert calls == ["terminate:scr-client", "pause", "terminate:torcs", "close-gui"]


def test_control_status_graceful_finish_keeps_simulator_closed(monkeypatch):
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")
    calls: list[str] = []

    class DeadProc:
        pid = 222
        returncode = 0

        def poll(self):
            return 0

    async def fake_terminate_proc(_proc, label):
        calls.append(f"terminate:{label}")
        return None

    monkeypatch.setattr(daemon, "_terminate_proc", fake_terminate_proc)
    monkeypatch.setattr(daemon, "_kill_managed_torcs_for_mode", lambda launch_mode: None)
    monkeypatch.setattr(daemon, "_pause_kiosk_loop", lambda: calls.append("pause"))
    monkeypatch.setattr(daemon, "_kill_stale_torcs", lambda: calls.append("close-gui"))
    monkeypatch.setattr(daemon, "_resume_kiosk_loop", lambda: calls.append("resume"))

    daemon._race = daemon.ActiveRace(
        session_id="s_torcs_live_finish_42",
        state=daemon.RaceState.ACTIVE,
        track="aalborg",
        laps=75,
        launch_mode="cockpit_practice",
    )
    daemon._race.scr_proc = DeadProc()

    client = TestClient(daemon.app)
    r = client.get("/control/status", headers=_auth_headers())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "cleanup"
    assert body["last_error"] is None
    assert daemon._race.state == daemon.RaceState.CLEANUP


def test_control_start_materializes_driver_config_and_passes_path(monkeypatch, tmp_path):
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")
    monkeypatch.setattr(daemon, "DRIVER_CONFIG_DIR", str(tmp_path / "driver-configs"))

    class FakeProc:
        def __init__(self, pid: int):
            self.pid = pid

        def poll(self):
            return None

    async def fake_wait_for_visible_practice_scr(timeout_s=daemon.LAUNCH_TIMEOUT_S):
        return True

    async def fake_launch_visible_practice(track, laps):
        return None

    captured: dict[str, str | None] = {}
    scr_proc = FakeProc(333)

    monkeypatch.setattr(daemon, "_launch_visible_practice", fake_launch_visible_practice)
    monkeypatch.setattr(daemon, "_wait_for_visible_practice_scr", fake_wait_for_visible_practice_scr)

    def fake_launch_scr_client(session_id, track, laps, telemetry_filename, driver_config_path):
        captured["path"] = driver_config_path
        return scr_proc

    monkeypatch.setattr(
        daemon,
        "_launch_scr_client",
        fake_launch_scr_client,
    )
    daemon._race = daemon._fresh_idle_race()

    client = TestClient(daemon.app)
    r = client.post(
        "/control/start",
        headers=_auth_headers(),
        json={
            "session_id": "s_torcs_live_cfg_99",
            "track": "aalborg",
            "laps": 75,
            "launch_mode": "cockpit_practice",
            "driver_config": DEFAULT_DRIVER_CONFIG.model_dump(mode="json"),
        },
    )

    assert r.status_code == 201, r.text
    assert captured["path"] is not None
    path = Path(str(captured["path"]))
    assert path.is_file()
    payload = json.loads(path.read_text())
    assert payload["speed"]["target_speed_kmh"] == 85.0
    assert daemon._race.state == daemon.RaceState.ACTIVE
    assert daemon._race.scr_proc is scr_proc
    assert daemon._race.torcs_proc is None


def test_visible_practice_xdotool_moves_window_to_origin_before_keys(monkeypatch):
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd, capture_output, text, env, timeout):
        del capture_output, text, timeout
        assert env["DISPLAY"] == daemon.TORCS_DISPLAY
        calls.append(cmd)
        if cmd[:3] == ["xdotool", "search", "--name"]:
            return Result(stdout="25165826\n")
        if cmd[:2] == ["xdotool", "windowfocus"]:
            return Result()
        if cmd[:2] == ["xdotool", "windowmove"]:
            return Result()
        if cmd[:2] == ["xdotool", "key"]:
            return Result()
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(daemon.subprocess, "run", fake_run)

    ok = daemon._send_visible_practice_launch_sequence_xdotool()

    assert ok is True
    assert ["xdotool", "windowmove", "25165826", "0", "0"] in calls
    assert calls.index(["xdotool", "windowfocus", "25165826"]) < calls.index(
        ["xdotool", "windowmove", "25165826", "0", "0"]
    )
    assert calls.index(["xdotool", "windowmove", "25165826", "0", "0"]) < calls.index(
        ["xdotool", "key", "Return"]
    )


def test_visible_practice_xte_uses_upstream_keyboard_sequence(monkeypatch):
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text, env, timeout):
        del capture_output, text, timeout
        assert env["DISPLAY"] == daemon.TORCS_DISPLAY
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(daemon.subprocess, "run", fake_run)

    daemon._send_visible_practice_launch_sequence_xte()

    assert calls == [
        [
            "xte",
            "-x",
            daemon.TORCS_DISPLAY,
            "key Return",
            "usleep 300000",
            "key Return",
            "usleep 300000",
            "key Up",
            "usleep 300000",
            "key Up",
            "usleep 300000",
            "key Return",
            "usleep 300000",
            "key Return",
        ]
    ]


def test_control_status_keeps_active_when_wrapper_dies_but_managed_torcs_bin_lives(monkeypatch):
    monkeypatch.setenv("TORCS_CONTROL_SECRET", "test-secret")

    class DeadProc:
        pid = 111
        returncode = 0

        def poll(self):
            return 0

    class LiveProc:
        pid = 222

        def poll(self):
            return None

    resume_calls: list[str] = []
    monkeypatch.setattr(daemon, "_managed_torcs_bin_running", lambda launch_mode: True)
    monkeypatch.setattr(daemon, "_resume_kiosk_loop", lambda: resume_calls.append("resume"))

    daemon._race = daemon.ActiveRace(
        session_id="s_torcs_live_keepalive",
        state=daemon.RaceState.ACTIVE,
        track="aalborg",
        laps=75,
        launch_mode="headless_quickrace",
    )
    daemon._race.torcs_proc = DeadProc()
    daemon._race.scr_proc = LiveProc()

    client = TestClient(daemon.app)
    r = client.get("/control/status", headers=_auth_headers())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "active"
    assert body["active"] is True
    assert daemon._race.state == daemon.RaceState.ACTIVE
    assert resume_calls == []
