# Security

> **Version:** v1.0 (submission scope). Last updated 2026-05-14.

> **Posture:** single-user, replay-first, no PII. The system is a demo/judging surface for the IBM SkillsBuild AI Builders Challenge, not a multi-tenant production service.

> **Authority:** if this doc disagrees with the code, the code wins and this doc has drifted. Open an issue and reconcile in the same commit. ADRs (`docs/adrs/`) take precedence over both this doc and the v6 plan for the decisions they record.

This document is referenced as the security baseline by `docs/07-deployment.md` §2, `docs/adrs/ADR-004` §"Security model", `docs/05-risk-register.md` (R14–R18), and the threat-model claims embedded in `docs/02-ai-and-technical-approach.md` and `docs/03-prd.md`. Anything that contradicts those references is drift and should be filed against this file.

---

## §1 - Threat model

**Operator scope.** OVERRIDE v1.0 is a single-operator system. The operator is the deployment owner - the person who set up `.env` with their `WATSONX_API_KEY`, brought up the Podman compose stack, and (for the hosted demo) provisioned the Cloudflare Tunnel. Everyone else - judges, demo viewers, anyone hitting `override.patrickndille.com` from the public internet - is a **read-mostly visitor** with no privileged operations exposed to them.

**Replay-first.** The demo path of record is fixture-driven (`?fixture=1`). Live pipeline invocations on the public endpoint are tolerated as a courtesy to curious judges but capped by Cloudflare WAF rate-limit and by the watsonx Essentials CA$10 budget alert (see R18). Nothing in v1.0 depends on a visitor's ability to invoke the live pipeline; failure to do so degrades the experience but preserves the rubric story.

**Worst-case attacker.** Anyone on the public internet who can reach `https://override.patrickndille.com` during the judging window. **What they CAN do** if mitigations work as designed:

- Hit `/api/health`, `/api/version`, `/api/sessions` (list), `/api/sessions/{id}` (read), `/api/sessions/{id}/laps|zones|zones/{id}` (read), `/api/regulation-source` (read), `/api/torcs-status` (read).
- POST `/api/sessions` (upload), `/api/sessions/{id}/what-if` (perturb), `/api/sessions/torcs-live` (ingest) - these burn watsonx credit per call but cannot bypass the WAF rate-limit (5 req/min/IP on `POST /api/sessions`) or the validator/Guardian path that gates output structure.
- Hit `/api/torcs/start-race` and `/stop-race` (the Phase 2 control plane endpoints). The frontend hides the buttons unless `window.location.hostname === "localhost"`, but the API itself is unauthenticated in v1.0 (see §5 "Known gaps").

**What they CANNOT do** if mitigations work as designed:

- Traverse the filesystem via path parameters - every user-controlled path component is regex-clamped (see §3).
- Read another user's session data - there are no other users; the single-session-per-operator model is the design, not a hole.
- Reach the TORCS desktop (noVNC at `:6080`), the Jaeger UI (`:16686`), the Ollama API (`:11434`), or the Langflow canvas (`:7860`). The first two are Cloudflare-Access-gated (one-time PIN + email allowlist); the last two have their tunnel routes deleted entirely (see 07-deployment.md §2).
- Reach the TORCS container's internal control daemon at `torcs:7000`. That port is never mapped to the host in `docker-compose.yml`; it is only reachable from the `override` service over the `override-net` Docker bridge, and every endpoint except `/health` requires the `TORCS_CONTROL_SECRET` bearer (constant-time-compared via `secrets.compare_digest`).
- Exfiltrate FIA regulation PDFs. PDFs are not committed (R14); only the derivative `data/regs/extracted_chunks.sample.json` is in the repo. The `/api/regulation-source` endpoint returns chunks, not full text.

**Out-of-scope adversaries.** Insiders with shell access to the deployment laptop, supply-chain attackers compromising IBM watsonx itself, network attackers between the laptop and Cloudflare with active MITM capability against TLS. Defense against these is documented as v1.1+ work in §6.

---

## §2 - Surface inventory

Public-facing HTTP surface (`https://override.patrickndille.com`, Cloudflare-Tunnel-fronted):

| Method | Path | Authn | Rate limit | Notes |
|---|---|---|---|---|
| GET | `/api/health` | None | none | Returns 200 + version metadata. Cheap. |
| GET | `/api/version` | None | none | Git SHA + build timestamp. |
| GET | `/api/sessions` | None | none | Paginated session summary list (limit ≤ 200). |
| POST | `/api/sessions` | None | **5 req/min/IP** at Cloudflare WAF | Multipart upload → full pipeline. The watsonx-burn surface. |
| GET | `/api/sessions/{id}` | None | none | `id` regex `^s_[A-Za-z0-9_]+$` - no traversal possible. |
| GET | `/api/sessions/{id}/laps\|zones\|zones/{zone_id}` | None | none | Same regex clamp on `zone_id`. |
| POST | `/api/sessions/{id}/what-if` | None | inherits POST /api/sessions WAF | Cache key short-circuits re-runs; `WhatIfRequest` validated by Pydantic. |
| POST | `/api/sessions/torcs-live` | None | inherits POST /api/sessions WAF | Reads from shared `torcs-telemetry` volume only; `run_id` regex `^[A-Za-z0-9_-]+$`. |
| GET | `/api/torcs-status` | None | none | Lists JSONL files in the shared volume. Returns `available: false` for empty volumes (never 404). |
| GET | `/api/regulation-source` | None | none | Returns extracted chunks; no PDF content. |
| POST | `/api/torcs/start-race`, `/stop-race` | **None (v1.0 gap - see §5)** | none | UI hides the buttons on non-localhost; backend proxies to internal daemon. |
| DELETE | `/api/sessions/{id}` | None | none | Single-user model - anyone can delete; documented as v1.0 limitation. |

