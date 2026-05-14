# Deployment

OVERRIDE ships in two shapes:

1. **Local** — `podman compose up` against the repo. Default path; documented in [`README.md`](../README.md). What judges experience when they clone the repo.
2. **Ephemeral hosted demo** — a **Cloudflare Tunnel** from a local WSL2 host, exposing the compose stack on a subdomain of `patrickndille.com` for the IBM SkillsBuild judging window (May 27 – May 31, 2026). Single-purpose, route-revoke post-May-31, **not a production deployment.**

The hosted demo is convenience, not the architectural promise. Per the v6 plan cuts list, item #4 is "skip cloud-VM provisioning; README-only deploy with `podman compose up` on a local machine." Strongly preferred but not in the hard floor.

This document is the runbook for the Cloudflare Tunnel deployment (v6 plan §3.7, amended).

> **History.** v6 plan §3.7 originally specified a Hetzner CX32 VM (~$3 for the judging window). The post-pre-flight pivot is to **Cloudflare Tunnel from local WSL** — $0 cost, automatic TLS at the Cloudflare edge, no SSH key management, no UFW config, tear-down is revoking tunnel routes. The trade-off is **availability tracks the local laptop's uptime** (mitigated via `--restart=always`, no-sleep settings, and the local-clone fallback in README).

---

## §1 — Architecture

```
┌──────────────────────┐        ┌─────────────────────┐        ┌────────────────────┐
│ Judge's browser      │  HTTPS │ Cloudflare edge     │  WSS   │ cloudflared daemon │
│ override.patrick…    │───────▶│ (TLS termination,   │───────▶│ on local WSL2      │
│ torcs.patrick…       │        │ Access policies)    │        │ (rootless tunnel)  │
│ jaeger.patrick…      │        └─────────────────────┘        └─────────┬──────────┘
└──────────────────────┘                                                  │ loopback
                                                                          ▼
                                       ┌──────────────────────────────────────────────┐
                                       │ Podman compose stack (override-net)          │
                                       │  override :8000   torcs :6080/:11434/:3001   │
                                       │  jaeger   :16686  langflow :7860             │
                                       └──────────────────────────────────────────────┘
```

Routes (in the Cloudflare dashboard → Zero Trust → Networks → Tunnels → `torcs` → Public Hostnames).

> **Currently live in v1.0: `override.patrickndille.com` only.** The table below documents the route topology pattern; additional gated routes can be added by extending the Cloudflare Tunnel configuration with Access policies as shown in §3. The torcs/jaeger/ollama/langflow rows below are reference for anyone wanting to expand the deployment — they are NOT live on the v1 submission.

| Subdomain | → Local service | Auth | Purpose |
|---|---|---|---|
| `override.patrickndille.com` | `http://localhost:8000` | **Public** | The demo. UI + API. |
| `torcs.patrickndille.com` | `http://localhost:6080` | **Cloudflare Access** (email allowlist) | Optional "drive TORCS yourself" affordance for curious judges. |
| `jaeger.patrickndille.com` | `http://localhost:16686` | **Cloudflare Access** (email allowlist) | Observability proof. Same gate as torcs. |
| ~~`ollama.patrickndille.com`~~ | ~~`http://localhost:11434`~~ | **Route deleted** | No legitimate external consumer; OVERRIDE reaches Ollama internally via the compose network at `http://torcs:11434`. |
| ~~`langflow.patrickndille.com`~~ | ~~`http://localhost:7860`~~ | **Route deleted** | Out of v1 scope. Langflow is a profile-gated compose service (`podman compose --profile langflow up langflow`); it runs locally for design-canvas work and is intentionally not tunneled. |

---

## §2 — Why two routes are gated and two are deleted

⚠️ **noVNC, Jaeger, Ollama, and Langflow all ship with NO authentication by default.** Cloudflare Tunnel by itself just brings the surface to the public internet — it does not add auth. Without further config, any of these four subdomains hands a stranger an unauthenticated admin interface.

Risk shape:

