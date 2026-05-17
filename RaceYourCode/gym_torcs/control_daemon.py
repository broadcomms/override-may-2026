"""HTTP control daemon for the TORCS container.

Phases 2 + 2.5 of `docs/roadmap-v1.1/interactive-torcs-integration.md` —
the daemon owns gym_torcs's subprocess lifecycle AND (when ``auto_launch_torcs``
is true, default) owns TORCS itself. One click in OVERRIDE → quickrace.xml
write → TORCS spawned → SCR port poll → gym_torcs spawned → race active.

**Security posture** (see ADR-004):
- Bound to 0.0.0.0:7000 inside the container; compose does NOT expose port
  7000 to the host. Only reachable from override over the override-net bridge.
- Shared-secret bearer auth via ``TORCS_CONTROL_SECRET``; constant-time
  comparison with ``secrets.compare_digest``.
- Single-active-race invariant: one ``asyncio.Lock`` wraps the entire TOCTOU
  window in /control/start so concurrent requests cannot start two races.
- Two-subprocess lifecycle: stop order is SCR client first (graceful flush),
  THEN torcs. Reversed order drops trailing telemetry.
- Daemon SIGTERM/SIGINT handler reaps both subprocesses before exit.

This module deliberately stays self-contained — no imports from OVERRIDE's
``core/`` or ``ingest/``. The torcs container's Python environment is the
SkillsBuild lab image plus pip-installed fastapi + uvicorn at compose-startup.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("torcs.control_daemon")

# ──────────────────────────────────────────────────────────────────────────────
# Auth (constant-time compare; never reverts to ==)
# ──────────────────────────────────────────────────────────────────────────────

CONTROL_SECRET = os.environ.get("TORCS_CONTROL_SECRET", "")
if not CONTROL_SECRET:
    raise RuntimeError(
        "TORCS_CONTROL_SECRET is empty. Refusing to start the control "
        "daemon with disabled auth. Set it in .env and re-run compose."
    )


def _verify_auth(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    token = authorization[len("Bearer ") :]
    if not secrets.compare_digest(token.encode(), CONTROL_SECRET.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


# ──────────────────────────────────────────────────────────────────────────────
# Paths + constants (probed against the running lab image 2026-05-13)
# ──────────────────────────────────────────────────────────────────────────────

GYM_TORCS_DIR = "/home/student/workspace/gym_torcs"
TELEMETRY_DIR = f"{GYM_TORCS_DIR}/telemetry/"
TORCS_SCRIPT = f"{GYM_TORCS_DIR}/torcs_jm_par.py"

# Probed: torcs binary at /usr/local/torcs/bin/torcs (NOT /usr/local/bin).
TORCS_BIN = os.environ.get("OVERRIDE_TORCS_BIN", "/usr/local/torcs/bin/torcs")
# Compose runs the torcs container as root (`user: "0:0"`), and both the
# kiosk supervisor and the daemon launch TORCS from that root session.
# That means the live profile TORCS reads is /root/.torcs, not
# /home/student/.torcs. Keep the path overrideable for tests.
TORCS_USER_HOME = os.environ.get("OVERRIDE_TORCS_USER_HOME", "/root")
TORCS_RACEMAN_DIR = f"{TORCS_USER_HOME}/.torcs/config/raceman"
TORCS_DATA_DIR = "/usr/local/torcs/share/games/torcs"
TORCS_STOCK_QUICKRACE = f"{TORCS_DATA_DIR}/config/raceman/quickrace.xml"
TORCS_STOCK_PRACTICE = f"{TORCS_DATA_DIR}/config/raceman/practice.xml"
PRACTICE_TEMPLATE_FALLBACK = f"{GYM_TORCS_DIR}/practice.xml"
TORCS_TRACKS_DIR = f"{TORCS_DATA_DIR}/tracks"
KIOSK_PAUSE_FILE = os.environ.get("OVERRIDE_TORCS_KIOSK_PAUSE_FILE", "/tmp/override-managed-race.lock")
# Probed: noVNC desktop Xvfb on :1.
TORCS_DISPLAY = os.environ.get("OVERRIDE_TORCS_DISPLAY", ":1")
SCR_PORT = 3001  # UDP — gym_torcs scr_server protocol

# Timeouts (configurable via env for tests + dev iteration)
LAUNCH_TIMEOUT_S = float(os.environ.get("OVERRIDE_TORCS_LAUNCH_TIMEOUT_S", "20"))
SCR_PORT_POLL_INTERVAL_S = float(os.environ.get("OVERRIDE_TORCS_POLL_INTERVAL_S", "0.5"))
TERMINATE_GRACE_S = float(os.environ.get("OVERRIDE_TORCS_TERMINATE_GRACE_S", "5"))
KILL_GRACE_S = float(os.environ.get("OVERRIDE_TORCS_KILL_GRACE_S", "2"))
GUI_READY_TIMEOUT_S = float(os.environ.get("OVERRIDE_TORCS_GUI_READY_TIMEOUT_S", "20"))

# Post-stop GUI reset env vars (3D/manual-launch mode only).
# Read inside _reset_torcs_gui_after_stop() so changes take effect without
# restarting the daemon.
#   OVERRIDE_TORCS_GUI_RESET=0          disable entirely (default: enabled)
#   OVERRIDE_TORCS_GUI_SETTLE_S=1.0     seconds to wait after SCR stop
#   OVERRIDE_TORCS_GUI_RESET_KEYS       colon-separated xte key names
#                                       (default: Escape:Down:Return)


# ──────────────────────────────────────────────────────────────────────────────
# State machine
# ──────────────────────────────────────────────────────────────────────────────


class RaceState(str, Enum):
    """Daemon-side race-lifecycle state. Surfaced via /control/status.

    Transition table (from ADR-004 amendment + plan §State machine):
      idle        → launching     (control/start accepted)
      launching   → waiting_scr   (torcs Popen returned, PID alive)
      waiting_scr → connecting    (netstat shows :3001 bound within timeout)
      connecting  → active        (scr-client Popen returned, alive)
      active      → stopping      (/control/stop, or either subprocess exited)
      stopping    → cleanup       (both subprocs reaped)
      cleanup     → idle          (state cleared)

    Any other transition is illegal → forced to `cleanup` with error context.
    """
    IDLE = "idle"
    LAUNCHING = "launching"
    WAITING_SCR = "waiting_scr"
    CONNECTING = "connecting"
    ACTIVE = "active"
    STOPPING = "stopping"
    CLEANUP = "cleanup"


# Allowed transitions. Anything not in this set raises on _transition_to.
_ALLOWED_TRANSITIONS = {
    RaceState.IDLE: {RaceState.LAUNCHING},
    RaceState.LAUNCHING: {RaceState.WAITING_SCR, RaceState.CLEANUP},
    RaceState.WAITING_SCR: {RaceState.CONNECTING, RaceState.CLEANUP},
    RaceState.CONNECTING: {RaceState.ACTIVE, RaceState.STOPPING},
    RaceState.ACTIVE: {RaceState.STOPPING},
    RaceState.STOPPING: {RaceState.CLEANUP},
    RaceState.CLEANUP: {RaceState.IDLE},
}


@dataclass
class ActiveRace:
    """All state for one in-flight race. Singleton at the module level."""
    session_id: str
    state: RaceState
    torcs_proc: Optional[subprocess.Popen] = None
    scr_proc: Optional[subprocess.Popen] = None
    started_at: float = field(default_factory=time.monotonic)
    state_since: float = field(default_factory=time.monotonic)
    last_error: Optional[str] = None
    last_exit_code: Optional[int] = None
    telemetry_filename: Optional[str] = None
    track: Optional[str] = None
    laps: Optional[int] = None
    launch_mode: Optional[str] = None

    def transition_to(self, new_state: RaceState, *, error: Optional[str] = None) -> None:
        """Validated state transition. Raises ValueError on illegal moves."""
        if new_state not in _ALLOWED_TRANSITIONS.get(self.state, set()):
            raise ValueError(
                f"Illegal transition {self.state.value} → {new_state.value}"
            )
        logger.info(
            "race state: %s → %s%s",
            self.state.value, new_state.value,
            f" ({error})" if error else "",
        )
        self.state = new_state
        self.state_since = time.monotonic()
        if error:
            self.last_error = error


# Module-level singleton + lock
_control_lock = asyncio.Lock()
_race: ActiveRace = ActiveRace(session_id="", state=RaceState.IDLE)


def _is_busy() -> bool:
    """True when /control/start should 409. Anything except IDLE is busy."""
    return _race.state != RaceState.IDLE


# ──────────────────────────────────────────────────────────────────────────────
# quickrace.xml generation: surgical patch of the stock template
# ──────────────────────────────────────────────────────────────────────────────

# Map track stem → category. Populated lazily from the filesystem; fallback
# "road" covers the common case.
_TRACK_CATEGORY_CACHE: dict[str, str] = {}
_TRACK_METADATA_CACHE: Optional[list["TrackMetadata"]] = None


@dataclass(frozen=True)
class TrackMetadata:
    name: str
    category: str
    display_name: str
    author: Optional[str]
    description: Optional[str]
    length_m: Optional[float]
    width_m: Optional[float]
    pits: Optional[int]
    has_preview_asset: bool
    has_map_asset: bool


def _scan_tracks() -> dict[str, str]:
    """Walk the TORCS tracks dir once, return {track_name: category}.

    Lazy + cached. The lab image's tracks dir is read-only at runtime so
    re-scanning every request would be wasteful; new tracks would require
    a daemon restart anyway.
    """
    if _TRACK_CATEGORY_CACHE:
        return _TRACK_CATEGORY_CACHE
    base = Path(TORCS_TRACKS_DIR)
    if not base.is_dir():
        return {}
    for category_dir in base.iterdir():
        if not category_dir.is_dir():
            continue
        category = category_dir.name
        for track_dir in category_dir.iterdir():
            if track_dir.is_dir():
                _TRACK_CATEGORY_CACHE[track_dir.name] = category
    return _TRACK_CATEGORY_CACHE


def _track_dir(category: str, track: str) -> Path:
    return Path(TORCS_TRACKS_DIR) / category / track


def _track_xml_path(category: str, track: str) -> Path:
    return _track_dir(category, track) / f"{track}.xml"


def _track_asset_candidates(category: str, track: str, kind: Literal["preview", "map"]) -> list[Path]:
    track_dir = _track_dir(category, track)
    if kind == "preview":
        return [
            track_dir / "background.png",
            track_dir / f"{track}.png",
            track_dir / "preview.png",
        ]
    return [
        track_dir / "raceline.png",
        track_dir / f"{track}.png",
        track_dir / "outline.png",
    ]


def _resolve_track_asset(category: str, track: str, kind: Literal["preview", "map"]) -> Optional[Path]:
    for candidate in _track_asset_candidates(category, track, kind):
        if candidate.is_file():
            return candidate
    return None


def _extract_track_text_attr(xml_text: str, attr_name: str) -> Optional[str]:
    match = re.search(
        rf'<att(?:str|num)\s+name="{re.escape(attr_name)}"(?:\s+unit="[^"]+")?\s+val="([^"]+)"',
        xml_text,
    )
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _extract_header_name(xml_text: str) -> Optional[str]:
    match = re.search(
        r'<section\s+name="Header">.*?<attstr\s+name="name"\s+val="([^"]+)"',
        xml_text,
        re.DOTALL,
    )
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _parse_track_float(xml_text: str, attr_name: str) -> Optional[float]:
    raw = _extract_track_text_attr(xml_text, attr_name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_track_int(xml_text: str, attr_name: str) -> Optional[int]:
    raw = _extract_track_text_attr(xml_text, attr_name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _load_track_metadata() -> list[TrackMetadata]:
    global _TRACK_METADATA_CACHE
    if _TRACK_METADATA_CACHE is not None:
        return _TRACK_METADATA_CACHE

    records: list[TrackMetadata] = []
    for track_name, category in sorted(_scan_tracks().items()):
        xml_path = _track_xml_path(category, track_name)
        xml_text = ""
        if xml_path.is_file():
            try:
                xml_text = xml_path.read_text(errors="replace")
            except OSError:
                xml_text = ""

        display_name = _extract_header_name(xml_text) or track_name.replace("-", " ").title()
        records.append(
            TrackMetadata(
                name=track_name,
                category=category,
                display_name=display_name,
                author=_extract_track_text_attr(xml_text, "author"),
                description=_extract_track_text_attr(xml_text, "description"),
                length_m=_parse_track_float(xml_text, "length"),
                width_m=_parse_track_float(xml_text, "width"),
                pits=_parse_track_int(xml_text, "pits"),
                has_preview_asset=_resolve_track_asset(category, track_name, "preview") is not None,
                has_map_asset=_resolve_track_asset(category, track_name, "map") is not None,
            )
        )

    _TRACK_METADATA_CACHE = records
    return records


def _category_for_track(track: str) -> str:
    return _scan_tracks().get(track, "road")


def _practice_template_path() -> Path:
    stock = Path(TORCS_STOCK_PRACTICE)
    if stock.is_file():
        return stock
    fallback = Path(PRACTICE_TEMPLATE_FALLBACK)
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(
        f"TORCS practice.xml missing at {TORCS_STOCK_PRACTICE} and {PRACTICE_TEMPLATE_FALLBACK}"
    )


def _write_quickrace_config(track: str, laps: int) -> str:
    """Stock-template-patch approach.

    Read the lab image's stock quickrace.xml, surgically replace the track
    name + category + lap count, write to ~student/.torcs/config/raceman/.
    No XML parser needed — TORCS XML uses ``<attstr name="X" val="Y"/>``
    so regex on the val-pair is unambiguous.

    The scr_server driver section is left UNTOUCHED — it's load-bearing
    for the SCR client to connect. Stock template already has it as idx=0.
    """
    stock = Path(TORCS_STOCK_QUICKRACE)
    if not stock.is_file():
        raise FileNotFoundError(
            f"TORCS stock quickrace.xml missing at {TORCS_STOCK_QUICKRACE}; "
            "is the lab image intact?"
        )
    template = stock.read_text()
    category = _category_for_track(track)

    # Track name (in Tracks section)
    patched = re.sub(
        r'(<attstr\s+name="name"\s+val=")[^"]+("/>\s*\n\s*<attstr\s+name="category")',
        rf'\g<1>{track}\g<2>',
        template,
        count=1,
    )
    # Category (immediately follows track name)
    patched = re.sub(
        r'(<attstr\s+name="category"\s+val=")[^"]+("/>)',
        rf'\g<1>{category}\g<2>',
        patched,
        count=1,
    )
    # Lap count (in Quick Race section)
    patched = re.sub(
        r'(<attnum\s+name="laps"\s+val=")[^"]+("/>)',
        rf'\g<1>{laps}\g<2>',
        patched,
        count=1,
    )

    # Phase 2.6 fix — force GUI rendering. Without this attribute, torcs -r
    # defaults to TEXT-MODE / batch results (no 3D window in noVNC, race
    # still runs and SCR serves normally). Probed 2026-05-13: stock
    # quickrace.xml doesn't carry `display mode`, so torcs uses its `-r`
    # default of headless. Append <attstr name="display mode" val="normal"/>
    # to the Quick Race section just after the `laps` attribute.
    # Idempotent: if "display mode" already exists, replace its value;
    # otherwise inject the new attribute.
    if 'name="display mode"' in patched:
        patched = re.sub(
            r'(<attstr\s+name="display mode"\s+val=")[^"]+("/>)',
            r'\g<1>normal\g<2>',
            patched,
            count=1,
        )
    else:
        patched = re.sub(
            r'(<attnum\s+name="laps"\s+val="[^"]+"/>)',
            r'\g<1>\n    <attstr name="display mode" val="normal"/>',
            patched,
            count=1,
        )

    # Defensive: verify scr_server driver module survived the patch.
    if 'name="module" val="scr_server"' not in patched:
        raise RuntimeError(
            "quickrace.xml patch corrupted the scr_server driver entry — "
            "patched output would not bind UDP :3001. Refusing to write."
        )

    os.makedirs(TORCS_RACEMAN_DIR, exist_ok=True)
    target = f"{TORCS_RACEMAN_DIR}/quickrace.xml"
    Path(target).write_text(patched)
    subprocess.run(
        ["chown", "-R", "student:student", f"{TORCS_USER_HOME}/.torcs"],
        check=False, capture_output=True,
    )
    return target


def _write_practice_config(track: str, laps: int) -> str:
    """Patch practice.xml so OVERRIDE owns track, laps, and SCR driver.

    Practice is the only supported 3D path. We keep the XML patch narrow:
    track/category/laps plus the focused SCR driver and normal display mode.
    """
    template_path = _practice_template_path()
    tree = ET.parse(template_path)
    root = tree.getroot()
    category = _category_for_track(track)

    tracks_section = root.find("./section[@name='Tracks']/section[@name='1']")
    practice_section = root.find("./section[@name='Practice']")
    drivers_section = root.find("./section[@name='Drivers']")
    first_driver = root.find("./section[@name='Drivers']/section[@name='1']")
    drivers_start_list = root.find("./section[@name='Drivers Start List']")
    if (
        tracks_section is None
        or practice_section is None
        or drivers_section is None
        or first_driver is None
    ):
        raise RuntimeError("practice.xml is missing required Tracks/Practice/Drivers sections")
    if drivers_start_list is None:
        drivers_start_list = ET.SubElement(root, "section", {"name": "Drivers Start List"})
    start_list_first = drivers_start_list.find("./section[@name='1']")
    if start_list_first is None:
        start_list_first = ET.SubElement(drivers_start_list, "section", {"name": "1"})

    def _set_child_attr(section: ET.Element, child_name: str, value: str) -> None:
        target = section.find(f"./attstr[@name='{child_name}']")
        if target is None:
            target = ET.SubElement(section, "attstr", {"name": child_name, "val": value})
        else:
            target.set("val", value)

    def _set_child_num(section: ET.Element, child_name: str, value: int | float) -> None:
        target = section.find(f"./attnum[@name='{child_name}']")
        if target is None:
            target = ET.SubElement(section, "attnum", {"name": child_name, "val": str(value)})
        else:
            target.set("val", str(value))

    _set_child_attr(tracks_section, "name", track)
    _set_child_attr(tracks_section, "category", category)
    _set_child_num(practice_section, "laps", laps)
    _set_child_attr(practice_section, "display mode", "normal")
    _set_child_num(practice_section, "distance", 0)
    _set_child_num(drivers_section, "maximum number", 1)
    _set_child_attr(drivers_section, "focused module", "scr_server")
    _set_child_num(drivers_section, "focused idx", 1)
    _set_child_num(first_driver, "idx", 0)
    _set_child_attr(first_driver, "module", "scr_server")
    _set_child_attr(start_list_first, "module", "scr_server")
    _set_child_num(start_list_first, "idx", 0)

    patched = ET.tostring(root, encoding="unicode")
    if 'name="module" val="scr_server"' not in patched:
        raise RuntimeError("practice.xml patch lost the scr_server driver entry")

    os.makedirs(TORCS_RACEMAN_DIR, exist_ok=True)
    target = f"{TORCS_RACEMAN_DIR}/practice.xml"
    Path(target).write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE params SYSTEM "params.dtd">\n\n' + patched)
    subprocess.run(
        ["chown", "-R", "student:student", f"{TORCS_USER_HOME}/.torcs"],
        check=False,
        capture_output=True,
    )
    return target


# ──────────────────────────────────────────────────────────────────────────────
# Process management
# ──────────────────────────────────────────────────────────────────────────────


def _kill_stale_torcs() -> None:
    """SIGKILL any existing torcs-bin. Verified with pgrep — raises on failure.

    Per the 2026-05-13 probe: scr_server is a .so loaded into torcs-bin, not
    a separate process. Only torcs-bin needs killing.
    """
    subprocess.run(["pkill", "-9", "-f", "torcs-bin"], check=False, capture_output=True)
    time.sleep(0.5)
    r = subprocess.run(["pgrep", "-f", "torcs-bin"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        raise RuntimeError(
            f"Failed to kill stale torcs-bin; live PIDs: {r.stdout.strip()}"
        )


def _restart_torcs_kiosk_surface() -> None:
    """Kick TORCS back to the kiosk loop without insisting on a zero-PID gap.

    During /control/recover the kiosk supervisor may relaunch plain TORCS
    almost immediately after we kill the direct-race process. That is the
    desired end state, so recovery should not fail just because a new
    torcs-bin appears before the verification window closes.
    """
    subprocess.run(["pkill", "-9", "-f", "torcs-bin"], check=False, capture_output=True)
    time.sleep(0.5)


def _pause_kiosk_loop() -> None:
    Path(KIOSK_PAUSE_FILE).write_text("managed\n")


def _resume_kiosk_loop() -> None:
    try:
        Path(KIOSK_PAUSE_FILE).unlink()
    except FileNotFoundError:
        pass


def _torcs_gui_alive() -> bool:
    r = subprocess.run(["pgrep", "-f", "torcs-bin"], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def _xfwm4_alive() -> bool:
    r = subprocess.run(["pgrep", "-x", "xfwm4"], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def _ensure_xfwm4() -> None:
    if _xfwm4_alive():
        return
    env = os.environ.copy()
    env["DISPLAY"] = TORCS_DISPLAY
    log = open("/tmp/xfwm4.log", "a")
    subprocess.Popen(
        ["xfwm4", "--replace"],
        env=env,
        cwd=TORCS_USER_HOME,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    time.sleep(1.0)


def _scr_port_bound() -> bool:
    """Check whether UDP :3001 has a listener via netstat (ss/lsof not on image)."""
    try:
        r = subprocess.run(
            ["netstat", "-uln"], capture_output=True, text=True, timeout=2.0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    # Match a line like:  udp  0  0  0.0.0.0:3001  0.0.0.0:*
    return bool(re.search(rf":{SCR_PORT}\s", r.stdout))


async def _wait_for_torcs_gui(timeout_s: float = GUI_READY_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    stable_started_at: Optional[float] = None
    while time.monotonic() < deadline:
        if _torcs_gui_alive():
            if stable_started_at is None:
                stable_started_at = time.monotonic()
            elif (time.monotonic() - stable_started_at) >= 3.0:
                return True
        else:
            stable_started_at = None
        await asyncio.sleep(SCR_PORT_POLL_INTERVAL_S)
    return False


async def _wait_for_scr_port(
    torcs_proc: Optional[subprocess.Popen] = None,
    timeout_s: float = LAUNCH_TIMEOUT_S,
) -> bool:
    """Poll netstat for UDP :3001 binding.

    Hardened version: if a torcs Popen handle is passed, also fail
    immediately when that process exits (early death detection). Returns
    True only when port is bound AND torcs (if supervised) is still alive
    — closes the race condition where torcs briefly bound :3001 during
    startup, the daemon saw it as ready, then torcs died.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if torcs_proc is not None and torcs_proc.poll() is not None:
            logger.warning(
                "torcs exited (code=%s) before SCR port bound — see %s",
                torcs_proc.returncode, TORCS_LAUNCH_LOG,
            )
            return False
        if _scr_port_bound():
            return True
        await asyncio.sleep(SCR_PORT_POLL_INTERVAL_S)
    return False


