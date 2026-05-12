# Deployment

OVERRIDE ships in two shapes:

1. **Local** — `podman compose up` against the repo. Default path; documented in [`README.md`](../README.md). What judges experience when they clone the repo.
2. **Ephemeral hosted demo** — a Hetzner Cloud CX32 VM standing up the same compose stack for the IBM SkillsBuild judging window (May 27 – May 31, 2026). Single-purpose, tear-down post-May-31, **not a production deployment.**

The hosted demo is convenience, not the architectural promise. Per the v6 plan cuts list, item #4 is "skip cloud-VM provisioning; README-only deploy with `podman compose up` on a local machine." Strongly preferred but not in the hard floor.

This document is the runbook for the ephemeral VM dry-run (v6 plan §3.7).

---

## §1 — VM size and OS

| Property | Value | Rationale |
|---|---|---|
| Provider | Hetzner Cloud | Cheap, fast provisioning, ~$0.013/h prorated billing |
| Size | **CX32** — 4 vCPU / 8 GB RAM / 80 GB NVMe | Handles the 10 GB TORCS lab image + everything else with margin. CX22 would have been default-profile-only — no `--profile torcs` headroom. |
| OS | **Ubuntu 24.04 LTS** | Ships Podman 4.9.x, matches the WSL dev shape (gotcha #7 pasta-networking fix needs 4.4+) |
| Cost | ~$11.40/mo prorated → **~$1.50–2 for the 4–5 day judging window** | Plus snapshot ~$1 → total ~$3–4 USD |

If Hetzner pricing or availability shifts, equivalent VMs work — minimum spec: **4 vCPU / 8 GB / Ubuntu 22.04+ / Podman 4.4+**.

---

## §2 — Firewall rules

⚠️ **noVNC has no authentication.** Exposing port 6080 publicly is a takeover vector. The hosted demo URL is fixture-only; the live TORCS drive path is intentionally not exposed.

| Port | Protocol | External | Reason |
|---|---|---|---|
| **22** | TCP | **OPEN** | SSH only — operator access |
| **80** | TCP | **OPEN** | Caddy → 8000 (or direct if TLS skipped) |
| **443** | TCP | **OPEN** (only if Caddy issues a cert) | Caddy → 8000 |
| 8000 | TCP | CLOSED | OVERRIDE API — reached internally via 80/443 |
| 5900 | TCP | CLOSED | VNC — operator SSH-tunnel only |
| **6080** | TCP | **CLOSED** | noVNC — auth-less; SSH-tunnel only |
| 3001 | UDP | CLOSED | SCR (gym_torcs ↔ TORCS server) — intra-pod |
| 11434 | TCP | CLOSED | Ollama HTTP — intra-pod |
| 16686 | TCP | CLOSED | Jaeger UI — operator SSH-tunnel only |

Apply on the VM with `ufw`:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Also configure Hetzner's network-edge firewall to match (defense in depth). Operator access to noVNC / Jaeger UI:

```bash
ssh -L 6080:localhost:6080 -L 16686:localhost:16686 user@vm
```

README documents this explicitly so judges aren't surprised:

> The hosted demo URL exposes the fixture-driven path only. Judges who want to drive live TORCS clone the repo and `podman compose --profile torcs up` locally.

---

## §3 — TLS choice

The 4–5 day demo on a single-purpose ephemeral VM does not justify the cost/complexity of a production-grade TLS setup. Three branches, in preference order:

### Branch A — Skip TLS (fastest, 0 min)

Judges access `http://<vm-public-ip>:8000` directly. HTTP-not-HTTPS is acceptable for a hackathon submission; the rubric scores architecture, not certificate management. Edit `docker-compose.yml` to publish `80:8000` (one line: `ports: ["80:8000"]` on the `override` service) and skip Caddy entirely.

### Branch B — DuckDNS + Caddy (recommended if URL aesthetics matter, ~10–30 min)

Polished URL like `override-demo.duckdns.org`. Steps:

```bash
# On the VM
sudo apt-get install -y caddy
# Point override.duckdns.org's A record at the VM IP via duckdns.org's web UI

# Foreground / ephemeral Caddy:
caddy reverse-proxy --from override.duckdns.org --to localhost:8000

# OR (more durable) a minimal Caddyfile in ~/Caddyfile:
cat > ~/Caddyfile <<'EOF'
override.duckdns.org {
    reverse_proxy localhost:8000
}
EOF
caddy run --config ~/Caddyfile
```

Caddy auto-issues Let's Encrypt certs on first request. **Typical time when DNS propagates fast and the HTTP-01 challenge succeeds first try: ~10 min.** Worst case (slow DNS, challenge retries): ~30 min. Cert re-acquires on Caddy restart (rate-limited but fine for a 4–5 day window); a proper systemd unit + persistent Caddyfile is v1.1.

### Branch C — Fallback (cert challenge fails)

Ship `http://<vm-public-ip>:8000` directly (Branch A). Covers any DNS / cert hiccup without slipping the 1.5h dry-run budget.

**Decision recorded at dry-run time**: [ ] Branch A — skip TLS &nbsp;&nbsp; [ ] Branch B — DuckDNS+Caddy succeeded &nbsp;&nbsp; [ ] Branch C — Caddy failed, fell back

---

## §4 — Runbook (mechanical, ~1.5h start-to-snapshot)

Pre-flight: have Hetzner Cloud credentials, an SSH public key, and `WATSONX_API_KEY` + `WATSONX_PROJECT_ID` ready.

```bash
# ── 0. Provision (in Hetzner Cloud console or via hcloud CLI) ──────────────
# • Image: Ubuntu 24.04
# • Type: CX32
# • Location: nbg1 or fsn1 (EU) — closest to the operator/judges
# • SSH key: paste public key
# • Firewall: optionally pre-bind a Hetzner firewall matching §2

# ── 1. SSH in + harden ────────────────────────────────────────────────────
ssh root@<vm-ip>
adduser deploy && usermod -aG sudo deploy
# Copy operator's SSH key into /home/deploy/.ssh/authorized_keys
# Then re-login as deploy and disable root SSH
exit
ssh deploy@<vm-ip>

# ── 2. Linger so containers survive SSH disconnect (gotcha #11) ───────────
sudo loginctl enable-linger $USER
cat /etc/subuid /etc/subgid    # verify range listed; missing → run:
# sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 $USER && podman system migrate

# ── 3. Install deps ───────────────────────────────────────────────────────
sudo apt-get update
sudo apt-get install -y podman git ufw curl
# Verify Podman 4.4+:
podman --version

# If `podman compose version` is missing (V2 plugin not bundled in this Ubuntu image):
sudo apt-get install -y python3-pip
pip install --user podman-compose      # the v1.0.6 path used during local smoke

# ── 4. Apply firewall (per §2) ────────────────────────────────────────────
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable && sudo ufw status verbose

# ── 5. Clone + configure ──────────────────────────────────────────────────
git clone https://github.com/<user>/overdrive-may-2026.git
cd overdrive-may-2026
cp .env.example .env
# Edit .env — paste WATSONX_API_KEY + WATSONX_PROJECT_ID + WATSONX_URL (us-south)

# ── 6. Bring up the default profile (fixture-driven demo path) ────────────
podman compose up -d
# Wait ~30s, then:
curl -fsS http://localhost:8000/api/health
# Expected: {"status":"ok",...}

# ── 7. Smoke: upload a fixture end-to-end ─────────────────────────────────
curl -fsS -X POST http://localhost:8000/api/sessions \
  -F "file=@data/sessions/sample_torcs.json;type=application/json" \
  -F "source=torcs" \
  | head -c 200      # expect a Session JSON payload

# ── 8. Optional: bring up live-TORCS path (first pull ~10–15 min) ─────────
# Skip this if cuts list item #4 is firing OR if VM disk space is tight.
podman compose --profile torcs up -d
podman logs torcs --tail 30      # watch for "[6/6] All services started"
# Verify noVNC desktop via SSH tunnel from a separate terminal:
#   ssh -L 6080:localhost:6080 deploy@<vm-ip>
#   open http://localhost:6080 in browser

# ── 9. Apply TLS branch per §3 ─────────────────────────────────────────────
# Branch A: edit compose to publish 80:8000 instead of 8000:8000, redeploy
# Branch B: caddy reverse-proxy --from override.duckdns.org --to localhost:8000
# Branch C: do nothing — judges hit http://<vm-ip>:8000

# ── 10. Snapshot (review #6 — disaster recovery) ──────────────────────────
# Hetzner Cloud console → VM → Create snapshot
# Cost: ~$0.012/GB/month → ~$1 for the window
# Record snapshot ID below.

# ── 11. Fresh-clone smoke (T-72h pre-flight equivalent) ───────────────────
cd ~
git clone /home/deploy/overdrive-may-2026 /tmp/override-fresh
cd /tmp/override-fresh
podman compose up -d
curl -fsS http://localhost:8000/api/health
# If green: tear down /tmp/override-fresh (it was just the smoke).
podman compose down -v
rm -rf /tmp/override-fresh

# ── 12. Done — paste the URL into docs/plans/submission-portal-copy.md §9 ─
```

**Decisions recorded** (fill at dry-run time):

```
VM IP / hostname:        ____________________
TLS branch:              [ ] A  [ ] B (url: _______________)  [ ] C
Snapshot ID:             ____________________
First-pull TORCS image:  [ ] ran   [ ] cut (cuts list item #4)
Volume-permission test:  [ ] re-verified (already green local; see §5)
loginctl linger enabled: [ ] yes
```

---

## §5 — Volume-permission re-verify on the VM

The UID-remap test (v6 plan gotcha #11) was already green locally during 3.2. Rootless Podman on a fresh VM has the same shape, but verify once because cross-machine differences happen:

```bash
podman compose --profile torcs up -d
podman exec torcs sh -c "touch /home/student/workspace/gym_torcs/telemetry/vm-check.txt"
podman exec override sh -c "cat /app/data/telemetry/vm-check.txt && echo OK"
```

If permission-denied: re-apply the `user: "0:0"` workaround on the `torcs` service in `docker-compose.yml` (it's already there from the local 3.1 smoke fix — re-verify it's in the cloned copy).

---

## §6 — Tear-down

Run on **2026-06-01** or earlier (post-judging, post-portal-confirmation).

```bash
# On the VM:
podman compose down -v        # also drops the torcs-telemetry named volume
cd ~ && rm -rf overdrive-may-2026
# In Hetzner Cloud console:
# • Delete the VM (stops further billing)
# • OPTIONAL: keep the snapshot (~$1/month) if a post-mortem replay is wanted
```

Total cost projection over the 19-day build + judging window:

| Line | Amount |
|---|---|
| Hetzner VM (~4–5 days @ ~$11.40/mo prorated) | ~$1.50–2.00 |
| Hetzner snapshot (~$1/mo for ~1 month if kept) | ~$0.50–1.00 |
| watsonx.ai burn (CA$10 budget alerts on Runtime + Studio) | ~$1–10 |
| **Total** | **~$3–13 USD** |

---

## §7 — When the dry-run produces a hosted URL

Paste it into [`docs/plans/submission-portal-copy.md`](plans/submission-portal-copy.md) §9 (the conditional row already accommodates either branch). The BeMyApp portal "How to try it" field gets `http://<vm-ip>:8000` (Branch A/C) or `https://override.duckdns.org` (Branch B), with the ephemeral-tear-down framing intact.

**If 3.7 is cut** (cuts list item #4) — the conditional row falls back to "OVERRIDE runs locally; use the YouTube link instead." No portal copy edit needed beyond that.
