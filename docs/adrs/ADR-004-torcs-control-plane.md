# ADR-004 — TORCS control plane: HTTP daemon inside the container

- **Status**: Accepted
- **Date**: 2026-05-13

## Context

Phase 2 of `docs/roadmap-v1.1/interactive-torcs-integration.md` removes the
noVNC-terminal step from the demo flow — judges click a "Start Race" button
on `/upload` instead of opening a terminal inside noVNC and running
`python3 torcs_jm_par.py`. The OVERRIDE API needs to start, stop, and
introspect a gym_torcs subprocess that lives inside the **separate** torcs
compose container.

Three approaches were considered.

### Option A — Mount the Podman socket into the override container

The override service mounts `/run/podman/podman.sock` and calls
`podman exec torcs python3 ...` via the Podman REST API or shell out to the
`podman` CLI.

- **Pros**: No new auth surface; uses Podman's own ACLs; standard k8s-shape
  control-plane pattern when adapted.
- **Cons** (the disqualifier): exposing the Podman socket to a container
  gives that container effective root on the host. Any RCE in the override
  service (e.g. through a fixture-upload parsing flaw, a Pydantic
  deserialization bug, a transitive dep CVE) becomes container-escape and
  full host compromise. v6 plan §5 cuts this category of risk
  ("single-user replay-first per 05-security.md") — adding a Podman socket
  would silently widen the threat model far beyond what the rest of the
  architecture assumes.
- **Verdict**: Rejected. The convenience isn't worth re-opening
  container-escape paths.

### Option B — A separate sidecar control service in compose

A new third service (call it `torcs-control`) running alongside torcs,
with the Podman socket mounted, exposing a narrow HTTP API to override.
torcs itself stays socket-less; override sees only the sidecar.

- **Pros**: Quarantines the socket-mount blast radius to one service.
- **Cons**: Still has the socket-mount risk on a service that's part
  of the demo. Two new compose services to coordinate. The sidecar
  has to run `podman exec` against the torcs container — adds a
  failure mode (sidecar up, torcs down) that doesn't simplify the
  user experience over Option C.
- **Verdict**: Rejected. The architectural improvement over A is
  meaningful, but C is simpler with the same security properties.

### Option C — HTTP daemon **inside** the torcs container (selected)

The torcs container itself runs a tiny FastAPI app
(`RaceYourCode/gym_torcs/control_daemon.py`) on an internal port
(`localhost:7000` inside the container, `http://torcs:7000` over
override-net). The daemon owns the gym_torcs subprocess via
`subprocess.Popen` — no Podman socket anywhere. OVERRIDE proxies
operator clicks (Start Race / Stop Race) to the daemon's
`/control/start` and `/control/stop` endpoints.

- **Pros**: No socket mount anywhere. The daemon's blast radius is the
  TORCS lab container itself, which is already the operator's untrusted
  driving environment. Subprocess lifecycle stays where the subprocess
  actually lives. No new compose services.
- **Cons**: The torcs container's Python environment grows by
  `fastapi + uvicorn` (~50 MB installed). Tolerable — the image is
  already 10 GB. Install happens at compose-startup time via the init
  script's pip step, so the host repo doesn't carry a permanent
  dependency.
- **Verdict**: **Accepted.**

## Decision

We ship a FastAPI control daemon as part of the TORCS container's boot
sequence, behind a shared-secret bearer token, only reachable over the
internal compose network.

## Security model

| Property | Implementation |
|---|---|
| Where it lives | Inside the torcs container at `0.0.0.0:7000`. Same image, same network namespace as the lab itself. |
| External reachability | **None.** `docker-compose.yml` does **NOT** map port 7000 to the host. The daemon is only reachable from the override service via `http://torcs:7000` over the `override-net` Docker bridge. A `curl localhost:7000/health` from the host operator's shell returns connection-refused. |
| Authentication | Shared-secret bearer token (`TORCS_CONTROL_SECRET` in `.env`). Required on every endpoint except `/health`. Compared with `secrets.compare_digest()` — constant-time, timing-attack-resistant. |
| Failure-loud posture | Empty `TORCS_CONTROL_SECRET` at daemon import time raises `RuntimeError` and prevents uvicorn from starting. A misconfigured compose stack fails fast instead of silently running with auth effectively disabled. |
| Single-writer invariant | `asyncio.Lock` wraps the **entire** TOCTOU window in `/control/start` (both the "is a race already running?" check and the `Popen` call). Two concurrent start requests cannot both spawn gym_torcs. |
| Subprocess hygiene | Termination is two-stage: SIGTERM with 5 s grace, then SIGKILL with 2 s reap. Daemon-level SIGTERM/SIGINT handler also reaps gym_torcs on container shutdown so the SCR UDP port doesn't leak across restarts. |
| Input validation | Pydantic field patterns reject path-traversal in `session_id` (`^s_[A-Za-z0-9_]+$`) and `track` (`^[a-z0-9_-]+$`). Lap counts bounded `[1, 200]`. |
| Hosted demo | The Phase 2 UI buttons only render under a `window.location.hostname === "localhost"` guard. On the Cloudflare-Tunnel-fronted hosted demo (`override.patrickndille.com`), the buttons are hidden — judges who want to drive TORCS still use the local-clone path. |

## What this is not

- It is **not** a production multi-tenant control plane. There's exactly one
  TORCS container per compose stack and at most one race active at a time.
- It is **not** transport-encrypted. The shared-secret bearer travels in
  plaintext over `override-net`, which is fine because that network is
  process-local on a single host. Any move to multi-host (Kubernetes,
  remote TORCS instances) would require mTLS, which is documented as v1.2
  work, not v1.1.
- It is **not** a substitute for proper auth. v1 is single-operator;
  Phase 2 doesn't introduce user accounts, RBAC, or audit logging. The
  shared secret is operator-scoped; if it leaks, an attacker on the host's
  compose network could start/stop races. That's an acceptable risk for
  a single-user judging-window demo.

## Consequences

- Operators must set `TORCS_CONTROL_SECRET` in `.env` to enable the
  daemon. Setting it empty disables the daemon (backward-compat path —
  the init script falls back to plain `start.sh`).
- The torcs container's first boot is ~30 s slower (pip install of
  fastapi + uvicorn). Subsequent restarts re-install but Python's
  cached wheels make it fast.
- `podman compose ps` will show a `health: unhealthy` for the torcs
  service for ~90 s after startup while noVNC is still coming up.
  Expected — `start_period: 90s` in the compose healthcheck.
- Phase 5 final-lock walks include a step to rotate `TORCS_CONTROL_SECRET`
  before the judging window so any value committed to a dev `.env` or
  leaked in chat logs is invalidated.

## Cross-references

- Plan: `docs/roadmap-v1.1/interactive-torcs-integration.md` §2
- Code: `RaceYourCode/gym_torcs/control_daemon.py`,
  `scripts/torcs_container_init.sh` (boot chain),
  `api/main.py` (`/api/torcs/start-race`, `/api/torcs/stop-race` proxy
  endpoints — landing in Phase 2 implementation commits)
- Security baseline: `docs/05-security.md` (single-user replay-first),
  `docs/07-deployment.md` §2 (per-subdomain risk table — torcs subdomain
  is intentionally **not** publicly mapped through the Cloudflare Tunnel)
- Adjacent ADRs:
  - ADR-001 (watsonx runtime — the bulk of compute lives off-host)
  - ADR-002 (TORCS as primary sandbox)
  - ADR-003 (LLM runtime abstraction — the only other internal-network
    HTTP boundary in the stack)
