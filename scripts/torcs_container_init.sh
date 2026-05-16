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

# ── Fix 3 — Xvfb visual config for software-Mesa alpha compositing ──────────
# The lab image's start.sh spawns Xvfb at `1920x1080x24` — 24-bit color, no
# alpha plane. Under software Mesa (llvmpipe — what we get with no /dev/dri
# or /dev/dxg passthrough), TORCS's menu rendering ends up compositing
# alpha-blended glyph quads against a backbuffer with no destination alpha,
# and the menu items blow out to solid white bars. Symptom seen 2026-05-13.
#
# Two-part patch:
#   1. `1280x720x24+32` — drop resolution to 1280x720 (16:9, within LLVMpipe's
#      reliable RGBA-texture-size range) and pad to 32 bits per pixel so an
#      8-bit alpha plane is allocated. At 1920x1080, TORCS's PUI dropshadow
#      texture hits a size where glTexImage2D silently no-ops — PUI falls back
#      to opaque white fill, producing the white-bars symptom.
#   2. `+extension RENDER +extension GLX` — explicitly enable XRender
#      (alpha compositing protocol) and GLX (OpenGL-via-X). Both are usually
#      on by default in modern Xvfb but harmless to assert.
#   3. `-ac` — disable host access control. Belt-and-braces with the xhost
#      grant below; covers the case where xhost runs late.
#
# Idempotent: sed pattern won't match a line that's already patched. Safe
# to run twice; safe to run on an already-fixed start.sh.
#
# Affects both default mode (exec start.sh) and control-daemon mode
# (background start.sh) since both paths execute start.sh downstream.
sed -i 's|Xvfb :1 -screen 0 1920x1080x24 &|Xvfb :1 -screen 0 1280x720x24+32 -ac +extension RENDER +extension GLX \&|' \
    /usr/local/bin/start.sh

# ── Fix 3.5 — x11vnc SIGSEGV in initialize_xfixes() ─────────────────────────
# x11vnc crashes with signal 11 (SIGSEGV) during initialize_xfixes() when
# TORCS or xfwm4 compositor is active. The xfixes extension provides
# cursor-shape notifications; without it x11vnc falls back to polling, which
# is fine for a kiosk or lab session (no precision cursor tracking needed).
#
# Adding -noxfixes disables the xfixes code path entirely, bypassing the
# crash. No user-visible degradation: cursor still renders, display still
# updates. The patch is unconditional — the crash reproducibly kills x11vnc
# regardless of OVERRIDE_KIOSK_MODE.
#
# Idempotent: sed won't match a line already containing -noxfixes.
sed -i 's|x11vnc -display :1 -nopw -listen 0\.0\.0\.0 -xkb -forever -shared|x11vnc -display :1 -nopw -listen 0.0.0.0 -xkb -forever -shared -noxfixes|' \
    /usr/local/bin/start.sh

# ── Fix 4 — Desktop launcher for TORCS GUI (one-click in noVNC) ─────────────
# The noVNC desktop ships with only File System + Home icons by default.
# Launching TORCS in GUI mode (which is what renders the 3D in-noVNC, since
# the daemon's `-r` path is text-mode-only — see commit 0e45fce thread)
# currently requires the operator to right-click the desktop → Open Terminal
# Here → type `torcs &`. Three steps and a typed command on a demo stage is
# bad UX; replace with a clickable desktop icon.
#
# Mechanism: XFCE's xfdesktop watches $HOME/Desktop for .desktop files.
# Drop one there with `Type=Application` + chmod +x and it renders as a
# clickable icon. xfdesktop uses inotify so newly-written files appear
# without restart. Container runs as root (compose `user: "0:0"`), so HOME
# is /root and the directory is /root/Desktop.
#
# Icon: TORCS doesn't ship a standalone .png icon (only splash screens
# inside data/img/). The splash-main.png is the closest thing — XFCE
# auto-resizes it to the desktop icon size. Falls back to a system theme
# name `applications-games` if the splash file is missing, which the
# Adwaita icon theme (present in the lab image) resolves.
#
# Trust prompt: on first click XFCE 4.16 may show "Launch / Mark Trusted /
# Cancel." The operator clicks "Mark Trusted" once and the prompt is gone
# forever. Suppressing it programmatically requires DBus session, which
# isn't running this early — accept the one-time click.
#
# Idempotent: re-running rewrites the same content; chmod is a no-op on
# already-executable files.
mkdir -p /root/Desktop
cat > /root/Desktop/launch-torcs.desktop <<'DESKTOP_EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Launch TORCS
Comment=Open TORCS in GUI mode — renders the 3D race in noVNC
Exec=/usr/local/torcs/bin/torcs
Icon=/usr/local/torcs/share/games/torcs/data/img/splash-main.png
Terminal=false
Categories=Game;
StartupNotify=false
DESKTOP_EOF
chmod +x /root/Desktop/launch-torcs.desktop