TORCS_LAUNCH_LOG = "/tmp/torcs-launch.log"
SCR_CLIENT_LOG = "/tmp/scr-client.log"


def _launch_torcs(raceman_path: str) -> subprocess.Popen:
    """Spawn `torcs -r <xml>`. Output → LOG FILE, not PIPE.

    Why a log file and not subprocess.PIPE: torcs writes ~tens-of-KB of
    diagnostics on startup (GL info, audio init, SCR-driver init).
    subprocess.PIPE only allocates a 64 KB kernel buffer; with no reader
    on the daemon side, torcs blocks on the first write() that overflows.
    Result is the wrapper hangs, eventually exits as a zombie, torcs-bin
    is orphaned, and SCR :3001 goes dead — exactly the symptom observed
    2026-05-13. File-backed stdout drains naturally; daemon never blocks.
    """
    env = os.environ.copy()
    env["DISPLAY"] = TORCS_DISPLAY
    log = open(TORCS_LAUNCH_LOG, "w")  # closed when the process exits
    return subprocess.Popen(
        [TORCS_BIN, "-r", raceman_path],
        env=env,
        cwd=TORCS_USER_HOME,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _launch_scr_client(req_session_id: str, req_track: str, req_laps: int,
                      req_telemetry_filename: Optional[str]) -> subprocess.Popen:
    """Spawn torcs_jm_par.py (the SCR client). Same file-backed stdout
    treatment as _launch_torcs — gym_torcs writes per-tick observations
    to stdout that would otherwise overflow a PIPE buffer in seconds."""
    env = os.environ.copy()
    env["OVERRIDE_SESSION_ID"] = req_session_id
    env["OVERRIDE_TRACK"] = req_track
    env["OVERRIDE_LAPS"] = str(req_laps)
    if req_telemetry_filename:
        env["OVERRIDE_LOG_TELEMETRY"] = TELEMETRY_DIR.rstrip("/") + "/" + req_telemetry_filename
    else:
        env["OVERRIDE_LOG_TELEMETRY"] = TELEMETRY_DIR
    log = open(SCR_CLIENT_LOG, "w")
    return subprocess.Popen(
        ["python3", TORCS_SCRIPT],
        env=env,
        cwd=GYM_TORCS_DIR,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


async def _terminate_proc(proc: Optional[subprocess.Popen], label: str) -> Optional[int]:
    """SIGTERM → wait → SIGKILL → wait. Returns exit code or None if no proc."""
    if proc is None:
        return None
    if proc.poll() is not None:
        return proc.returncode
    logger.info("terminating %s pid=%s (SIGTERM, %ss grace)", label, proc.pid, TERMINATE_GRACE_S)
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=TERMINATE_GRACE_S)
        return proc.returncode
    except asyncio.TimeoutError:
        logger.warning("terminate %s pid=%s timed out; SIGKILL", label, proc.pid)
        try:
            proc.kill()
            await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=KILL_GRACE_S)
            return proc.returncode
        except (asyncio.TimeoutError, OSError):
            logger.error("SIGKILL %s pid=%s did not reap", label, proc.pid)
            return -9


