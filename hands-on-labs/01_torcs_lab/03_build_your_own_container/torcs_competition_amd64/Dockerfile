# ============================================================
# Dockerfile: Ubuntu 22.04 + TORCS 1.3.7 (SCR patch) + VS Code
#             + Ollama + IBM Granite 4.0 350M
# For use in AI-driven car racing competitions
#
# Build:
#   podman build --platform linux/amd64 -t torcs-competition:amd64 .
#
# Run:
#   podman run -it --rm \
#     -p 5900:5900 \        # VNC
#     -p 6080:6080 \        # noVNC (browser access)
#     -p 3001:3001 \        # TORCS SCR UDP port
#     -v ~/RaceYourCode:/home/student/workspace:Z \
#     torcs-competition:amd64
#
# GPU (optional):
#   podman run -it --rm --device nvidia.com/gpu=all \
#     -p 5900:5900 -p 6080:6080 -p 3001:3001 \
#     -v ~/RaceYourCode:/home/student/workspace:Z \
#     torcs-competition:amd64
#
# Access desktop in browser: http://localhost:6080/vnc.html
#
# Notes:
#   - Students mount their local RaceYourCode folder at runtime.
#     Nothing is baked into /home/student/workspace in this image.
#   - VS Code extensions (ms-python, Continue.dev) are installed
#     on first container start, not at build time. This avoids a
#     Node.js/yauzl ZIP bug that breaks extension installs under
#     QEMU emulation when cross-building amd64 on macOS.
#   - PyTorch is installed with CUDA 12.1 support (~2.5GB).
#     On CPU-only machines it automatically falls back to CPU.
#     On NVIDIA GPU machines, launch with --device nvidia.com/gpu=all.
# ============================================================

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV OLLAMA_MODELS=/opt/ollama/models
ENV OLLAMA_HOST=0.0.0.0:11434

# ------------------------------------------------------------
# 1. System dependencies
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core build tools
    build-essential \
    cmake \
    autoconf \
    automake \
    libtool \
    git \
    wget \
    curl \
    unzip \
    sudo \
    # TORCS graphics and audio dependencies
    libglib2.0-dev \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    freeglut3-dev \
    libpng-dev \
    libjpeg-dev \
    libopenal-dev \
    libalut-dev \
    libvorbis-dev \
    libogg-dev \
    # TORCS input and windowing dependencies
    libxi-dev \
    libxmu-dev \
    libxrender-dev \
    libxrandr-dev \
    libxxf86vm-dev \
    libplib-dev \
    # Virtual desktop, VNC, and browser-based access
    xvfb \
    x11vnc \
    xfce4 \
    xfce4-terminal \
    dbus-x11 \
    novnc \
    websockify \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    # Utilities
    net-tools \
    nano \
    xdg-utils \
    xautomation \
    # Required by Ollama installer
    zstd \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# 2. Create non-root student user
# ------------------------------------------------------------
RUN useradd -m -s /bin/bash student && \
    echo "student:student" | chpasswd && \
    usermod -aG sudo student && \
    echo "student ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# ------------------------------------------------------------
# 3. Install VS Code
#    apt-get update is needed here as the cache was wiped in
#    step 1. libnspr4 and libnss3 must be pre-installed as
#    VS Code's .deb lists them as required dependencies.
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnspr4 \
    libnss3 && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then \
        wget -qO /tmp/vscode.deb "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-arm64"; \
    else \
        wget -qO /tmp/vscode.deb "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64"; \
    fi && \
    apt-get install -y /tmp/vscode.deb && \
    rm /tmp/vscode.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# 4. Configure VS Code settings and Continue.dev for Granite
#    Settings are written to /etc/skel so they are copied into
#    any new home directory, including when a named volume is
#    mounted over /home/student on first run.
#    Key settings:
#      - Copilot chat disabled to prevent popup on first launch
#      - GitHub Copilot and all telemetry disabled
#      - Continue.dev pre-configured to use local Ollama
# ------------------------------------------------------------
RUN mkdir -p /etc/skel/.config/Code/User && \
    cat > /etc/skel/.config/Code/User/settings.json << 'EOF'
{
    "editor.inlineSuggest.enabled": true,
    "python.defaultInterpreterPath": "/usr/bin/python3",
    "python.analysis.typeCheckingMode": "basic",
    "github.copilot.enable": {"*": false},
    "github.copilot.chat.welcomeMessage": "never",
    "telemetry.telemetryLevel": "off",
    "workbench.startupEditor": "none",
    "extensions.autoCheckUpdates": false,
    "update.mode": "none"
}
EOF