# ── Fix 4.5 — OVERRIDE branded car livery for car1-trb1 ──────────────────────
# The SCR server driver (scr_server.xml) uses car1-trb1 for all race slots.
# If assets/brand/car1-trb1.rgb is mounted at /opt/override-brand/, copy it
# over the stock texture so the TORCS 3D view shows the OVERRIDE livery.
#
# Applies unconditionally (both kiosk and operator modes) whenever the brand
# volume is mounted.  Idempotent: cp overwrites same bytes on repeated starts.
LIVERY_SRC=/opt/override-brand/car1-trb1.rgb
LIVERY_DST=/usr/local/torcs/share/games/torcs/cars/car1-trb1/car1-trb1.rgb
if [ -f "$LIVERY_SRC" ]; then
    cp "$LIVERY_SRC" "$LIVERY_DST"
    echo "[init] OVERRIDE livery applied: car1-trb1.rgb → $LIVERY_DST"
else
    echo "[init] no brand livery found at $LIVERY_SRC — stock car texture unchanged"
fi

# ── Fix 4.6 — OVERRIDE branded TORCS menu splash assets ─────────────────────
# TORCS menu and setup flows reference square `data/img/splash-*.png` assets
# from XML (quick race, practice, options, results, quit, etc.). When a
# branded override set is mounted at /opt/override-brand/torcs-menu/, copy the
# matching splash files over the stock versions so the visible menu layer feels
# product-owned without touching TORCS source or menu logic.
MENU_SRC_DIR=/opt/override-brand/torcs-menu
MENU_DST_DIR=/usr/local/torcs/share/games/torcs/data/img
if [ -d "$MENU_SRC_DIR" ]; then
    copied_menu_assets=0
    for src in "$MENU_SRC_DIR"/splash-*.png; do
        [ -e "$src" ] || continue
        cp "$src" "$MENU_DST_DIR/$(basename "$src")"
        copied_menu_assets=$((copied_menu_assets + 1))
    done
    if [ "$copied_menu_assets" -gt 0 ]; then
        echo "[init] OVERRIDE menu splash assets applied: ${copied_menu_assets} file(s) → $MENU_DST_DIR"
    else
        echo "[init] menu override dir present at $MENU_SRC_DIR but no splash-*.png assets found"
    fi
else
    echo "[init] no branded TORCS menu assets found at $MENU_SRC_DIR — stock menu splashes unchanged"
fi
# Transforms the XFCE desktop from a generic remote desktop into a minimal
# race-focused appliance surface. Only activates when OVERRIDE_KIOSK_MODE=1.
#
# What kiosk mode does:
#   a. Remove all XFCE panels (top bar + bottom taskbar)
#   b. Disable generic desktop file icons (File System, Home, Trash)
#   c. Suppress right-click desktop context menu and window-list menu
#   d. Set a branded backdrop: uses /opt/override-brand/logo-on-dark.png if
#      the brand assets volume is mounted, otherwise solid OVERRIDE navy
#      (#111827 ≈ rgba 0.067, 0.094, 0.153, 1.0).
#   e. Auto-launch TORCS on XFCE session start via ~/.config/autostart/
#
# Operator escape path: leave OVERRIDE_KIOSK_MODE unset (default 0) for the
# normal full desktop with the manual Fix 4 launcher icon. The kiosk config
# files are only written when the flag is "1".
#
# Config writes target /root/.config/xfce4/ — XFCE reads user config from
# $HOME, which is /root since compose runs this container as user: "0:0".
# Writing before start.sh means the files are in place before xfconfd starts
# in step [4/6] (startxfce4); xfconfd reads them on session init.
#
# Branding hook: mount ./assets/brand:/opt/override-brand:ro in compose and
# the script auto-promotes from solid-color to image backdrop automatically.
#
# Idempotent — re-running overwrites the same content; no extra side effects.