async def _reset_torcs_gui_after_stop() -> None:
    """Reset the TORCS surface after a 3D-mode stop.

    Called fire-and-forget (asyncio.create_task) from control_stop() when the
    daemon did NOT own TORCS (3D cockpit / manual-launch mode — torcs_proc is
    None).  After the SCR client disconnects, TORCS stays mid-race; without
    this the operator would need a manual second action to settle the simulator.

    Strategy — xte key injection:
    ─────────────────────────────
    After SCR stops, TORCS enters its Race Stopped menu.  We send a short
    key sequence (default: Escape → Down → Return) to select Abandon Race
    and return TORCS to a stable main-menu state.

    Guard: we confirm torcs-bin is alive via pgrep before sending any keys.
    This prevents stray keystrokes landing on the XFCE desktop or another
    window if TORCS has already exited or crashed before Stop race was called.

    Env vars (read on every call — no daemon restart needed):
      OVERRIDE_TORCS_GUI_RESET=0          disable entirely (default: enabled)
      OVERRIDE_TORCS_GUI_SETTLE_S=1.0     seconds to wait after SCR stop
      OVERRIDE_TORCS_GUI_RESET_KEYS       colon-separated X key names sent via
                                          xte (default: Escape:Down:Return).
                                          Each token becomes xte 'key <token>'.
    """
    if os.environ.get("OVERRIDE_TORCS_GUI_RESET", "1") == "0":
        logger.info("gui-reset: disabled via OVERRIDE_TORCS_GUI_RESET=0")
        return

    settle_s = float(os.environ.get("OVERRIDE_TORCS_GUI_SETTLE_S", "") or "1.0")
    await asyncio.sleep(settle_s)

    # Guard: confirm torcs-bin is still running before injecting keys.
    # Without this guard, keys would land on whichever X window currently has
    # focus — potentially the XFCE desktop or another application.
    check = subprocess.run(
        ["pgrep", "-f", "torcs-bin"], capture_output=True, text=True
    )
    if check.returncode != 0:
        logger.info("gui-reset: no torcs-bin found; skipping key injection")
        return

    raw_keys = (
        os.environ.get("OVERRIDE_TORCS_GUI_RESET_KEYS", "") or "Escape:Down:Return"
    )
    key_seq = [k.strip() for k in raw_keys.split(":") if k.strip()]

    xte_env = {**os.environ, "DISPLAY": ":1"}
    xte_cmds: list[str] = []
    for key_name in key_seq:
        xte_cmds.append(f"key {key_name}")
        xte_cmds.append("usleep 150000")

    try:
        subprocess.run(["xte"] + xte_cmds, capture_output=True, env=xte_env)
    except FileNotFoundError:
        logger.warning("gui-reset: xte not found — install xautomation in the container")
        return

    logger.info("gui-reset: sent key sequence [%s] to TORCS", ", ".join(key_seq))


