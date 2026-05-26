# Cloud VM Go-Live Checklist

Use this as the short operator checklist for the `v1.0.0` IBM Cloud release branch. The full runbook is `docs/07-deployment.md`.

## Cloud Instance

| Item | Value |
|---|---|
| Type | Public hourly VM, not Transient |
| Profile | 4 vCPU, 16 GB RAM |
| Disk | 100 GB |
| OS | Ubuntu Linux 24.04 LTS Noble Numbat Minimal Install, 64-bit |
| Network | 100 Mbps public/private uplink |

Only SSH should be reachable on the raw IBM public IP, limited to the operator IP. OVERRIDE and TORCS should be exposed through Cloudflare Tunnel.

## Branch Strategy

| Branch | Role |
|---|---|
| `main` | Stable public project branch |
| `dev` | Local WSL development branch |
| `v1.0.0` | IBM Cloud VM release branch |

Do not tag the release unless the project owner explicitly asks for a tag.

## Runtime Shape

```bash
git clone https://github.com/broadcomms/override-may-2026.git /opt/override-may-2026
cd /opt/override-may-2026
git checkout v1.0.0
cp .env.example .env
```

Required `.env` values:

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

Start:

```bash
podman-compose build override torcs
podman-compose up -d override torcs
```

If UFW is enabled, allow Podman bridge DNS and container-to-container routing:

```bash
PODMAN_IFACE=$(podman network inspect override-may-2026_override-net | jq -r '.[0].network_interface')
PODMAN_SUBNET=$(podman network inspect override-may-2026_override-net | jq -r '.[0].subnets[0].subnet')
PODMAN_GATEWAY=$(podman network inspect override-may-2026_override-net | jq -r '.[0].subnets[0].gateway')

ufw allow in on "$PODMAN_IFACE" from "$PODMAN_SUBNET" to "$PODMAN_GATEWAY" port 53 proto udp
ufw allow in on "$PODMAN_IFACE" from "$PODMAN_SUBNET" to "$PODMAN_GATEWAY" port 53 proto tcp
ufw route allow in on "$PODMAN_IFACE" out on "$PODMAN_IFACE" from "$PODMAN_SUBNET" to "$PODMAN_SUBNET"
ufw reload
```

## Routes

| Hostname | Target | Access |
|---|---|---|
| `override.patrickndille.com` | `http://localhost:8000` | Public |
| `torcs-run.patrickndille.com` | `http://localhost:6080` | Cloudflare Access |
| `jaeger.patrickndille.com` | `http://localhost:16686` | Cloudflare Access, optional |

Do not route:

- raw VNC `5900`
- SCR UDP `3001`
- Ollama `11434`
- TORCS control daemon `7000`
- Langflow `7860`

## Smoke Checks

```bash
podman ps
curl -fsS http://localhost:8000/api/health | jq .
curl -fsS http://localhost:6080/ >/dev/null
curl -fsS http://localhost:8001/health | jq .
curl -fsS http://localhost:8000/api/torcs/control-status | jq .
curl -fsS https://override.patrickndille.com/api/health | jq .
```

Browser acceptance:

- `/upload` shows Race Control.
- Start Race works in `cockpit_practice`.
- `/cockpit` displays the noVNC TORCS frame.
- If Cloudflare Access blocks the iframe, open `torcs-run.patrickndille.com` once, authenticate, then return to `/cockpit`.
- Telemetry appears and can be ingested through `POST /api/sessions/torcs-live`.