Gated subdomains (Cloudflare Access - one-time PIN + email allowlist; see 07-deployment.md §2):

- `torcs.patrickndille.com` → `localhost:6080` (TORCS desktop via noVNC).
- `jaeger.patrickndille.com` → `localhost:16686` (trace UI).

Deleted subdomains (no tunnel route; only reachable from the operator's own loopback):

- `ollama` → `localhost:11434` - free LLM inference would be abused, no legitimate external consumer.
- `langflow` → `localhost:7860` - design canvas with arbitrary-tool execution, out of demo scope.

Internal-only surface (`override-net` Docker bridge - no host port mapping):

- `torcs:7000` - control daemon. **Bearer-token authenticated** (`TORCS_CONTROL_SECRET`, `secrets.compare_digest`). See ADR-004 §"Security model" for the full shape.
- `torcs:11434` - Ollama API. Reachable from `override` only; used by `OVERRIDE_LLM_RUNTIME=ollama` mode and by the lab's `Continue.dev` extension. No bearer; same-host trust boundary.

---

## §3 - Shipped mitigations (verified in code, 2026-05-14)

**Input validation - no filesystem traversal possible from user input:**

- `session_id`: Pydantic field `pattern=r"^s_[A-Za-z0-9_]+$"`. Used by every per-session endpoint and as a directory name under `data/sessions/`.
- `zone_id`: Pydantic field `pattern=r"^z_[A-Za-z0-9_]+$"`. Used by what-if endpoint and per-zone endpoints.
- `run_id` (torcs-live): Pydantic `pattern=r"^[A-Za-z0-9_-]+$"`, length 1–64. Resolves to `/app/data/telemetry/{run_id}.jsonl` only; the directory is the shared `torcs-telemetry` volume, no escape paths.
- `track` (control daemon): Pydantic `pattern=r"^[a-z0-9_-]+$"`. Filtered through a daemon-side allowlist of TORCS-known tracks before being written into `quickrace.xml`.
- WhatIf perturbation parameters: bounded integers (`n ∈ [1,10]`, `extra_laps ∈ [1,5]`).
- Lap counts (control daemon): bounded `[1, 200]`.

**Concurrency safety:**

- `_fan_locks: dict[str, asyncio.Lock]` with `setdefault`-based TOCTOU-safe creation in `api/main.py`. Prevents the lazy fan-mode read-modify-write race that two parallel zone-fan requests would otherwise hit.
- Atomic write via `tempfile + os.replace` in `api/storage.save_recommendations_only` and elsewhere. No partial-state writes on crash.
- Control daemon wraps the entire start-race TOCTOU window (state check + Popen) in a single `asyncio.Lock` - two concurrent `/control/start` calls cannot both spawn gym_torcs.

**Robustness against partial input:**

- JSONL safe-read in `ingest/torcs_parser.py` skips incomplete tail lines (no trailing `\n`) and swallows `json.JSONDecodeError` silently - the live-ingest endpoint reads while `torcs_jm_par.py` may still be appending.
- Validator (Pass 1) and Guardian (Pass 2) both run on every reasoning output; failures are returned to the UI, not hidden. Two-pass safety is unconditional.

**Subprocess hygiene:**

- Control daemon uses two-stage termination: `SIGTERM` with 5s grace, then `SIGKILL` with 2s reap. Daemon-level `SIGTERM/SIGINT` handler reaps gym_torcs on container shutdown so the SCR UDP port doesn't leak across restarts.
- Six-state race lifecycle (Phase 2.5) prevents illegal transitions; `_ALLOWED_TRANSITIONS` enforces the state machine and force-cleans up on violation.
- Verified-kill: after `pkill -9 -f torcs-bin`, `pgrep` confirms the reap or raises with the live PIDs.

**Fail-loud configuration:**

- Empty `TORCS_CONTROL_SECRET` raises `RuntimeError` at daemon import - uvicorn refuses to start a misconfigured stack.
- `OVERRIDE_LLM_RUNTIME=ollama` probes `GET {OVERRIDE_OLLAMA_BASE_URL}/api/tags` at first `get_chat_client()` invocation with a 2-second timeout; refuses to boot if Ollama is unreachable.
- watsonx connectivity is gated by `scripts/test_watsonx.py` (gate G-1) before any reasoning call ships; failures surface as 500s, not silent hangs.

**Secrets handling:**

- `.env` is gitignored; `.env.example` documents the required keys without values.
- No `WATSONX_API_KEY`, `TORCS_CONTROL_SECRET`, or other secrets are logged at any level - verified by grep across `api/`, `core/`, `ingest/`, `analysis/`.
- Cloudflare API tokens used by `cloudflared` live in the operator's account, not the repo.

**Edge protections (Cloudflare):**

- One-time PIN + email allowlist on `torcs` and `jaeger` subdomains. Session duration 24h; allowlist managed in the Cloudflare dashboard per 07-deployment.md §2.
- WAF zone rule: rate-limit `POST /api/sessions` at 5 req/min/IP. Covers `/api/sessions/{id}/what-if` and `/api/sessions/torcs-live` by URL-prefix match.
- TLS termination at the Cloudflare edge; cloudflared maintains an outbound WSS tunnel to the local WSL2 host. No inbound ports opened on the operator's network.

**Asset / content discipline (rubric):**

- All visuals original (TORCS, UI, generated charts, Langflow canvas). No F1 broadcast footage, paddock photography, or team livery (per R15).
- FIA PDFs not committed (R14). `scripts/download_regulations.py` fetches them at build time; `scripts/build_chunks.py` runs Docling locally; only the derivative `extracted_chunks.sample.json` ships in the repo.
- gym_torcs MIT LICENSE preserved at `RaceYourCode/gym_torcs/LICENSE` per upstream redistribution requirement.

---

## §4 - Operational hardening for the judging window

Listed concretely so the T-72h walk-through has something to check:

- `podman update --restart=always override torcs jaeger` - survives container crashes.
- Windows host: Settings → System → Power → Screen and sleep → Never (plugged in), for May 24–31.
- `systemctl enable --now cloudflared` - survives WSL reboots.
- `loginctl enable-linger $USER` - containers survive SSH disconnect on a fresh login session.
- `TORCS_CONTROL_SECRET` rotated before the judging window - invalidates any value committed to a dev `.env` or leaked in chat logs (per ADR-004 §"Consequences").
- Pre-flight: external-network smoke from a cellular device against all three subdomains. `override` → 200; `torcs` and `jaeger` → 302 redirect to Cloudflare Access (NOT 200 directly).

---

## §5 - Known gaps (v1.0 → v1.1)

**The `/api/torcs/start-race` and `/api/torcs/stop-race` endpoints are unauthenticated in v1.0.** The frontend localhost-hostname guard hides the buttons when accessed via `override.patrickndille.com`, but a curl request still reaches the daemon-proxy code path. The TORCS control daemon itself is bearer-authenticated, and the daemon is only reachable from the override service over `override-net` - so even an unauthenticated proxy call has to traverse the bearer check before it can start a race. **The risk surface is therefore "anyone can trigger a watsonx call by hitting the override endpoint, which then attempts a daemon call that fails with 401 if `TORCS_CONTROL_SECRET` is set."** Acceptable for v1.0; closed in v1.1 by gating the proxy endpoint behind a Cloudflare Access policy or by adding a server-side hostname check in the FastAPI handler.

**`DELETE /api/sessions/{id}` has no authz.** Single-user model; the public visitor can delete sessions. Acceptable because (a) the public visitor doesn't know which session IDs to target, (b) replay is fixture-driven, and (c) the operator can re-upload the canonical sample to reconstruct the dashboard. v1.1 candidate: per-IP delete rate-limit or full session-list authentication.

**No application-layer rate limit.** Only the Cloudflare WAF rule covers `POST /api/sessions`. A FastAPI-level per-IP limiter is documented as v1.1 work in `docs/05-risk-register.md` R18.

**No audit log.** What-if invocations and session deletions don't write a tamper-evident trail. Adequate for v1.0 (no compliance requirement); v1.1 candidate: append-only journal under `data/sessions/_audit.jsonl`.

**No mTLS inside the compose network.** Override → torcs control daemon traffic is plaintext HTTP over `override-net`. Process-local on a single host (single-operator model), so the threat is contained. ADR-004 §"What this is not" documents this as v1.2 work pending a multi-host deployment.

**No supply-chain attestation.** `requirements.txt` is pinned, `models.json` records watsonx model IDs, but there's no SBOM, no signed image, no SLSA attestation. v1.1+ - out of scope for the May 2026 submission window.

---

## §6 - Cross-references

- **ADR-001** (`docs/adrs/ADR-001-watsonx-runtime.md`) - auth surface introduced by the watsonx migration; `WATSONX_API_KEY` handling.
- **ADR-004** (`docs/adrs/ADR-004-torcs-control-plane.md`) §"Security model" - full control daemon security shape (bearer auth, single-writer lock, subprocess hygiene, hosted-demo button suppression).
- **07-deployment.md** §2 - per-subdomain risk table, Cloudflare Access policy setup, WAF rule.
- **05-risk-register.md** - R14 (FIA PDF licensing), R15 (broadcast footage), R17 (Guardian deprecation), R18 (watsonx outage / rate-limit).
- **AGENTS.md** (repo root) - operator behaviors that affect security posture (branch discipline, `.env` handling, secret-rotation expectation).