LaunchMode = Literal["cockpit_practice", "headless_quickrace"]


def _resolve_launch_mode(req: "StartRaceRequest") -> LaunchMode:
    if req.launch_mode is not None:
        return req.launch_mode
    return "headless_quickrace" if req.auto_launch_torcs else "cockpit_practice"


def _fresh_idle_race() -> ActiveRace:
    return ActiveRace(session_id="", state=RaceState.IDLE)


# ──────────────────────────────────────────────────────────────────────────────
# Request / response shapes
# ──────────────────────────────────────────────────────────────────────────────


class StartRaceRequest(BaseModel):
    """Body for POST /control/start."""
    session_id: str = Field(pattern=r"^s_[A-Za-z0-9_]+$", min_length=3, max_length=80)
    track: str = Field(default="aalborg", pattern=r"^[a-z0-9_-]+$", max_length=40)
    laps: int = Field(default=75, ge=1, le=200)
    telemetry_filename: Optional[str] = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]+\.jsonl$", max_length=120,
    )
    launch_mode: Optional[LaunchMode] = None
    auto_launch_torcs: bool = False


class StartRaceResponse(BaseModel):
    session_id: str
    pid: int                                      # SCR-client PID
    telemetry_dir: str
    track: str
    laps: int
    torcs_pid: Optional[int] = None               # populated when auto_launch=True
    launch_mode: LaunchMode
    state: RaceState = RaceState.ACTIVE


