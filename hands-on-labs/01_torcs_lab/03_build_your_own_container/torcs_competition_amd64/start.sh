#!/bin/bash
# ============================================================
# start.sh - Startup script for the TORCS competition container
#
# Handles on every start:
#   - Restoring default configs if not already on the volume
#   - VS Code extension install (first boot only)
#   - Ollama startup with health check
#   - Virtual display, XFCE desktop, VNC, noVNC
# ============================================================

set -e

# Clean up any stale X lock files from previous runs
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# ------------------------------------------------------------
# 0. Restore default configs onto the persistent volume
#    /home/student is mounted as a named volume. On first run
#    it is empty, so we copy the defaults baked into the image
#    via /etc/skel. On subsequent runs the files already exist
#    so nothing is overwritten — student changes are preserved.
# ------------------------------------------------------------
echo "[0/6] Checking persistent home directory..."
if [ ! -f "$HOME/.config/Code/User/settings.json" ]; then
    echo "      First boot — copying default VS Code settings..."
    mkdir -p "$HOME/.config/Code/User"
    cp /etc/skel/.config/Code/User/settings.json "$HOME/.config/Code/User/settings.json"
fi

if [ ! -f "$HOME/.continue/config.json" ]; then
    echo "      First boot — copying default Continue.dev config..."
    mkdir -p "$HOME/.continue"
    cp /etc/skel/.continue/config.json "$HOME/.continue/config.json"
fi

# ------------------------------------------------------------
# 1. Install VS Code extensions (first boot only)
#    Extensions are installed here rather than at image build
#    time to avoid a Node.js/yauzl ZIP bug under QEMU emulation.
#    The --force flag suppresses the "continue anyway [y/n]" prompt.
#    Once installed they persist on the named volume.
# ------------------------------------------------------------
echo "[1/6] Checking VS Code extensions..."
if ! ls "$HOME/.vscode/extensions" 2>/dev/null | grep -q "ms-python.python"; then
    echo "      Installing VS Code extensions (first boot, may take a minute)..."
    code --no-sandbox --do-not-sync \
         --install-extension ms-python.python \
         --install-extension Continue.continue \
         --force 2>&1 | grep -v "^$" || true
    echo "      VS Code extensions installed."
else
    echo "      VS Code extensions already installed, skipping."
fi

# ------------------------------------------------------------
# 2. Start Ollama model server
#    Granite 4.0 350M is pre-baked into the image.
#    We wait until the API responds before continuing so that
#    VS Code / Continue.dev always find Ollama ready on launch.
# ------------------------------------------------------------
echo "[2/6] Starting Ollama..."
ollama serve > /tmp/ollama.log 2>&1 &

# Wait up to 30 seconds for Ollama API to become available
OLLAMA_READY=0
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        OLLAMA_READY=1
        break
    fi
    sleep 1
done

if [ $OLLAMA_READY -eq 1 ]; then
    echo "      Ollama ready at http://localhost:11434"
else
    echo "      WARNING: Ollama did not start in time. Check /tmp/ollama.log"
fi

# ------------------------------------------------------------
# 3. Start virtual framebuffer display
# ------------------------------------------------------------
echo "[3/6] Starting virtual display..."
Xvfb :1 -screen 0 1920x1080x24 &
export DISPLAY=:1
sleep 1

# ------------------------------------------------------------
# 4. Start XFCE desktop
# ------------------------------------------------------------
echo "[4/6] Starting XFCE desktop..."
startxfce4 &
sleep 2

# ------------------------------------------------------------
# 5. Start VNC server
# ------------------------------------------------------------
echo "[5/6] Starting VNC server..."
x11vnc -display :1 -nopw -listen 0.0.0.0 -xkb -forever -shared &

# ------------------------------------------------------------
# 6. Start noVNC (browser-based VNC client)
# ------------------------------------------------------------
echo "[6/6] Starting noVNC..."
websockify --web=/usr/share/novnc 6080 localhost:5900 &

echo ""
echo "======================================================"
echo " Environment ready!"
echo ""
echo " Desktop (browser) : http://localhost:6080/vnc.html"
echo " Desktop (VNC)     : localhost:5900"
echo " Ollama API        : http://localhost:11434"
echo " TORCS SCR port    : 3001 (UDP)"
echo " Student workspace : /home/student/workspace"
echo ""
echo " Granite 4.0 350M is available in VS Code via the"
echo " Continue extension (already configured)"
echo ""
echo " To stop the container gracefully:"
echo "   podman stop <container-id>"
echo "======================================================"

# Keep container running
tail -f /dev/null
