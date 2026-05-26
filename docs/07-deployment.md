# Deployment

This runbook covers the `v1.0.0` release branch for the IBM Cloud Ubuntu VM review environment. The goal is a stable hosted deployment where OVERRIDE, TORCS noVNC, and optional TTM-R2 forecasting run on one VM, while Cloudflare controls the public routes.

`dev` remains the WSL/local-development branch. This branch is optimized for Ubuntu 24.04 on the cloud VM.

---

## 1. Target Shape

```
User browser
  |
  | HTTPS
  v
Cloudflare edge
  |
  | outbound tunnel
  v
cloudflared on IBM Cloud VM
  |
  | loopback only
  v
podman-compose stack
  - override :8000
  - torcs noVNC :6080
  - ttm :8001
  - jaeger :16686, optional
```

Routes:

| Hostname | Local target | Access | Purpose |
|---|---|---|---|
| `override.patrickndille.com` | `http://localhost:8000` | Public | Review app: UI, API, upload, sessions, cockpit, Driver Lab |
| `torcs-run.patrickndille.com` | `http://localhost:6080` | Cloudflare Access | noVNC simulator surface for the live cockpit iframe |
| `jaeger.patrickndille.com` | `http://localhost:16686` | Cloudflare Access, optional | Observability proof when tracing is enabled |

Do not publish routes for Ollama, Langflow, raw VNC, SCR UDP, or the TORCS control daemon.

---

## 2. IBM Cloud VM Settings

Use a normal public hourly VM, not a transient instance, for the judging link.

| Setting | Value |
|---|---|
| Type | Public |
| Profile | 4 vCPU / 16 GB RAM |
| Disk | 100 GB boot disk |
| OS | Ubuntu Linux 24.04 LTS Noble Numbat Minimal Install, 64-bit |
| Network | 100 Mbps public/private uplink |
| SSH | Key-based SSH only |

Security group:

- Allow TCP `22` only from the operator IP.
- Do not allow raw public access to `8000`, `6080`, `8001`, `16686`, `7860`, or `11434`.
- Cloudflare Tunnel provides HTTPS access without opening inbound app ports.

---

## 3. Server Bootstrap

```bash
ssh root@<IBM_PUBLIC_IP>

apt update
apt upgrade -y
apt install -y git curl jq ufw podman podman-compose python3-venv build-essential

ufw default deny incoming
ufw default allow outgoing
ufw allow from <YOUR_PUBLIC_IP>/32 to any port 22 proto tcp
ufw enable
```

Clone the release branch:

```bash
mkdir -p /opt
git clone https://github.com/broadcomms/override-may-2026.git /opt/override-may-2026
cd /opt/override-may-2026
git checkout v1.0.0
cp .env.example .env
chmod 600 .env
```

Set production values in `.env`:

```bash
WATSONX_API_KEY=<real_key>
WATSONX_PROJECT_ID=<real_project_id>
WATSONX_URL=https://us-south.ml.cloud.ibm.com
OVERRIDE_UI_ORIGIN=https://override.patrickndille.com
OVERRIDE_LLM_RUNTIME=watsonx
OVERRIDE_KIOSK_MODE=1
OVERRIDE_TRACING=off
TORCS_CONTROL_SECRET=<long_random_secret>
```

Generate the control secret with:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
```

---

## 4. Start The Release Stack

```bash
cd /opt/override-may-2026
podman-compose build override torcs ttm
podman-compose up -d override torcs ttm
```

The cloud release branch removes WSL-only device mounts and forces TORCS through Xvfb + Mesa llvmpipe:

- no `/dev/dxg`
- no `/usr/lib/wsl`
- no `/mnt/wslg`
- no raw host ports for VNC, SCR UDP, Ollama, or the TORCS control daemon

Only loopback ports are bound on the VM:

| Service | Loopback port |
|---|---|
| OVERRIDE | `127.0.0.1:8000` |
| TORCS noVNC | `127.0.0.1:6080` |
| TTM-R2 service | `127.0.0.1:8001` |
| Jaeger, optional | `127.0.0.1:16686` |
| Langflow, operator-only | `127.0.0.1:7860` |

Smoke locally before creating public routes:

```bash
podman ps
curl -fsS http://localhost:8000/api/health | jq .
curl -fsS http://localhost:6080/ >/dev/null
curl -fsS http://localhost:8001/health | jq .
curl -fsS http://localhost:8000/api/torcs/control-status | jq .
```

---

## 5. Cloudflare Tunnel

Install `cloudflared` using Cloudflare's current Linux package instructions, then create a tunnel named `override-ibm-vm`.

Recommended order:

1. Add `override-staging.patrickndille.com -> http://localhost:8000`.
2. Smoke the staging route from an external network.
3. Add `torcs-run.patrickndille.com -> http://localhost:6080`.
4. Put `torcs-run` behind Cloudflare Access before sharing any URL.
5. Move `override.patrickndille.com` to the IBM VM tunnel after staging passes.

