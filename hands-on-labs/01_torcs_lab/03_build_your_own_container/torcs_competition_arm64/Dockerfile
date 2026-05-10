# ============================================================
# Dockerfile: Ubuntu + TORCS (with SCR patch) + VS Code
#             + Ollama + IBM Granite 4.0 350M
# For use in AI-driven car racing competitions
#
# Build:  podman build -t torcs-competition .
#
# Run:    podman run -it --rm \
#           -p 5900:5900 \            # VNC
#           -p 6080:6080 \            # noVNC (browser access)
#           -p 3001:3001/udp \            # TORCS SCR UDP port
#           -v ~/RaceYourCode:/home/student/workspace:Z \
#           torcs-competition
#
# NOTE:   Students mount their local RaceYourCode folder which
#         contains the gym_torcs starter kit and their own code.
#         Nothing is baked into /home/student/workspace in this image.
#
# GPU:    podman run -it --rm --device nvidia.com/gpu=all \
#           -p 5900:5900 -p 6080:6080 -p 3001:3001 \
#           -v ~/RaceYourCode:/home/student/workspace:Z \
#           torcs-competition
#
# Access the desktop via browser at: http://localhost:6080/vnc.html
# ============================================================

FROM docker.io/library/ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Ollama model storage path and host binding
ENV OLLAMA_MODELS=/opt/ollama/models
ENV OLLAMA_HOST=0.0.0.0:11434

# ------------------------------------------------------------
# 1. System dependencies
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y \
    # Build tools
    build-essential \
    cmake \
    git \
    wget \
    curl \
    unzip \
    sudo \
    zstd \
    # TORCS dependencies
    libglib2.0-dev \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    freeglut3-dev \
    libpng-dev \
    libjpeg-dev \
    libopenal-dev \
    libalut-dev \
    libvorbis-dev \
    libxi-dev \
    libxmu-dev \
    libxrender-dev \
    libxrandr-dev \
    libxxf86vm-dev \
    libplib-dev \
    # Virtual display & VNC
    xvfb \
    x11vnc \
    xfce4 \
    xfce4-terminal \
    dbus-x11 \
    # noVNC for browser-based access
    novnc \
    websockify \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    # Misc utilities
    net-tools \
    iputils-ping \
    nano \
    vim \
    xdg-utils \
    # Required by gym-TORCS autostart.sh to automate TORCS GUI
    xautomation \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# 2. Create a non-root student user
# ------------------------------------------------------------
RUN useradd -m -s /bin/bash student && \
    echo "student:student" | chpasswd && \
    usermod -aG sudo student && \
    echo "student ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# ------------------------------------------------------------
# 3. Install VS Code (official Microsoft .deb)
# ------------------------------------------------------------
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then \
    wget -qO /tmp/vscode.deb "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-arm64"; \
    else \
    wget -qO /tmp/vscode.deb "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64"; \
    fi && \
    apt-get install -y /tmp/vscode.deb && \
    rm /tmp/vscode.deb && \
    apt-get clean

# ------------------------------------------------------------
# 4. Install VS Code extensions as the student user
#    - Python extension
#    - Continue.dev (AI code assistant, connects to local Ollama)
# ------------------------------------------------------------
USER student
RUN code --install-extension ms-python.python --force && \
    code --install-extension Continue.continue --force
USER root

# ------------------------------------------------------------
# 5. Configure VS Code settings and Continue.dev for Granite
# ------------------------------------------------------------
# VS Code settings
RUN mkdir -p /home/student/.config/Code/User && \
    cat > /home/student/.config/Code/User/settings.json << 'EOF'
{
    "editor.inlineSuggest.enabled": true,
    "python.defaultInterpreterPath": "/usr/bin/python3",
    "python.analysis.typeCheckingMode": "basic"
}
EOF
RUN chown -R student:student /home/student/.config

# Continue.dev config — points at local Ollama serving Granite 4.0 350M
# This file is read by the Continue.dev extension at startup
RUN mkdir -p /home/student/.continue && \
    cat > /home/student/.continue/config.json << 'EOF'
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
RUN chown -R student:student /home/student/.continue

# ------------------------------------------------------------
# 6. Build and install TORCS 1.3.7 from source
# ------------------------------------------------------------
WORKDIR /opt
RUN git clone https://github.com/fmirus/torcs-1.3.7.git torcs-src

WORKDIR /opt/torcs-src
RUN ./configure --prefix=/usr/local/torcs && \
    make && \
    make install && \
    make datainstall

ENV TORCS_HOME=/usr/local/torcs
ENV PATH="$TORCS_HOME/bin:$PATH"

# ------------------------------------------------------------
# 7. SCR server patch is already included in torcs-1.3.7
#    The UDP socket interface on port 3001 is built-in
# ------------------------------------------------------------

# ------------------------------------------------------------
# 7a. Copy pre-made formula/car design into TORCS drivers folder
#     scr_server.zip must be in the same folder as this Dockerfile
# ------------------------------------------------------------
COPY scr_server.zip /tmp/scr_server.zip
RUN unzip -o /tmp/scr_server.zip -d /usr/local/torcs/share/games/torcs/drivers/ && \
    rm -rf /usr/local/torcs/share/games/torcs/drivers/__MACOSX && \
    find /usr/local/torcs/share/games/torcs/drivers/ -name ".DS_Store" -delete && \
    rm /tmp/scr_server.zip

# ------------------------------------------------------------
# 8. Python packages for student AI agents
# ------------------------------------------------------------
RUN pip3 install --no-cache-dir \
    numpy \
    scipy \
    scikit-learn \
    torch \
    tensorflow \
    keras \
    gymnasium \
    matplotlib \
    pandas

# ------------------------------------------------------------
# 9. Install Ollama
# ------------------------------------------------------------
RUN curl -fsSL https://ollama.com/install.sh | sh

# ------------------------------------------------------------
# 10. Pre-pull IBM Granite 4.0 350M and bake into the image
#     Ollama is started temporarily just to perform the pull,
#     then shut down. The model files remain in $OLLAMA_MODELS.
# ------------------------------------------------------------
RUN mkdir -p $OLLAMA_MODELS && \
    ollama serve & \
    OLLAMA_PID=$! && \
    sleep 8 && \
    ollama pull granite4:350m && \
    kill $OLLAMA_PID && \
    wait $OLLAMA_PID 2>/dev/null || true

# ------------------------------------------------------------
# 11. Startup script
# ------------------------------------------------------------
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# ------------------------------------------------------------
# 12. Switch to student user for runtime
# ------------------------------------------------------------
USER student
WORKDIR /home/student
RUN mkdir -p /home/student/workspace

# Ports:
#   5900  - VNC
#   6080  - noVNC (browser)
#   3001  - TORCS SCR UDP
#   11434 - Ollama REST API
EXPOSE 5900 6080 3001/udp 11434

CMD ["/usr/local/bin/start.sh"]