| Subdomain | What an unauth visitor gets | Mitigation chosen |
|---|---|---|
| `override` (`:8000`) | Read-only-ish FastAPI + UI; watsonx calls (cost lever, no privilege escalation). Single-user replay-first per [`docs/05-security.md`](./05-security.md). | **Public** — the demo. Only "cost" is watsonx burn, capped by the CA$10 Essentials budget alerts. |
| `torcs` (`:6080`) | Full remote desktop into the TORCS container. Anyone can drive the sim, change container state, and depending on container escape vectors, potentially reach the host. | **Gated** — Cloudflare Access with email allowlist. |
| `jaeger` (`:16686`) | All trace content: prompt text, model IDs, request timing, internal pipeline shape. Information disclosure. | **Gated** — same Access policy. |
| `ollama` (`:11434`) | Free unmetered LLM inference for anyone who finds the subdomain. Even with Cloudflare Access, an authenticated visitor has full inference. No legitimate use case for external access. | **Route deleted entirely.** |
| `langflow` (`:7860`) | Visual flow editor with arbitrary-tool execution. Out of v1 demo scope. | **Route deleted entirely.** |

**Subdomain enumeration is trivial** — once `override.patrickndille.com` is in the BeMyApp portal, `crt.sh`, `subfinder`, and a 5-second guess at sibling names will surface the others. There is no security-through-obscurity here.

### Cloudflare Access policy setup (~5 min per gated subdomain)

