#!/usr/bin/env bash
# scripts/torcs_container_init.sh — compose-time entrypoint override for
# the IBM SkillsBuild lab container `docker.io/johnsloe/torcs-competition`.
#
# The lab image ships with two known bugs that bite on every fresh start
# (documented in hands-on-labs/01_torcs_lab/RESULTS.md). This script
# absorbs both at boot, then chains to the image's real Cmd. Mounted
# read-only into the torcs service in docker-compose.yml.
#
# Two bugs absorbed:
#
#   1. Ollama directory ownership
#      The image ships /opt/ollama owned by root, but `ollama serve` runs
#      as user `student` and needs to write models there. start.sh's
#      step [2/6] hits "permission denied" and fails silently with
#      "WARNING: Ollama did not start in time".
#      Fix: chown -R student:student /opt/ollama before start.sh runs.
#      Narrow /tmp chown to ollama-specific paths only (review #5 from
#      v6 plan task 3.1b) — recursive chown on the whole /tmp tree would
#      clobber XFCE/Xvfb/DBus lock files student doesn't own.
#
#   2. VS Code extension install hang
#      start.sh's step [1/6] runs `code --install-extension ms-python.python`
#      inside the container, but on WSL2 the bundled `code` CLI prints
#      "please install VS Code in Windows" and hangs the whole script.
#      We're not editing code in the container (task 1.5 needs telemetry
#      capture only), so pre-create the marker directories the script's
#      skip-condition greps for, then suppress the hang defensively.
#
# After both absorptions, exec into the image's real entrypoint
# `/usr/local/bin/start.sh` (Cmd, not Entrypoint — confirmed via
# `podman inspect --format '{{json .Config}}'` and recorded in
# docs/plans/torcs-entrypoint.md during v6 task 1.1).
#
# Idempotent — running twice has no extra effect (chmod/chown on the
# same paths, mkdir -p on the marker dirs, pkill ignored when no match).

set -e

# ── Fix 1 — Ollama directory ownership ──────────────────────────────────────
# Recursive chown on /opt/ollama is safe (image-internal, not bind-mounted).
chown -R student:student /opt/ollama 2>/dev/null || true
# /tmp is shared between XFCE/Xvfb/DBus and ollama; only chown the paths
# ollama actually uses. Wildcard catches ollama-XXX socket dirs that get
# created on subsequent ollama serve invocations.
chown student:student /tmp/ollama.log 2>/dev/null || true
chown -R student:student /tmp/ollama 2>/dev/null || true
chown student:student /tmp/ollama-* 2>/dev/null || true

# ── Fix 2 — VS Code extension install hang ──────────────────────────────────
# Pre-create the marker dirs that start.sh's step [1/6] greps for. Once
# present, the script's "already installed, skipping" branch fires and
# the install step (which hangs under WSL2) is avoided.
mkdir -p /home/student/.vscode/extensions/ms-python.python \
         /home/student/.vscode/extensions/Continue.continue 2>/dev/null || true
chown -R student:student /home/student/.vscode 2>/dev/null || true

# Defensive: also kill any code.install-extension process if one slipped
# through (e.g., student modified a marker dir). Silent when no match.
pkill -f "code.*install-extension" 2>/dev/null || true

# Suppress the WSL-install prompt loop entirely. The marker prevents the
# install from running, but `code --version` or other `code` invocations
# downstream could still trip the prompt. compose runs this script as root
# (user: "0:0" in the torcs service) so the >> /etc/environment write
# succeeds; defensive `|| true` keeps the script working if someone
# strips the user: override (e.g., for testing as student).
{
    grep -q "DONT_PROMPT_WSL_INSTALL" /etc/environment 2>/dev/null || \
        echo "DONT_PROMPT_WSL_INSTALL=1" >> /etc/environment
} || true

# ── Telemetry capture dir owned by student so the logger can write ──────────
# Volume-permission UID-remap interaction (v6 plan gotcha #11): the
# torcs-telemetry named volume mounts here. Rootless Podman would normally
# create it root-owned in the user namespace; chown'ing as root (this init
# script runs as root before the image hands off to student) gives student
# write access regardless of UID-remap shape.
mkdir -p /home/student/workspace/gym_torcs/telemetry 2>/dev/null || true
chown -R student:student /home/student/workspace/gym_torcs/telemetry 2>/dev/null || true
chmod 0775 /home/student/workspace/gym_torcs/telemetry 2>/dev/null || true

# ── Boot sequence ───────────────────────────────────────────────────────────
# Two modes:
#   - default (no TORCS_CONTROL_SECRET): exec into the lab's start.sh as
#     before. Backward-compatible for operators running the image manually
#     or without the control-daemon profile.
#   - control-daemon (TORCS_CONTROL_SECRET set): background start.sh, wait
#     for noVNC at :6080 (proves Xvfb/VNC are up so gym_torcs will have
#     a display when /control/start is called), pip-install daemon deps,
#     exec uvicorn against control_daemon:app on :7000.
#
# Confirmed via `podman inspect docker.io/johnsloe/torcs-competition:amd64`:
#   Entrypoint: None
#   Cmd:        ["/usr/local/bin/start.sh"]
# (See docs/plans/torcs-entrypoint.md — deleted in the same PR as this
# script ships, per plan-file-lifecycle.)