if [ "${OVERRIDE_KIOSK_MODE:-0}" = "1" ]; then
    echo "[init] OVERRIDE_KIOSK_MODE=1 — applying kiosk desktop surface"
    mkdir -p \
        /root/.config/xfce4/xfconf/xfce-perchannel-xml \
        /root/.config/autostart

    # ── (a) Remove all XFCE panels ──────────────────────────────────────────
    # An empty `panels` array tells xfce4-panel there is nothing to draw.
    # xfce4-panel still starts as part of startxfce4 but renders no windows.
    cat > /root/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml <<'PANEL_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by OVERRIDE torcs_container_init.sh — kiosk mode.
     Empty panels array suppresses all XFCE panel chrome. -->
<channel name="xfce4-panel" version="1.0">
  <property name="panels" type="array"/>
</channel>
PANEL_EOF

    # ── (b/c/d) xfdesktop: no file icons, no context menus, branded backdrop ─
    # Backdrop path for XFCE 4.16 on a single Xvfb display:
    #   /backdrop/screen0/monitor0/workspace0
    # "monitor0" is xfdesktop's internal zero-based index, not the Xrandr
    # connector name — consistent across all Xvfb sessions.
    # color-style=0 (solid). rgba1 values are normalised 0.0–1.0 doubles
    # matching OVERRIDE's dark navy (#111827 ≈ 0.067, 0.094, 0.153).
    # When logo-on-dark.png is mounted, image-style=5 (zoomed fill) activates
    # so the branding fills the Xvfb surface behind the TORCS window.
    #
    # We stage the mounted image into a local wallpaper path first instead of
    # pointing XFCE at the bind mount directly. This makes the branded backdrop
    # survive the session off a stable, read-local path that is definitely
    # present by the time xfdesktop reads its config.
    BRAND_IMAGE_MOUNT=/opt/override-brand/logo-on-dark.png
    BRAND_IMAGE_STAGED=/usr/local/share/backgrounds/override-kiosk.png
    BRAND_IMAGE=""
    if [ -f "$BRAND_IMAGE_MOUNT" ]; then
        mkdir -p /usr/local/share/backgrounds
        cp "$BRAND_IMAGE_MOUNT" "$BRAND_IMAGE_STAGED"
        chmod 0644 "$BRAND_IMAGE_STAGED"
        BRAND_IMAGE="$BRAND_IMAGE_STAGED"
        BACKDROP_IMAGE_STYLE=5
        BACKDROP_IMAGE_LINE="          <property name=\"last-image\" type=\"string\" value=\"${BRAND_IMAGE}\"/>"
    else
        BACKDROP_IMAGE_STYLE=0
        BACKDROP_IMAGE_LINE=""
    fi

    # Unquoted heredoc so ${BACKDROP_IMAGE_STYLE} and ${BACKDROP_IMAGE_LINE}
    # expand. The XML body contains no other $ sequences.
    cat > /root/.config/xfce4/xfconf/xfce-perchannel-xml/xfdesktop.xml <<XFDESKTOP_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by OVERRIDE torcs_container_init.sh — kiosk mode.
     Disables file icons, context menus; sets OVERRIDE branded backdrop. -->
<channel name="xfdesktop" version="1.0">
  <property name="backdrop" type="empty">
    <property name="screen0" type="empty">
      <property name="monitor0" type="empty">
        <property name="workspace0" type="empty">
          <property name="color-style" type="int" value="0"/>
          <property name="rgba1" type="array">
            <value type="double" value="0.067"/>
            <value type="double" value="0.094"/>
            <value type="double" value="0.153"/>
            <value type="double" value="1.0"/>
          </property>
          <property name="image-style" type="int" value="${BACKDROP_IMAGE_STYLE}"/>
