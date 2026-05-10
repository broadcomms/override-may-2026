#!/bin/bash
# ============================================================
# start.sh - Launches Ollama, virtual display, VNC, noVNC,
#            and XFCE desktop
# ============================================================

# Clean up any stale lock files
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# ------------------------------------------------------------
# 1. Start Ollama model server
#    Granite 4.0 350M is pre-baked into the image so this
#    starts instantly with no download needed
# ------------------------------------------------------------
echo "[1/5] Starting Ollama (Granite 4.0 350M)..."
ollama serve &
sleep 3
echo "      Ollama ready at http://localhost:11434"

# ------------------------------------------------------------
# 2. Start virtual framebuffer display
# ------------------------------------------------------------
echo "[2/5] Starting virtual display..."
Xvfb :1 -screen 0 1920x1080x24 &
export DISPLAY=:1
sleep 1

# ------------------------------------------------------------
# 3. Start XFCE desktop
# ------------------------------------------------------------
echo "[3/5] Starting XFCE desktop..."
startxfce4 &
sleep 2

# ------------------------------------------------------------
# 4. Start VNC server
#    Remove -nopw and add -passwd yourpassword for security
# ------------------------------------------------------------
echo "[4/5] Starting VNC server..."
x11vnc -display :1 -nopw -listen 0.0.0.0 -xkb -forever -shared &

# ------------------------------------------------------------
# 5. Start noVNC (browser-based VNC client)
# ------------------------------------------------------------
echo "[5/5] Starting noVNC..."
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
echo " watsonx Code Assistant extension (already configured)"
echo "======================================================"

# Keep container running
tail -f /dev/null
