#!/usr/bin/env bash
# scripts/run_torcs_lab.sh — bring up the IBM SkillsBuild TORCS lab container
# locally with the VS-Code-extension-install hang patched out.
#
# Problem: docker.io/johnsloe/torcs-competition:amd64 ships /usr/local/bin/start.sh
# which on first boot runs:
#
#   if ! ls "$HOME/.vscode/extensions" 2>/dev/null | grep -q "ms-python.python"; then
#       code --no-sandbox --do-not-sync --install-extension ms-python.python ...
#
# Inside WSL2 the bundled Linux `code` CLI prints "please install VS Code in
# Windows" and hangs the script (RESULTS.md documents the manual recovery via
# `podman exec torcs pkill -f "code.*install-extension"`). We don't edit code
# inside the container — task 1.5 just needs telemetry capture — so pre-create
# the markers the grep looks for and start.sh's "already installed, skipping"
# branch fires on first boot. No image rebuild required.
#
# Usage:
#   scripts/run_torcs_lab.sh                       # interactive, foreground
#
# After the container lands at "Environment ready!", open
# http://localhost:6080/vnc.html in your browser, drive Race → Practice →
# Configure Race → scr_server → Accept → Accept → New Race, then in a second
# terminal:
#
#   podman exec -it torcs bash -lc 'cd /home/student/workspace/gym_torcs && \
#     OVERRIDE_LOG_TELEMETRY=/home/student/workspace/gym_torcs/telemetry/baseline.jsonl \
#     python3 torcs_jm_par.py'
#
# Telemetry path convention — INSIDE the container:
#   /home/student/workspace/gym_torcs/telemetry/<run_id>.jsonl
# ON the host (via the bind mount on /home/student/workspace):
#   $PWD/RaceYourCode/gym_torcs/telemetry/<run_id>.jsonl
# Both must match; the writer's try/except OSError silently swallows
# FileNotFoundError, so a path typo produces zero captures with zero
# visible errors. (Discovered task 1.5 first attempt.)
#
# Permission gotcha: rootless Podman remaps host UID 1000 → container
# UID 0 in the user namespace. Telemetry dir created by the host user
# (patrick, 1000) appears as root-owned in the container, while the
# script runs as user `student` (container UID 1000, falls into "other"
# perms). Without the chmod 0777 below, student can't write. Fix is
# applied to the host dir before the bind-mount so it propagates.
#
# Stop the AI driver with Ctrl-C; quit TORCS via ESC → Quit; stop the
# container with Ctrl-C in this terminal (or `podman stop torcs`).
#
# Architecture choice — bare podman-run (not compose) for task 1.5 because the
# compose stack (Week 3) isn't shipped yet and 1.5 only needs a working TORCS,
# not the full OVERRIDE+TORCS network. Week 3's scripts/torcs_container_init.sh
# applies the same marker-creation fix inside a compose entrypoint override.

set -euo pipefail

# Use namespaced env-var names — bare `NAME` collides with the user's shell
# env (where it's often set to the hostname by default), causing the
# container to land with the wrong name and breaking `podman exec NAME ...`.
IMAGE=${TORCS_IMAGE:-docker.io/johnsloe/torcs-competition:amd64}
TORCS_NAME=${TORCS_NAME:-torcs}
WORKSPACE=${TORCS_WORKSPACE:-${PWD}/RaceYourCode}

# Sanity check — RaceYourCode/gym_torcs must exist so the bind-mount lands
# something useful at /home/student/workspace.
if [[ ! -d "${WORKSPACE}/gym_torcs" ]]; then
    echo "error: ${WORKSPACE}/gym_torcs missing — expected the unzipped lab files." >&2
    echo "run from the repo root, or set WORKSPACE=/path/to/RaceYourCode." >&2
    exit 1
fi

mkdir -p "${WORKSPACE}/gym_torcs/telemetry"
# Rootless Podman remaps host UID 1000 → container UID 0 in the user
# namespace, so the host-created telemetry dir lands as root-owned (755)
# inside the container while the AI driver runs as `student` (container
# UID 1000). chmod 0777 grants "other" write on the host dir, which
# propagates through the bind mount so student can write per-tick JSONL.
# Without this, the writer's try/except OSError silently swallows
# PermissionError → zero captures, zero error messages, easy to miss.
chmod 0777 "${WORKSPACE}/gym_torcs/telemetry"

# Stop any leftover container with the same name (idempotent).
podman rm -f "${TORCS_NAME}" >/dev/null 2>&1 || true

# The fix:
# 1. Pre-create the markers start.sh greps for in step [1/6]. Persist them
#    on the bind-mounted volume so subsequent runs are also fast.
# 2. Set DONT_PROMPT_WSL_INSTALL=1 to suppress any residual WSL prompts.
# 3. Override entrypoint to a bash wrapper that mkdirs the markers, then
#    chains into /usr/local/bin/start.sh (the image's real Cmd).
# Port forwarding rationale:
#   5900       VNC (raw protocol) — drive TORCS from a VNC client
#   6080       noVNC web UI — drive TORCS from a browser, http://localhost:6080
#   3001/udp   SCR — gym_torcs ↔ TORCS server channel for the AI driver
#   11434      Ollama HTTP API — the lab image ships granite4:350m bundled
#              and listens here. Forwarded for *dev convenience*: enables
#              `curl http://localhost:11434/api/tags` from the WSL host (2-second
#              "is Ollama reachable + is granite4:350m loaded?" sanity check),
#              and lets a host-side uvicorn (Week 2 step 2.10 manual gate) hit
#              http://localhost:11434 for the OVERRIDE_LLM_RUNTIME=ollama
#              end-to-end test without exec'ing into the container.
#
# Security note (Week 3 §3.7): on the deployed Hetzner CX32 VM, the cloud
# firewall closes 5900, 6080, 3001/udp, 11434, and 16686 externally — only
# 80/443 (Caddy → 8000) are public. Ollama-over-the-open-internet has no
# auth and would be a takeover vector. The host port forward here exposes
# Ollama on the dev box's loopback only (localhost binds reach localhost).
# Belt-and-suspenders security is fine; security via absence-of-port-forward
# enforced in the wrong abstraction layer (compose YAML) is not.
exec podman run -it --rm \
    --name "${TORCS_NAME}" \
    -p 5900:5900 \
    -p 6080:6080 \
    -p 3001:3001/udp \
    -p 11434:11434 \
    -e DONT_PROMPT_WSL_INSTALL=1 \
    -v "${WORKSPACE}:/home/student/workspace:Z" \
    --entrypoint /bin/bash \
    "${IMAGE}" \
    -c '
set -e
# Convince start.sh the VS Code extensions are already there. The script
# only checks "does a directory named ms-python.python exist under
# ~/.vscode/extensions?" — it does not validate manifests or run code.
mkdir -p "$HOME/.vscode/extensions/ms-python.python" \
         "$HOME/.vscode/extensions/Continue.continue"
# Chain to the lab image'\''s real entrypoint (Entrypoint is None,
# Cmd is ["/usr/local/bin/start.sh"] — confirmed by podman inspect,
# captured in docs/plans/torcs-entrypoint.md during v6 task 1.1).
exec /usr/local/bin/start.sh
'