${BACKDROP_IMAGE_LINE}
        </property>
      </property>
    </property>
  </property>
  <property name="desktop" type="empty">
    <property name="icons" type="empty">
      <property name="file-icons" type="empty">
        <property name="show-filesystem" type="bool" value="false"/>
        <property name="show-home" type="bool" value="false"/>
        <property name="show-trash" type="bool" value="false"/>
        <property name="show-removable" type="bool" value="false"/>
      </property>
    </property>
    <property name="desktop-menu" type="empty">
      <property name="show" type="bool" value="false"/>
    </property>
    <property name="windowlist-menu" type="empty">
      <property name="show" type="bool" value="false"/>
    </property>
  </property>
</channel>
XFDESKTOP_EOF

    # ── (e) TORCS restart-loop supervisor ────────────────────────────────────
    # Hard-kiosk: write a supervisor wrapper so autostart never points at torcs
    # directly. The wrapper relaunches TORCS after any exit (normal quit,
    # Alt+F4, crash) so the user never lands on a usable desktop.
    #
    # Crash-loop guard: if TORCS exits in < MIN_RUNTIME seconds on
    # CRASH_LIMIT consecutive attempts, backs off BACKOFF_SLEEP seconds before
    # the next launch. This prevents a misconfigured binary from hammering the
    # display stack in a tight spin.
    #
    # The script is written to /usr/local/bin/ (root-owned, init runs as root)
    # so it survives for the life of the container. Re-running rewrites it
    # (idempotent). Do not edit manually — changes are overwritten on restart.
    cat > /usr/local/bin/torcs-kiosk-loop.sh <<'LOOP_EOF'
#!/usr/bin/env bash
# OVERRIDE hard-kiosk TORCS supervisor.
# Written by scripts/torcs_container_init.sh — do not edit manually.
export DISPLAY=:1

MIN_RUNTIME=3    # seconds — shorter exit counts as a crash
CRASH_LIMIT=3    # consecutive crash-exits before backoff
BACKOFF_SLEEP=15 # seconds to wait after crash-loop is detected
RESTART_SLEEP=2  # normal exit restart delay

# Initial delay: let XFCE compositor fully initialise before the
# first GL context opens.
sleep 2

# Disable X screen blanking so the display never fades to grey during
# idle periods (e.g. between TORCS restarts or on a paused race).
# xset s off     — turns off the screen-saver timer entirely
# xset s noblank — belt-and-suspenders: no blank even if timer fires
# xset -dpms     — harmless on Xvfb (DPMS unavailable) but correct
#                  on any real display that may be mapped to this X server
DISPLAY=:1 xset s off
DISPLAY=:1 xset s noblank
DISPLAY=:1 xset -dpms

fast_exits=0
while true; do
    start_ts=$(date +%s)
    /usr/local/torcs/bin/torcs
    end_ts=$(date +%s)
    runtime=$(( end_ts - start_ts ))

    if [ "$runtime" -lt "$MIN_RUNTIME" ]; then
        fast_exits=$(( fast_exits + 1 ))
        echo "[kiosk-loop] fast exit #${fast_exits} (${runtime}s)"
        if [ "$fast_exits" -ge "$CRASH_LIMIT" ]; then
            echo "[kiosk-loop] crash-loop guard — backing off ${BACKOFF_SLEEP}s"
            sleep "$BACKOFF_SLEEP"
            fast_exits=0
        fi
    else
        fast_exits=0
        echo "[kiosk-loop] TORCS exited after ${runtime}s — restarting in ${RESTART_SLEEP}s"
        sleep "$RESTART_SLEEP"
    fi
done
LOOP_EOF
    chmod +x /usr/local/bin/torcs-kiosk-loop.sh

    # ── (f) Autostart pointing to the supervisor ──────────────────────────────
    # xfce4-session executes ~/.config/autostart/ .desktop entries at login.
    # No "Mark Trusted" prompt — that dialog applies to xfdesktop file icons
    # only, not to session-autostart entries.
    cat > /root/.config/autostart/torcs-kiosk.desktop <<'AUTOSTART_EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=TORCS Kiosk Supervisor