Ingress shape:

```yaml
ingress:
  - hostname: override.patrickndille.com
    service: http://localhost:8000
  - hostname: torcs-run.patrickndille.com
    service: http://localhost:6080
  - hostname: jaeger.patrickndille.com
    service: http://localhost:16686
  - service: http_status:404
```

Install the tunnel as a service:

```bash
cloudflared tunnel run override-ibm-vm
# After staging passes, install with the tokenized service command from Cloudflare.
systemctl status cloudflared
```

Cloudflare Access policy for `torcs-run` and optional `jaeger`:

- Application type: Self-hosted.
- Identity provider: One-time PIN.
- Include rule: approved operator/reviewer email addresses.
- Session duration: 24 hours.
- Default: deny everyone else.

Add a Cloudflare WAF/rate-limit rule for `POST /api/sessions`, around 5 requests per minute per IP, to cap watsonx burn from public uploads.

---

## 6. Runtime Persistence

Create a systemd unit:

```ini
# /etc/systemd/system/override-compose.service
[Unit]
Description=OVERRIDE compose stack
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/override-may-2026
ExecStart=/usr/bin/podman-compose up -d override torcs ttm
ExecStop=/usr/bin/podman-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
systemctl daemon-reload
systemctl enable --now override-compose
systemctl status override-compose
```

After compose starts, set restart policy on the long-lived containers:

```bash
podman update --restart=always override torcs override-ttm
```

---

## 7. Live TORCS Acceptance

Browser flow:

1. Open `https://override.patrickndille.com`.
2. Open `/upload` and confirm Race Control is visible.
3. Start a `cockpit_practice` run.
4. If Cloudflare Access blocks the iframe, click `Open simulator surface`, authenticate on `torcs-run`, then return to the cockpit.
5. Confirm `/cockpit` displays the TORCS noVNC frame.
6. Confirm timing state, hybrid rail, and telemetry update after the first closed lap.
7. Stop the run, then ingest the generated TORCS capture from the upload page.
8. Confirm Engineer reasoning, Fan Mode, validation, and counterfactual strategy review still work.

CLI checks:

```bash
curl -fsS https://override.patrickndille.com/api/health | jq .
curl -s -o /dev/null -w "torcs-run: %{http_code}\n" https://torcs-run.patrickndille.com/
podman exec torcs sh -c 'ls -lh /home/student/workspace/gym_torcs/telemetry | tail'
```

Expected:

- `override` returns `200`.
- `torcs-run` redirects to Cloudflare Access until authenticated.
- Telemetry JSONL appears in the shared volume after a live run.

---

## 8. Optional Jaeger Proof

Only enable when capturing observability evidence:

```bash
sed -i 's/^OVERRIDE_TRACING=.*/OVERRIDE_TRACING=otlp/' .env
podman-compose up -d override jaeger
podman-compose up -d --force-recreate override
```

Expose `jaeger.patrickndille.com` only behind Cloudflare Access. Turn tracing back off after capture:

```bash
sed -i 's/^OVERRIDE_TRACING=.*/OVERRIDE_TRACING=off/' .env
podman-compose up -d --force-recreate override
```

---

## 9. Rollback

If the cloud release branch has a deployment issue:

1. Keep `https://override-video.patrickndille.com` unchanged; the product video remains the canonical review artifact.
2. Move `override.patrickndille.com` back to the previous known-good tunnel/origin if available.
3. Keep `dev` untouched for local WSL development.
4. Use the README local-clone path as the fallback review route.

Do not force-push `dev` or rewrite `main` to recover the VM. Fix `v1.0.0` directly or create a follow-up release branch from it.