RUN mkdir -p /etc/skel/.continue && \
    cat > /etc/skel/.continue/config.json << 'EOF'
{
  "models": [
    {
      "title": "Granite 4.0 350M (local)",
      "provider": "ollama",
      "model": "granite4:350m",
      "apiBase": "http://localhost:11434"
    }
  ],
  "tabAutocompleteModel": {
    "title": "Granite 4.0 350M (autocomplete)",
    "provider": "ollama",
    "model": "granite4:350m",
    "apiBase": "http://localhost:11434"
  },
  "allowAnonymousTelemetry": false
}
EOF

# Copy skel configs into the student home directory
RUN cp -r /etc/skel/.config /home/student/.config && \
    cp -r /etc/skel/.continue /home/student/.continue && \
    chown -R student:student /home/student/.config /home/student/.continue

# ------------------------------------------------------------
# 5. Build and install TORCS 1.3.7 from source
#    Clone, build, install, and delete the source tree in a
#    single RUN layer so build artifacts (~400MB of object
#    files and source) are never committed to the image.
#    Note: parallel make (-j) is intentionally avoided —
#    TORCS's Makefile uses a self-reinvoking "restart" target
#    that causes race conditions under parallel builds.
# ------------------------------------------------------------
WORKDIR /opt
RUN git clone --depth=1 https://github.com/fmirus/torcs-1.3.7.git torcs-src && \
    cd torcs-src && \
    ./configure --prefix=/usr/local/torcs && \
    make && \
    make install && \
    make datainstall && \
    cd / && rm -rf /opt/torcs-src

ENV TORCS_HOME=/usr/local/torcs
ENV PATH="$TORCS_HOME/bin:$PATH"

# ------------------------------------------------------------
# 6. Install SCR server car/driver into TORCS drivers folder
#    scr_server.zip must be present in the build context.
#    The SCR UDP interface on port 3001 is built into torcs-1.3.7.
# ------------------------------------------------------------
COPY scr_server.zip /tmp/scr_server.zip
RUN mkdir -p /usr/local/share/games/torcs/drivers && \
    unzip -o /tmp/scr_server.zip -d /usr/local/share/games/torcs/drivers/ && \
    rm -rf /usr/local/share/games/torcs/drivers/__MACOSX && \
    find /usr/local/share/games/torcs/drivers/ -name ".DS_Store" -delete && \
    rm /tmp/scr_server.zip

# ------------------------------------------------------------
# 7. Python packages for student AI agents
#    PyTorch is installed with CUDA 12.1 support so the image
#    works on NVIDIA GPU machines. On CPU-only machines PyTorch
#    automatically falls back to CPU — no code changes needed.
#    CUDA 12.1 is chosen as it covers most modern NVIDIA drivers
#    (GTX 10xx and newer). To use a different CUDA version swap
#    cu121 for cu118 (CUDA 11.8) or cpu (CPU-only, ~200MB).
# ------------------------------------------------------------
RUN pip3 install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cu121 \
    numpy \
    scipy \
    scikit-learn \
    torch \
    torchvision \
    gymnasium \
    matplotlib \
    pandas

# ------------------------------------------------------------
# 8. Install Ollama
# ------------------------------------------------------------
RUN curl -fsSL https://ollama.com/install.sh | sh

# ------------------------------------------------------------
# 9. Pre-pull IBM Granite 4.0 350M into the image
#    Ollama is started temporarily to perform the pull then
#    shut down. The model files persist in $OLLAMA_MODELS.
# ------------------------------------------------------------
RUN mkdir -p $OLLAMA_MODELS && \
    ollama serve & \
    OLLAMA_PID=$! && \
    sleep 8 && \
    ollama pull granite4:350m && \
    kill $OLLAMA_PID && \
    wait $OLLAMA_PID 2>/dev/null || true

# ------------------------------------------------------------
# 10. Startup script
# ------------------------------------------------------------
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# ------------------------------------------------------------
# 11. Switch to student user for runtime
# ------------------------------------------------------------
USER student
WORKDIR /home/student
RUN mkdir -p /home/student/workspace

# Exposed ports:
#   5900  - VNC
#   6080  - noVNC (browser)
#   3001  - TORCS SCR UDP
#   11434 - Ollama REST API
EXPOSE 5900 6080 3001 11434

CMD ["/usr/local/bin/start.sh"]