Comment=OVERRIDE hard-kiosk: TORCS restart-loop keeps the cockpit surface live
Exec=/usr/local/bin/torcs-kiosk-loop.sh
Terminal=false
Hidden=false
X-XFCE-Autostart-Enabled=true
AUTOSTART_EOF

    # ── (g) Strip window decorations via xfwm4 ───────────────────────────────
    # Empty button_layout removes title-bar controls (close, minimize,
    # maximize) from all windows. TORCS in fullscreen already has no visible
    # frame, so the race surface is unaffected. Any window that appears while
    # TORCS is loading or restarting will have no title-bar escape affordances.
    # xfwm4 reads this file at session start before drawing any window.
    cat > /root/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml <<'XFWM4_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by OVERRIDE torcs_container_init.sh — kiosk mode.
     Empty button_layout removes all title-bar controls. -->
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="button_layout" type="string" value=""/>
  </property>
</channel>
XFWM4_EOF

    echo "[init] hard-kiosk surface configured — panels suppressed, icons hidden, supervisor installed, decorations stripped"
    if [ -f "$BRAND_IMAGE" ]; then
        echo "[init] kiosk backdrop: branded image staged from ${BRAND_IMAGE_MOUNT} to ${BRAND_IMAGE}"
    else
        echo "[init] kiosk backdrop: solid OVERRIDE navy (#111827) — mount assets/brand/ for branded image"
    fi
else
    echo "[init] OVERRIDE_KIOSK_MODE not set — standard desktop mode"
fi

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
# the file and fell back to the stock 640x480 windowed default.
#
# Phase 2.7 v6 — resolution dropped from 1920x1080 to 1280x720.
#
# v5 fixed the blue cast (gamma 2.0 → 1.0) but left the menu buttons
# rendering as solid white blocks. The 3D scene (car/track/sky) rendered
# correctly, so polygon + texture paths were fine — only TORCS's PUI
# menu widget path was broken.
#
# Root cause: Mesa's LLVMpipe software rasterizer (the GL impl used by
# Xvfb without a real GPU) has documented size limits on RGBA textures.
# TORCS's PUI menu uses a dropshadow texture that scales with the screen
# resolution; at 1920x1080 the texture hit a size where glTexImage2D
# silently no-ops. PUI's fallback render is opaque white fill — which is
# exactly the symptom that was reported.
#
# 1280x720 stays well within LLVMpipe's reliable range and is still 16:9
# so the OVERRIDE iframe's aspect-video wrapper hosts it cleanly. HUD
# text at iframe display size (~720px tall in the embedded view) is
# perfectly legible since the source is now 1:1 with the iframe height.
#
# Why not just drop fullscreen and let TORCS default to 640x480 windowed:
# we'd lose the "drives in noVNC" demo flow and re-introduce the manual
# config step the operator should not have to do.
#
# Force-overwrite each container start (not idempotent-conditional)
# because the previous wrong-values file may be sitting on disk from
# the prior commit; we want the corrected screen.xml to land cleanly.
echo "[init] writing /root/.torcs/config/screen.xml (fullscreen=yes, 1280x720, bpp=32, gamma=1.5, OVERRIDE menu theme)"
mkdir -p /root/.torcs/config
cat > /root/.torcs/config/screen.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by OVERRIDE torcs_container_init.sh — Phase 2.7 v6.
     Schema matches /usr/local/torcs/share/games/torcs/config/screen.xml.
     1280x720 stays within LLVMpipe's reliable RGBA-texture-size envelope;
     at 1920x1080 TORCS's PUI dropshadow texture hits a size where
     glTexImage2D silently no-ops and PUI falls back to opaque white fill.
     See the comment block above this `cat` heredoc for the full diagnosis. -->