class StatusResponse(BaseModel):
    """Current daemon-side race state. `active` kept for backward compat."""
    state: RaceState
    active: bool                                  # True iff state == ACTIVE (compat)
    session_id: Optional[str] = None
    pid: Optional[int] = None                     # SCR-client PID (when present)
    torcs_pid: Optional[int] = None
    uptime_s: Optional[float] = None
    state_since_s: Optional[float] = None
    last_exit_code: Optional[int] = None
    last_error: Optional[str] = None
    track: Optional[str] = None
    laps: Optional[int] = None
    launch_mode: Optional[LaunchMode] = None


class StopResponse(BaseModel):
    status: str                                   # "stopped" | "no_active_race"
    session_id: Optional[str] = None
    scr_exit_code: Optional[int] = None
    torcs_exit_code: Optional[int] = None


class RecoverResponse(BaseModel):
    status: str                                   # "recovered" | "no_active_race"
    session_id: Optional[str] = None
    scr_exit_code: Optional[int] = None
    torcs_exit_code: Optional[int] = None
    state: RaceState = RaceState.IDLE


class TrackInfo(BaseModel):
    name: str
    category: str                                 # road | oval | dirt
    display_name: str
    author: Optional[str] = None
    description: Optional[str] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    pits: Optional[int] = None
    has_preview_asset: bool = False
    has_map_asset: bool = False