1. Cloudflare dashboard → **Zero Trust** → **Access** → **Applications** → **Add an application** → **Self-hosted**.
2. **Application domain**: e.g. `torcs.patrickndille.com`.
3. **Session duration**: 24 hours (judging window is 5 days; 24h is the sweet spot — re-auth once per day, no perpetual sessions).
4. **Identity providers**: enable **One-time PIN** (zero setup; judges enter their email, get a code, click through). Add specific email allowlist as judges are confirmed.
5. **Policies → Add a policy → Include → Emails**: `your@email.com` (+ any allowlisted testers / judges as they're known). Allow that one rule; deny all else.
6. Save. The subdomain now redirects unauthenticated visitors to Cloudflare's Access auth page before proxying to localhost.

### Optional but recommended: Cloudflare WAF on `override`

For the public route, add a basic WAF rule at the zone level: rate-limit `POST /api/sessions` to ~5 req/min/IP. Caps the watsonx burn surface in the worst case (someone scripting fixture uploads). Free-tier WAF rules cover this.

---

## §3 — Runbook (mechanical, ~30 min start-to-public)

Pre-flight: Cloudflare account on the `patrickndille.com` zone, the local WSL2 box running with Podman 4.4+, and `WATSONX_API_KEY` + `WATSONX_PROJECT_ID` in `.env`.

```bash
# ── 1. Install cloudflared (WSL2 Ubuntu 24.04) ────────────────────────────
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
cloudflared --version    # expect 2024.x+

# ── 2. Authenticate cloudflared against the Cloudflare account ────────────
cloudflared tunnel login
# Opens a browser → pick the patrickndille.com zone → cert.pem written to
# ~/.cloudflared/cert.pem

# ── 3. Create the tunnel (one-time) ───────────────────────────────────────
cloudflared tunnel create torcs
# Outputs a tunnel UUID + writes ~/.cloudflared/<UUID>.json with credentials.
# Record the UUID; the dashboard refers to it by name ("torcs") but config
# files use the UUID.

# ── 4. Configure tunnel routes ────────────────────────────────────────────
# Easiest path: Cloudflare dashboard → Zero Trust → Networks → Tunnels
# → torcs → Public Hostnames → Add three:
#   override.patrickndille.com → http://localhost:8000
#   torcs.patrickndille.com    → http://localhost:6080
#   jaeger.patrickndille.com   → http://localhost:16686
# Do NOT add ollama or langflow routes (per §2).

# OR via CLI (~/.cloudflared/config.yml):
cat > ~/.cloudflared/config.yml <<EOF
tunnel: <UUID-from-step-3>
credentials-file: /home/$USER/.cloudflared/<UUID>.json
ingress:
  - hostname: override.patrickndille.com
    service: http://localhost:8000
  - hostname: torcs.patrickndille.com
    service: http://localhost:6080
  - hostname: jaeger.patrickndille.com
    service: http://localhost:16686
  - service: http_status:404      # catch-all (required)
EOF

# ── 5. Add Cloudflare Access policies for torcs + jaeger ──────────────────
# Dashboard path is the only sane way — see §2 above. Create one self-hosted
# application per gated subdomain, one-time-PIN, email allowlist.

# ── 6. Bring up the compose stack ─────────────────────────────────────────
cd ~/overdrive-may-2026
cp .env.example .env       # or edit existing — watsonx creds + OVERRIDE_TRACING=otlp
podman compose up -d override                   # public demo path
podman compose up -d override torcs             # if torcs subdomain is in routes
podman compose up -d override jaeger            # if jaeger subdomain is in routes
# Verify each service responds on its loopback port BEFORE starting the tunnel.

# ── 7. Start cloudflared as a systemd service ─────────────────────────────
# Persistent, auto-restart on failure, survives WSL reboot:
sudo cloudflared service install     # installs to /etc/systemd/system/
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared    # expect "active (running)"

# Alternative (ephemeral foreground, for testing):
# cloudflared tunnel run torcs

# ── 8. Smoke from outside the local network ───────────────────────────────
# From a phone on cellular or a different machine:
curl -sf https://override.patrickndille.com/api/health | jq .
# Expected: {"status":"ok",...}

# Gated subdomains should 302 to the Access auth page, NOT 200:
curl -s -o /dev/null -w "torcs:  %{http_code}\n"  https://torcs.patrickndille.com/
curl -s -o /dev/null -w "jaeger: %{http_code}\n"  https://jaeger.patrickndille.com/
# Expected: 302 each (redirect to Cloudflare Access).

# ── 9. Operational hardening for the judging window ───────────────────────
# Container restart policy — survive Podman / compose failures:
podman update --restart=always override torcs jaeger

# Windows-side: disable sleep on the host machine for May 24-31.
# Settings → System → Power → Screen and sleep → Never (while plugged in).

# WSL config: ~/.wslconfig on the Windows side, keep memory + processors stable.

# ── 10. Paste the URL into the BeMyApp portal copy ────────────────────────
# Edit docs/plans/submission-portal-copy.md §9 — the row already accommodates
# the Cloudflare URL. Final paste happens at T-2h on May 31.
```

**Decisions recorded** (fill at deploy time):

```
Tunnel UUID:             ____________________
cloudflared service:     [ ] systemd  [ ] foreground (NOT for judging window)
Routes published:        [ ] override  [ ] torcs (gated)  [ ] jaeger (gated)
                         [ ] ollama (deleted)  [ ] langflow (deleted)
Access policy emails:    ____________________
WAF rate limit on /api/sessions:  [ ] yes (5 req/min/IP)  [ ] skipped
External smoke pass:     [ ] override 200  [ ] torcs 302  [ ] jaeger 302
--restart=always set:    [ ] yes
Host no-sleep set:       [ ] yes
```

---

## §4 — Volume-permission re-verify

Same shape as before — the named-volume + bind-mount layout the compose stack uses works identically whether the tunnel is up or not. The named volume `torcs-telemetry` shadows the bind-mount path at `/home/student/workspace/gym_torcs/telemetry/` inside the `torcs` container.

```bash
podman compose up -d override torcs
podman exec torcs sh -c "touch /home/student/workspace/gym_torcs/telemetry/__test.txt"
podman exec override sh -c "cat /app/data/telemetry/__test.txt && echo OK"
podman exec torcs rm /home/student/workspace/gym_torcs/telemetry/__test.txt
```

If permission-denied: confirm the `user: "0:0"` workaround is still on the `torcs` service in `docker-compose.yml`. The named volume + root-writes posture is the working state from local 3.1 smoke.

**Data on host** lives at `~/.local/share/containers/storage/volumes/overdrive-may-2026_torcs-telemetry/_data/` — extract for offline inspection with:

```bash
cp ~/.local/share/containers/storage/volumes/overdrive-may-2026_torcs-telemetry/_data/baseline.jsonl ./baseline.jsonl
head -2 baseline.jsonl | jq
```

---

## §5 — Local-dev redeploy loop (Phase G capture)

Quick reference for iterating on the code locally while the tunnel is up. The Cloudflare side stays connected; you just bounce the override container:

```bash
# After editing api/, core/, ingest/, analysis/:
podman compose build override                   # rebuild image
podman compose up -d --force-recreate override  # recreate so env_file + new image apply

# After editing ui/:
cd ui && npm run build && cd ..                 # rebuild static bundle
podman compose up -d --force-recreate override  # static bundle is COPYed into the image

# Clean rebuild (no layer cache — use after dependency changes):
podman compose build --no-cache override

# Inspect image size growth between rebuilds:
podman images override --format "table {{.Repository}}\t{{.Tag}}\t{{.CreatedSince}}\t{{.Size}}"

# Prune dangling layers after multiple rebuilds:
podman image prune -f
```

**`podman restart` vs `podman compose up -d --force-recreate`** — `podman restart` reuses the container's existing env; new `.env` values are NOT picked up. Always use `--force-recreate` after editing `.env` or any env_file-referenced variable.

---

## §6 — Tear-down

Run on **2026-06-01** or earlier (post-judging, post-portal-confirmation).

```bash
# Stop the tunnel
sudo systemctl stop cloudflared
sudo systemctl disable cloudflared
# Delete the tunnel (irreversible — credentials become invalid):
cloudflared tunnel delete torcs

# In Cloudflare dashboard:
# • Zero Trust → Access → Applications → delete torcs + jaeger applications
# • DNS → delete the override / torcs / jaeger CNAME records (auto-created by
#   cloudflared but linger after tunnel delete)

# Local containers + volumes
cd ~/overdrive-may-2026
podman compose down -v        # drops torcs-telemetry named volume + langflow-data
# Repo can stay; it's the canonical local-clone path going forward.

# Disable host no-sleep + WSL --restart=always tweaks if you want laptop back to normal.
```

Total cost projection over the 19-day build + judging window:

| Line | Amount |
|---|---|
| Cloudflare Tunnel | **$0** (free tier; one zone, three routes, two Access policies, well under all limits) |
| Cloudflare WAF rule (optional) | **$0** (free-tier zone rules) |
| watsonx.ai burn (CA$10 budget alerts on Runtime + Studio) | ~$1–10 |
| **Total** | **~$1–10 USD** |

vs the original Hetzner CX32 plan at ~$3–13 USD. Net savings ~$3 + ~1.5h of provisioning friction.

---

## §7 — Operational resilience

The trade-off vs a hosted VM is **availability tracks the laptop**, not a datacenter.

**Single-laptop failure modes for the 4–5 day judging window**:

| Risk | Mitigation |
|---|---|
| Laptop sleeps | Windows → Power → Screen and sleep → Never (plugged in). For May 24–31. |
| Containers crash | `podman update --restart=always override torcs jaeger` in Step 9. |
| cloudflared crashes | `systemctl enable --now cloudflared` in Step 7 — auto-restart on failure. |
| WSL kernel hang | Rare. Recovery: `wsl --shutdown` then `wsl` from PowerShell, then re-run `podman compose up -d`. Tunnel re-connects automatically. |
| Power outage / network outage | No mitigation — falls back to README local-clone path. Judges still see a fully-reproducible local demo. |

**Fallback that doesn't cost more**: the README's local-clone Quickstart works regardless of the hosted URL. The portal copy explicitly states this: "OVERRIDE runs locally via `podman compose up` — see README. The hosted URL is convenience, not the architectural promise." If `override.patrickndille.com` goes dark mid-judging, the rubric story is unchanged.

**Paranoid fallback** (skip unless nervous): spin up a Hetzner CX22 for $0.50/window with the same compose stack and a second Cloudflare Tunnel pointing to it as `backup.override.patrickndille.com`. Swap the BeMyApp URL in 30 seconds if primary dies. Realistically: unnecessary for a 4-day window.