<!DOCTYPE params SYSTEM "../tgf/params.dtd">
<params name="screen" type="params" mode="mw">
  <section name="Screen Properties">
    <attnum name="x" val="1280"/>
    <attnum name="y" val="720"/>
    <attnum name="bpp" val="32"/>
    <attstr name="maximum color depth" val="yes"/>
    <attstr name="fullscreen" in="yes,no" val="yes"/>
    <attnum name="gamma" val="1.5"/>
  </section>

  <section name="Menu Font">
    <attstr name="name" val="b5.glf"/>
    <attnum name="size big" val="16"/>
    <attnum name="size large" val="12"/>
    <attnum name="size medium" val="9"/>
    <attnum name="size small" val="7"/>
  </section>

  <section name="Console Font">
    <attstr name="name" val="b7.glf"/>
    <attnum name="size big" val="14"/>
    <attnum name="size large" val="10"/>
    <attnum name="size medium" val="6"/>
    <attnum name="size small" val="5"/>
  </section>

  <section name="Digital Font">
    <attstr name="name" val="digital.glf"/>
    <attnum name="size big" val="6"/>
  </section>

  <section name="Menu Colors">
    <section name="colors">
      <section name="background">
        <attnum name="red" val="0.02"/>
        <attnum name="green" val="0.05"/>
        <attnum name="blue" val="0.13"/>
        <attnum name="alpha" val="0.08"/>
      </section>
      <section name="title">
        <attnum name="red" val="0.95"/>
        <attnum name="green" val="0.97"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="background focused button">
        <attnum name="red" val="0.10"/>
        <attnum name="green" val="0.16"/>
        <attnum name="blue" val="0.36"/>
        <attnum name="alpha" val="0.85"/>
      </section>
      <section name="background pushed button">
        <attnum name="red" val="0.16"/>
        <attnum name="green" val="0.26"/>
        <attnum name="blue" val="0.55"/>
        <attnum name="alpha" val="0.95"/>
      </section>
      <section name="background enabled button">
        <attnum name="red" val="0.05"/>
        <attnum name="green" val="0.09"/>
        <attnum name="blue" val="0.22"/>
        <attnum name="alpha" val="0.80"/>
      </section>
      <section name="background disabled button">
        <attnum name="red" val="0.05"/>
        <attnum name="green" val="0.06"/>
        <attnum name="blue" val="0.10"/>
        <attnum name="alpha" val="0.50"/>
      </section>
      <section name="focused button">
        <attnum name="red" val="1.0"/>
        <attnum name="green" val="1.0"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="pushed button">
        <attnum name="red" val="1.0"/>
        <attnum name="green" val="1.0"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="enabled button">
        <attnum name="red" val="0.93"/>
        <attnum name="green" val="0.96"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="disabled button">
        <attnum name="red" val="0.48"/>
        <attnum name="green" val="0.54"/>
        <attnum name="blue" val="0.64"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="background scroll list">
        <attnum name="red" val="0.01"/>
        <attnum name="green" val="0.03"/>
        <attnum name="blue" val="0.10"/>
        <attnum name="alpha" val="0.65"/>
      </section>
      <section name="scroll list">
        <attnum name="red" val="0.93"/>
        <attnum name="green" val="0.96"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="background selected scroll list">
        <attnum name="red" val="0.11"/>
        <attnum name="green" val="0.18"/>
        <attnum name="blue" val="0.40"/>
        <attnum name="alpha" val="0.95"/>
      </section>
      <section name="selected scroll list">
        <attnum name="red" val="1.0"/>
        <attnum name="green" val="1.0"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="label">
        <attnum name="red" val="0.95"/>
        <attnum name="green" val="0.97"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="tip">
        <attnum name="red" val="0.76"/>
        <attnum name="green" val="0.84"/>
        <attnum name="blue" val="0.98"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="mouse 1">
        <attnum name="red" val="0.35"/>
        <attnum name="green" val="0.58"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="mouse 2">
        <attnum name="red" val="0.09"/>
        <attnum name="green" val="0.15"/>
        <attnum name="blue" val="0.35"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="help key">
        <attnum name="red" val="1.0"/>
        <attnum name="green" val="0.72"/>
        <attnum name="blue" val="0.20"/>
        <attnum name="alpha" val="1.0"/>
      </section>
      <section name="help description">
        <attnum name="red" val="0.70"/>
        <attnum name="green" val="0.84"/>
        <attnum name="blue" val="1.0"/>
        <attnum name="alpha" val="1.0"/>
      </section>
    </section>
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