class TracksResponse(BaseModel):
    tracks: list[TrackInfo]


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="TORCS Control Daemon",
    description=(
        "Internal control plane for the IBM SkillsBuild TORCS lab container. "
        "Reached only over the compose override-net (no host port exposed). "
        "Phase 2.5 (2026-05-13): daemon owns TORCS + SCR-client lifecycle. "
        "See ADR-004."
    ),
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/control/status",
    response_model=StatusResponse,
    dependencies=[Depends(_verify_auth)],
)
async def control_status() -> StatusResponse:
    # No lock held here — status reads are read-only on the dataclass and
    # FastAPI runs them concurrently with stop/start. Eventual consistency
    # is acceptable; the worst case is a stale state value briefly visible
    # to a poller.
    #
    # Detect-dead-subprocesses (2026-05-13): poll both Popen objects.
    # If either has exited while state is ACTIVE/CONNECTING/WAITING_SCR, the
    # race is over — but distinguish graceful completion (exit=0) from
    # actual failure (non-zero or signal). UI uses last_error to decide
    # whether to show a success or failure framing.
    r = _race
    if r.state in (RaceState.WAITING_SCR, RaceState.CONNECTING, RaceState.ACTIVE):
        torcs_dead = r.torcs_proc is not None and r.torcs_proc.poll() is not None
        scr_dead = r.scr_proc is not None and r.scr_proc.poll() is not None
        if torcs_dead or scr_dead:
            torcs_code = r.torcs_proc.returncode if torcs_dead else None  # type: ignore[union-attr]
            scr_code = r.scr_proc.returncode if scr_dead else None        # type: ignore[union-attr]
            # Graceful = all observed exits are 0. The race ended normally
            # (lap count exhausted, /control/stop received, or operator
            # closed the TORCS window).
            graceful = all(c == 0 for c in (torcs_code, scr_code) if c is not None)
            if graceful:
                r.last_error = None
                logger.info(
                    "control_status: race ended gracefully (torcs=%s, scr=%s)",
                    torcs_code, scr_code,
                )
            else:
                died = []
                if torcs_dead:
                    died.append(f"torcs (exit={torcs_code})")
                if scr_dead:
                    died.append(f"scr-client (exit={scr_code})")
                r.last_error = "Subprocess(es) failed: " + ", ".join(died)
                logger.warning("control_status: %s", r.last_error)
            if scr_code is not None:
                r.last_exit_code = scr_code
            _resume_kiosk_loop()
            # Force-cleanup; direct assignment because some transition_to
            # moves would be illegal from the current state.
            r.state = RaceState.CLEANUP
            r.state_since = time.monotonic()
            # Reset proc handles so the next poll doesn't re-trigger this
            # block (and so /control/start can transition idle→launching).
            r.torcs_proc = None
            r.scr_proc = None

    # Bonus: cleanup → idle auto-advance once a status call observes the
    # cleanup state. Without this, the daemon stays "cleanup" until the
    # next /control/stop or /control/start; the UI badge gets stuck.
    if r.state == RaceState.CLEANUP and (time.monotonic() - r.state_since) > 0.5:
        r.state = RaceState.IDLE
        r.state_since = time.monotonic()

    now = time.monotonic()
    return StatusResponse(
        state=r.state,
        active=(r.state == RaceState.ACTIVE),
        session_id=r.session_id or None,
        pid=r.scr_proc.pid if r.scr_proc is not None else None,
        torcs_pid=r.torcs_proc.pid if r.torcs_proc is not None else None,
        uptime_s=round(now - r.started_at, 1) if r.state != RaceState.IDLE else None,
        state_since_s=round(now - r.state_since, 1),
        last_exit_code=r.last_exit_code,
        last_error=r.last_error,
        track=r.track,
        laps=r.laps,
        launch_mode=r.launch_mode,  # type: ignore[arg-type]
    )