if [ -z "$TORCS_CONTROL_SECRET" ]; then
    exec /usr/local/bin/start.sh "$@"
fi

# Phase 2 control-daemon mode.
echo "[init] TORCS_CONTROL_SECRET present → control-daemon mode"

# Background the lab boot sequence.
/usr/local/bin/start.sh "$@" &
LAB_PID=$!

# Wait for noVNC to come up. Load-bearing per v3 plan §2.3A and the
# architect's correctness item #1 — uvicorn must NOT start until Xvfb is
# ready, otherwise the first /control/start call will spawn gym_torcs
# against a missing display and fail. Cap at 120s so a broken lab boot
# fails the container instead of hanging compose forever.
echo "[init] waiting for noVNC on :6080 (cap 120s)..."
for _ in $(seq 1 120); do
    if curl -sf http://localhost:6080 >/dev/null 2>&1; then
        echo "[init] noVNC ready; reaping any leftover daemon deps install..."
        break
    fi
    sleep 1
done
if ! curl -sf http://localhost:6080 >/dev/null 2>&1; then
    echo "[init] FAIL: noVNC did not come up within 120s — control daemon will not start."
    wait $LAB_PID
    exit 1
fi

# Phase 2.6 — grant the daemon's torcs subprocess access to Xvfb :1
# without needing XAUTHORITY plumbing. start.sh launches Xvfb under
# whatever uid xstartup runs as; my daemon spawns torcs as root with
# no .Xauthority on disk, so torcs falls back to TEXT-MODE rendering
# (the SCR server still works, but no 3D window in noVNC). xhost
# +SI:localuser:root tells the X server "let any local process running
# as root connect" — closes the auth gap so torcs renders to :1 and
# the noVNC iframe shows the live race instead of a blank desktop.
#
# Trade-off: this widens X11 access from "Xauth-only" to "any local
# root process." Acceptable here because the container is single-user
# (user: "0:0" in docker-compose.yml — everything in this container
# IS root) and the X server is bound only to the in-container Xvfb
# unix socket. No host-side or cross-container X exposure.
echo "[init] granting root xhost access to :1 for the daemon's torcs spawns"
DISPLAY=:1 xhost +SI:localuser:root 2>/dev/null \
  || DISPLAY=:1 xhost +local:root 2>/dev/null \
  || DISPLAY=:1 xhost + 2>/dev/null \
  || echo "[init] WARN: xhost grant failed — torcs may run text-mode only"

# Phase 2.7 — pre-seed TORCS screen.xml with fullscreen=yes so the GUI
# race fills the entire Xvfb display (1920x1080) instead of opening a
# small window inside the XFCE desktop.
#
# Schema MUST match the stock TORCS screen.xml — confirmed against
# /usr/local/torcs/share/games/torcs/config/screen.xml in the lab image:
#   - section name is "Screen Properties" (NOT "Properties")
#   - dimensions are "x" + "y" (NOT "window width" + "window height")
#   - fullscreen attribute uses in="yes,no" enum
# The earlier 2.7 attempt used the wrong names — TORCS silently ignored
# the file and fell back to the stock 640x480 windowed default. That's
# why the iframe showed a tiny TORCS window inside a 1920x1080 XFCE
# desktop, with the HUD effectively unreadable.
#
# Force-overwrite each container start (not idempotent-conditional)
# because the previous wrong-schema file may be sitting on disk from
# the prior commit; we want the correct schema to land cleanly.
echo "[init] writing /root/.torcs/config/screen.xml (fullscreen=yes, correct schema)"
mkdir -p /root/.torcs/config
cat > /root/.torcs/config/screen.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by OVERRIDE torcs_container_init.sh — Phase 2.7 fix.
     Schema matches /usr/local/torcs/share/games/torcs/config/screen.xml. -->
<!DOCTYPE params SYSTEM "../tgf/params.dtd">
<params name="screen" type="params" mode="mw">
  <section name="Screen Properties">
    <attnum name="x" val="1920"/>
    <attnum name="y" val="1080"/>
    <attnum name="bpp" val="24"/>
    <attstr name="fullscreen" in="yes,no" val="yes"/>
    <attnum name="gamma" val="2.0"/>
  </section>
</params>
EOF

# Install daemon dependencies into the image's Python. The lab image
# ships Python 3 but not fastapi/uvicorn; install once per container start.
# --quiet keeps the compose logs from being flooded; failures fall through
# to the exec which will surface the actual import error.
pip install --quiet fastapi 'uvicorn[standard]' 2>/dev/null || \
    pip install --quiet fastapi uvicorn

# Launch the daemon in the foreground (replaces this shell so PID 1 is
# uvicorn — clean signal propagation when compose stops the container).
echo "[init] launching control daemon on :7000 (internal-only)"
cd /home/student/workspace/gym_torcs
exec python3 -m uvicorn control_daemon:app --host 0.0.0.0 --port 7000