@app.get(
    "/control/tracks",
    response_model=TracksResponse,
    dependencies=[Depends(_verify_auth)],
)
async def control_tracks() -> TracksResponse:
    """List every track installed under TORCS_TRACKS_DIR. Cached after
    first scan; daemon restart picks up new tracks."""
    tracks = [
        TrackInfo(
            name=record.name,
            category=record.category,
            display_name=record.display_name,
            author=record.author,
            description=record.description,
            length_m=record.length_m,
            width_m=record.width_m,
            pits=record.pits,
            has_preview_asset=record.has_preview_asset,
            has_map_asset=record.has_map_asset,
        )
        for record in _load_track_metadata()
    ]
    return TracksResponse(tracks=tracks)


@app.get(
    "/control/tracks/{category}/{track}/asset/{kind}",
    dependencies=[Depends(_verify_auth)],
)
async def control_track_asset(
    category: str,
    track: str,
    kind: Literal["preview", "map"],
):
    asset = _resolve_track_asset(category, track, kind)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track asset not found")
    return FileResponse(asset)


@app.post(
    "/control/start",
    response_model=StartRaceResponse,
    dependencies=[Depends(_verify_auth)],
    status_code=status.HTTP_201_CREATED,
)
async def control_start(req: StartRaceRequest) -> StartRaceResponse:
    global _race
    async with _control_lock:
        if _is_busy():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Race already in state '{_race.state.value}' for "
                    f"session {_race.session_id!r}. Stop it first."
                ),
            )

        # Initialize new race; lock held across the full launch sequence.
        launch_mode = _resolve_launch_mode(req)
        _race = ActiveRace(
            session_id=req.session_id,
            state=RaceState.IDLE,
            track=req.track,
            laps=req.laps,
            telemetry_filename=req.telemetry_filename,
            launch_mode=launch_mode,
        )
        _race.transition_to(RaceState.LAUNCHING)

        try:
            torcs_proc: Optional[subprocess.Popen] = None
            if launch_mode == "headless_quickrace":
                # Headless-race path. _kill_stale_torcs is ONLY safe here
                # because we're about to launch our own torcs as a fresh
                # process — anything currently running would conflict on
                # UDP :3001 and on the Xvfb display. In manual-launch mode
                # (auto_launch_torcs=False) we explicitly do NOT kill —
                # the operator's running TORCS GUI is the whole point.
                try:
                    raceman_path = _write_quickrace_config(req.track, req.laps)
                except (FileNotFoundError, RuntimeError, OSError) as e:
                    _race.transition_to(RaceState.CLEANUP, error=f"config write failed: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Could not write quickrace.xml: {e}",
                    )
                try:
                    _pause_kiosk_loop()
                    _kill_stale_torcs()
                except RuntimeError as e:
                    _resume_kiosk_loop()
                    _race.transition_to(RaceState.CLEANUP, error=str(e))
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e),
                    )
                try:
                    torcs_proc = _launch_torcs(raceman_path)
                except (OSError, FileNotFoundError) as e:
                    _resume_kiosk_loop()
                    _race.transition_to(RaceState.CLEANUP, error=f"torcs spawn failed: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Could not spawn torcs: {e}",
                    )
                # Surface the new PID + transition before we await the port poll.
                _race.torcs_proc = torcs_proc
                _race.transition_to(RaceState.WAITING_SCR)
                if not await _wait_for_scr_port(torcs_proc, LAUNCH_TIMEOUT_S):
                    # Reap the dead torcs before bailing. Capture log tail
                    # so /control/status surfaces a useful error message.
                    await _terminate_proc(torcs_proc, "torcs")
                    _resume_kiosk_loop()
                    log_tail = ""
                    try:
                        from pathlib import Path as _P
                        log_text = _P(TORCS_LAUNCH_LOG).read_text(errors="replace")
                        log_tail = log_text[-500:] if log_text else "(empty)"
                    except OSError:
                        log_tail = "(could not read log)"
                    _race.transition_to(
                        RaceState.CLEANUP,
                        error=f"torcs failed to bind UDP :{SCR_PORT}. Log tail: {log_tail}",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail=(
                            f"TORCS launched but SCR server did not bind UDP :{SCR_PORT} "
                            f"within {LAUNCH_TIMEOUT_S}s. Last lines of {TORCS_LAUNCH_LOG}: "
                            + log_tail
                        ),
                    )
                _race.transition_to(RaceState.CONNECTING)
            else:
                try:
                    raceman_path = _write_practice_config(req.track, req.laps)
                except (FileNotFoundError, RuntimeError, OSError, ET.ParseError) as e:
                    _race.transition_to(RaceState.CLEANUP, error=f"practice config failed: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Could not write practice.xml: {e}",
                    )
                try:
                    _pause_kiosk_loop()
                    _kill_stale_torcs()
                except RuntimeError as e:
                    _resume_kiosk_loop()
                    _race.transition_to(RaceState.CLEANUP, error=str(e))
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e),
                    )
                try:
                    torcs_proc = _launch_torcs(raceman_path)
                except (OSError, FileNotFoundError) as e:
                    _resume_kiosk_loop()
                    _race.transition_to(RaceState.CLEANUP, error=f"practice torcs spawn failed: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Could not spawn TORCS Practice run: {e}",
                    )
                _race.torcs_proc = torcs_proc
                _race.transition_to(RaceState.WAITING_SCR)
                if not await _wait_for_scr_port(torcs_proc, LAUNCH_TIMEOUT_S):
                    await _terminate_proc(torcs_proc, "torcs")
                    _resume_kiosk_loop()
                    log_tail = ""
                    try:
                        from pathlib import Path as _P
                        log_text = _P(TORCS_LAUNCH_LOG).read_text(errors="replace")
                        log_tail = log_text[-500:] if log_text else "(empty)"
                    except OSError:
                        log_tail = "(could not read log)"
                    _race.transition_to(
                        RaceState.CLEANUP,
                        error=f"Practice launch did not bind UDP :{SCR_PORT}. Log tail: {log_tail}",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail=(
                            f"Practice launch did not bind UDP :{SCR_PORT} within {LAUNCH_TIMEOUT_S}s. "
                            f"Last lines of {TORCS_LAUNCH_LOG}: {log_tail}"
                        ),
                    )
                _race.transition_to(RaceState.CONNECTING)

            # Spawn the SCR client either way.
            try:
                scr_proc = _launch_scr_client(
                    req.session_id, req.track, req.laps, req.telemetry_filename,
                )
            except (OSError, FileNotFoundError) as e:
                # Tear down torcs if we launched it
                await _terminate_proc(torcs_proc, "torcs")
                _resume_kiosk_loop()
                _race.transition_to(RaceState.CLEANUP, error=f"scr-client spawn failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Could not spawn SCR client: {e}",
                )

            _race.scr_proc = scr_proc
            _race.transition_to(RaceState.ACTIVE)
            logger.info(
                "control_start: race active session_id=%s track=%s laps=%s "
                "torcs_pid=%s scr_pid=%s",
                req.session_id, req.track, req.laps,
                torcs_proc.pid if torcs_proc else None, scr_proc.pid,
            )

            return StartRaceResponse(
                session_id=req.session_id,
                pid=scr_proc.pid,
                telemetry_dir=TELEMETRY_DIR,
                track=req.track,
                laps=req.laps,
                torcs_pid=torcs_proc.pid if torcs_proc else None,
                launch_mode=launch_mode,
                state=RaceState.ACTIVE,
            )
        except HTTPException:
            # Already transitioned to CLEANUP above
            raise
        except Exception as e:
            logger.exception("control_start: unexpected failure")
            _race.transition_to(RaceState.CLEANUP, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected control_start failure: {e}",
            )


@app.post(
    "/control/stop",
    response_model=StopResponse,
    dependencies=[Depends(_verify_auth)],
)
async def control_stop() -> StopResponse:
    """Stop SCR client first (graceful telemetry flush), then TORCS.

    Idempotent: no active race → 200 with status='no_active_race'.
    """
    global _race
    async with _control_lock:
        if _race.state == RaceState.IDLE:
            return StopResponse(
                status="no_active_race",
                scr_exit_code=_race.last_exit_code,
            )
        # The state could be ACTIVE, but also transitional. Move to STOPPING
        # if allowed; otherwise force-cleanup.
        try:
            _race.transition_to(RaceState.STOPPING)
        except ValueError:
            # If we're already past ACTIVE in some weird state, treat as
            # already-stopping and proceed with reaping.
            pass

        sid = _race.session_id
        # In 3D/manual-launch mode torcs_proc is None — we didn't own TORCS,
        # it's the live GUI surface.  Capture before the handles are cleared.
        gui_mode = _race.torcs_proc is None
        scr_exit = await _terminate_proc(_race.scr_proc, "scr-client")
        torcs_exit = await _terminate_proc(_race.torcs_proc, "torcs")
        _resume_kiosk_loop()

        _race.last_exit_code = scr_exit
        # CLEANUP → IDLE
        if _race.state == RaceState.STOPPING:
            _race.transition_to(RaceState.CLEANUP)
        if _race.state == RaceState.CLEANUP:
            _race.transition_to(RaceState.IDLE)
        # Reset transient handles so /control/status reads cleanly
        _race.scr_proc = None
        _race.torcs_proc = None

        # In 3D mode the TORCS GUI stays running after stop; drive it back to
        # a stable menu state so the operator doesn't need a manual ESC.
        # Fire-and-forget: response returns immediately; keys land ~1 s later.
        if gui_mode:
            asyncio.create_task(_reset_torcs_gui_after_stop())

        return StopResponse(
            status="stopped",
            session_id=sid,
            scr_exit_code=scr_exit,
            torcs_exit_code=torcs_exit,
        )


@app.post(
    "/control/recover",
    response_model=RecoverResponse,
    dependencies=[Depends(_verify_auth)],
)
async def control_recover() -> RecoverResponse:
    """Hard reset the simulator surface inside the torcs container only."""
    global _race
    async with _control_lock:
        sid = _race.session_id or None
        scr_exit = await _terminate_proc(_race.scr_proc, "scr-client")
        torcs_exit = await _terminate_proc(_race.torcs_proc, "torcs")
        _resume_kiosk_loop()
        _restart_torcs_kiosk_surface()

        _ensure_xfwm4()
        if not await _wait_for_torcs_gui():
            _race = _fresh_idle_race()
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="TORCS did not return to its standby GUI surface after recovery.",
            )

        _race = _fresh_idle_race()
        return RecoverResponse(
            status="recovered",
            session_id=sid,
            scr_exit_code=scr_exit,
            torcs_exit_code=torcs_exit,
            state=RaceState.IDLE,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle: ensure subprocesses don't outlive the daemon
# ──────────────────────────────────────────────────────────────────────────────


def _reap_on_signal(signum: int, _frame) -> None:
    """SIGTERM/SIGINT handler — kills BOTH subprocesses before exit.

    Order: SCR first (lets gym_torcs flush JSONL), then torcs. Without this,
    `podman stop torcs` shuts down uvicorn but leaves the subprocesses alive
    holding UDP :3001; the next container start fails to bind.
    """
    logger.info("daemon received signal=%s; reaping subprocesses if any", signum)

    def _sync_terminate(proc: Optional[subprocess.Popen], label: str) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=TERMINATE_GRACE_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=KILL_GRACE_S)
                except subprocess.TimeoutExpired:
                    logger.error("signal reap: %s pid=%s won't die", label, proc.pid)
        except OSError:
            pass

    # SCR first, then torcs — same order as graceful /control/stop.
    _sync_terminate(_race.scr_proc, "scr-client")
    _sync_terminate(_race.torcs_proc, "torcs")
    raise SystemExit(0)


signal.signal(signal.SIGTERM, _reap_on_signal)
signal.signal(signal.SIGINT, _reap_on_signal)
