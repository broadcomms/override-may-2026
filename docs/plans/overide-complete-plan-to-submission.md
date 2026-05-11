# OVERRIDE — Completion Plan to Submission

**Submission target:** May 27–28, 2026 (T-16/17 days from May 11). Final deadline May 31 11:59 PM ET. Phase 5 final-lock runs May 29–31. First-10-teams bonus (May 23) abandoned in favor of clean ship.

**Total estimate (v6 — CX32 confirmed + ten review amendments):** ~85h baseline / ~106h with 25% slack. **Two denominators:** ~15 working days through the May 27–28 target = **~5.6h/day**; or 17 elapsed days through the same target = **~5.0h/day average** (some days off, some heavy). Submission week (May 29–31) adds Phase 5's 6h on top. Honest math: this is a real ~5–6h/day commitment for two-plus weeks; the 25% slack is for unknown surprises (Podman networking edge cases, UID-remap surprises, container init bugs, VM dry-run friction), not for taking weekends off. If a personal/work conflict eats two days inside the window, the cuts list fires mechanically — most likely cut #4 (hosted demo URL) pre-emptively.

Weekly totals: Week 1 ~17h + Week 2 ~33h (25h sub-tasks + 8h FR-8 integration contingency) + Week 3 ~29h + Phase 5 ~6h = 85h baseline × 1.25 = 106h with slack.

## Context

OVERRIDE is feature-complete for Tier-1: the pipeline (ingest → zones → reasoning → validator → Guardian → fan-mode) runs end-to-end, 231 tests pass, the UI Engineer+Fan modes work, the Docling regulation grounding (G-4) is closed against Issue 18. What's still missing from the **original vision** are four specific items, plus several smaller gaps the audit surfaced:

**Major gaps vs vision** (per `docs/03-prd.md`, `docs/06-roadmap.md`, `.bob/AGENTS.md`):
- `ingest/torcs_parser.py` is 0 bytes — TORCS data path never closed (P1.4 incomplete). The lab now runs (`hands-on-labs/01_torcs_lab/`), so the data-source story can finally be honored.
- FR-8 what-if simulation (delay_first_deploy / skip_harvest_zone / extend_override) — required by the PRD, never implemented.
- `Dockerfile`, `docker-compose.yml` empty — `docs/07-deployment.md` treats Docker as the shipping shape.
- `.github/workflows/ci.yml` empty — never spec'd; will be deleted, not implemented.

**Smaller gaps** (from the code-completeness audit):
- Concurrency hazard in the lazy fan-mode `save_session` (`api/main.py:351-372`) — parallel zone-fan fetches race and the last writer wins.
- Five stale plan files violate the project's "delete plan in same PR that ships the feature" rule (`.bob/rules.md`).
- `SessionsPage.tsx` is an empty-state stub citing "Tier 2"; list endpoint helper exists in storage but isn't wired.
- TTM-R2 forecasting (`core/forecasting.py` empty) — **deferred per graceful-degradation guardrail**, just needs a stub docstring + UI badge update.
- P3.6 Jaeger trace screenshot still pending.

**Locked scope decisions** (this session):
| Track | Choice | Rationale |
|---|---|---|
| TORCS | Parser + 2 pre-captured fixtures + telemetry logger + **TORCS as a profile-gated service in compose** with shared-volume live-ingest endpoint | Fixture path stays canonical for demo determinism; live TORCS adds realtime explorability for judges who want to drive |
| FR-8 | Full ship — all 3 perturbations, end-to-end | PRD requirement, not optional |
| Container runtime | **Podman** (not Docker) — multi-stage build, single OVERRIDE image, TORCS lab image profile-gated alongside | User's chosen runtime; lab already runs on it; Podman is Compose V2 compatible |
| **LLM runtime (NEW)** | **Hybrid switchable: watsonx primary for OVERRIDE; ollama+granite4:350m kept inside TORCS container for the driver. `OVERRIDE_LLM_RUNTIME=watsonx\|ollama` env var routes the OVERRIDE chat path.** Reasoning + Fan Mode work via either runtime; Guardian + Embedding stay watsonx-only (no equivalent in the shipped ollama model). | User wants the original lab-shipped ollama path preserved + clean v1.1 migration path to all-ollama. The `WatsonxChatClient` Protocol in `core/reasoning.py` already allows this — adding `OllamaChatClient` is structural, not architectural. |
| Repo layout | **`RaceYourCode/` lives in repo root.** gym_torcs unzipped here once, committed. Compose mounts `./RaceYourCode:/home/student/workspace:Z`. Single repo, no external scratch dir. | User explicit; matches "everything in one repo" principle; avoids the v4 footgun of mounting a path that didn't exist (the zip was in `04_files/gym_torcs.zip`, never extracted on the host). |
| Deployment target | **Ephemeral Ubuntu Linux VM** (cloud) for judging window; matches WSL Ubuntu architecture for parity. Tear-down post-May-31. | User-stated; ephemeral keeps security posture (single-user, replay-first per `05-security.md`) consistent with the v1 non-goals; ~30 min added to Week 3. |
| First-time TORCS image pull | **Accept the 10–15 min pull on first `--profile torcs up`.** Document loudly in README. After first pull, the image is cached locally and re-uses fast. | User explicit. Trade-off: judges with slow connections see a one-time delay; subsequent runs are fast. |
| CI | Defer to v1.1 | Never spec'd; delete empty placeholder |
| TTM-R2 | Defer to v1.1 — stub file + UI badge + doc updates | Graceful-degradation guardrail makes it explicitly optional |

## Architectural decision — Podman compose with TORCS in the stack

This is a v4 amendment to v3's compose design. v3 said "don't bundle TORCS in OVERRIDE's compose." That decision is reversed: TORCS *is* in the compose stack, profile-gated, so the realtime explorability story works while the default `podman compose up` stays lean.

```yaml
# docker-compose.yml (NO top-level `version:` — Compose V2; works with `podman compose` and `docker compose`)
services:
  override:                                  # API + built UI bundle (multi-stage image)
    build: .
    ports: ["8000:8000"]
    env_file: .env
    environment:
      # When OVERRIDE_LLM_RUNTIME=ollama, route chat to the TORCS container's ollama
      OVERRIDE_OLLAMA_BASE_URL: http://torcs:11434
    volumes:
      - ./data/sessions:/app/data/sessions   # session persistence
      - torcs-telemetry:/app/data/telemetry  # shared with TORCS service
    networks: [override-net]

  torcs:                                     # IBM lab container, profile-gated
    image: docker.io/johnsloe/torcs-competition:amd64
    ports:
      - "5900:5900"                          # VNC (drive via desktop)
      - "6080:6080"                          # noVNC web at /vnc.html
      - "3001:3001/udp"                      # SCR (AI driver protocol)
      - "11434:11434"                        # Ollama HTTP API (granite4:350m)
    volumes:
      - ./RaceYourCode:/home/student/workspace:Z          # gym_torcs source, host-edited; one repo
      - torcs-telemetry:/home/student/workspace/telemetry:Z
      - ./scripts/torcs_container_init.sh:/usr/local/bin/torcs_init.sh:Z,ro
    # Override the lab container's default entrypoint to (1) fix the Ollama
    # permission bug from RESULTS.md, (2) suppress the VS Code extension
    # install hang, then (3) chain into the original entrypoint.
    # Script content lives in scripts/torcs_container_init.sh (see Week 3 3.1).
    entrypoint: ["/usr/local/bin/torcs_init.sh"]
    networks: [override-net]
    profiles: [torcs]                        # default `up` does NOT pull this 10 GB image

  jaeger:
    image: docker.io/jaegertracing/all-in-one
    ports: ["16686:16686", "4317:4317"]
    profiles: [observability]

volumes:
  torcs-telemetry:                           # shared bus for live-ingest path

networks:
  override-net:
```

**Three commands, three modes:**
- `podman compose up` — OVERRIDE alone (UI + API at :8000). Fast, lean, no 10 GB pull. Fixture-driven demo path. Watsonx-backed reasoning.
- `podman compose --profile torcs up` — OVERRIDE + TORCS. Drive in noVNC at `:6080`. `torcs_jm_par.py` writes JSONL to `/home/student/workspace/telemetry/`; OVERRIDE reads from `/app/data/telemetry/`. Ollama-granite4:350m on `:11434` reachable from inside the OVERRIDE container at `http://torcs:11434` (used by the lab's AI driver and optionally by OVERRIDE when `OVERRIDE_LLM_RUNTIME=ollama`).
- `podman compose --profile observability up` — OVERRIDE + Jaeger at `:16686`.

**Realtime ingest path** (new endpoint, Week 3 sub-step 3.6):
- `POST /api/sessions/torcs-live` with `{ "run_id": "<run>" }` body — reads `/app/data/telemetry/<run_id>.jsonl`, calls `ingest.torcs_parser.parse_torcs_session`, pipes through `run_pipeline()`, returns Session.
- UI gets a "Ingest live TORCS run" button on `/upload` page that's only enabled when `GET /api/torcs-status` reports the shared volume non-empty.
- **NOT a streaming endpoint.** Lap-paced ingestion on demand, not tick-by-tick. True streaming (SSE pushing zone detections as laps complete) is documented as v1.1.

**Demo invariant:** the YouTube video uses fixtures (`s_torcs_engineer_demo?fixture=1` per 2.8), not live TORCS. The realtime path is for judges exploring the cloned repo, not for the recording. This preserves the v3 demo-determinism decision.

## Pre-flight gotchas (resolve before coding)

These are the booby-traps the agent doing the work shouldn't have to re-derive. ~30–60 min total to absorb up front; several hours if hit mid-implementation.

1. **TORCS energy-model calibration.** The fastf1 constants (`HARVEST_KJ_PER_BRAKE_SECOND`, `DEPLOY_KJ_PER_FULL_THROTTLE_SECOND`) were tuned for FastF1 timescales and vehicle dynamics. TORCS sensor sample rates, lap durations, and brake/throttle profiles differ. **Copy verbatim and the first capture will likely produce 2 MJ/lap or 24 MJ/lap — either breaks zone detector and the harvest_cap rule.** Calibration step is non-optional: run captured baseline through the parser, scale constants until per-lap harvest/deploy lands in the 4–7 MJ/lap range (under the 8.5 MJ cap parsed from regs). Then lock with a regression test (see 1.6).
2. **gym_torcs `fuel` sensor IS exposed.** Standard gym_torcs observations include `fuel` (plus `distFromStart`, `distRaced`, `curLapTime`). Fuel-burn rate is a better proxy for engine work than a throttle integral — it captures load, gear, and RPM implicitly. Check what the captures emit and prefer `fuel` where available. Still derived (not measured 2026 hybrid state), but stronger signal.
3. **`asyncio.Lock` dict has a TOCTOU race.** Naïve `if session_id not in locks: locks[session_id] = Lock()` is racy under parallel requests. Use `setdefault`:
   ```python
   _session_locks: dict[str, asyncio.Lock] = {}
   lock = _session_locks.setdefault(session_id, asyncio.Lock())
   async with lock:
       ...
   ```
4. **WhatIf cache key — be explicit.** Pydantic frozen models with list fields aren't natively hashable. Spec:
   ```python
   cache_key = hashlib.sha256(request.model_dump_json().encode()).hexdigest()[:16]
   ```
   Stable across runs, deterministic, filename-safe.
5. **`python:3.12-slim` lacks build tools.** pyarrow / docling / some scientific deps need `gcc`/`g++`. Add `RUN apt-get update && apt-get install -y --no-install-recommends build-essential` before the pip install, OR fall back to `python:3.12` base if wheel resolution still fails.
6. **No `version:` in docker-compose.yml.** Deprecated in Compose V2; modern schema is just `services: ...` at the top level. (Same for both Podman and Docker.)
7. **Podman ≠ Docker — five concrete differences:**
   - **Compose command:** `podman compose ...` (built into Podman 4.x) or `podman-compose` (separate Python package). Most v3 syntax works; profile flag is `--profile`, same as Docker.
   - **Image refs need full path:** Podman does not default to Docker Hub. Use `docker.io/johnsloe/torcs-competition:amd64`, `docker.io/jaegertracing/all-in-one`, etc. Verbatim image names without the registry will fail.
   - **Volume SELinux relabel:** Append `:Z` to volume mounts (`./RaceYourCode:/home/student/workspace:Z`). **No-op (with harmless warning) on Ubuntu/WSL/Debian**; **mandatory on Fedora/RHEL/Rocky/CentOS**. Don't drop the flag — safe everywhere it's not needed; required everywhere it is.
   - **Rootless networking:** Podman is rootless by default. Service-to-service DNS (`http://override:8000` from inside `torcs`) works fine within a compose network. **UDP forwarding is occasionally flaky** — verify port 3001/udp before assuming it's open.
   - **Healthchecks identical syntax;** `HEALTHCHECK CMD curl -f http://localhost:8000/api/health || exit 1` works the same.
8. **The TORCS image is ~10 GB.** Profile-gate it strictly (`profiles: [torcs]`) so default `podman compose up` doesn't pull it. Image pull on first `--profile torcs up` takes 10–15 min on typical home connections. Document this in the README so judges aren't surprised.
9. **WSL needs TORCS install too.** Migrating to WSL doesn't carry TORCS over. Budget the lab's `02.2_torcs_container_setup_guide.pdf` Podman path (`sudo apt-get -y install podman` + `podman run -it --rm -p 5900:5900 -p 6080:6080 -p 3001:3001/udp -v ~/RaceYourCode:/home/student/workspace:Z --name torcs docker.io/johnsloe/torcs-competition:amd64`). WSLg forwards the noVNC desktop; X server isn't needed. **Fallback:** if Podman+WSLg friction blocks Week 1 progress past 5h, fall back to running TORCS captures on the existing macOS machine and transferring JSONL files to WSL — the parser is platform-agnostic.
10. **TORCS container init quirks (from `hands-on-labs/01_torcs_lab/RESULTS.md`).** The IBM lab image ships with two known bugs that bite on fresh start. **The compose entrypoint override (`scripts/torcs_container_init.sh`) absorbs both automatically — no manual intervention needed for the typical case.** The two bugs and their automated fixes:
    - **Ollama directory ownership:** `/opt/ollama` is owned by root in the image; Ollama needs it writable by `student`. The init script runs `chown -R student:student /opt/ollama`. **For `/tmp`**, narrow scope to only Ollama's own paths (`chown student:student /tmp/ollama.log /tmp/ollama-* 2>/dev/null || true`) — a recursive chown on the entire `/tmp` tree is too aggressive and can break unrelated container state.
    - **VS Code extension install hang:** the image's bootstrap blocks at `[1/6] Checking VS Code extensions`. We don't edit code inside the container, so kill that bootstrap before it stalls compose: `pkill -f "code.*install-extension"` (silent if not running). Also write `DONT_PROMPT_WSL_INSTALL=1` to `/etc/environment` to suppress the prompt loop entirely.
    - **Manual fallback (rare):** if `podman logs -f torcs` stalls at the `[1/6] Checking VS Code extensions` line, the init script either didn't run or didn't exec successfully. Recovery: `podman exec torcs pkill -f "code.*install-extension"`. Document in README under "Troubleshooting." Should not be needed in normal operation.
11. **Volume-permission UID remap test (rootless Podman).** TORCS writes JSONL inside its container as `student` (UID 1000 or similar). OVERRIDE reads as a different UID. Rootless Podman remaps via `/etc/subuid` / `/etc/subgid`, so the file `student` wrote may not be readable to the OVERRIDE app user. **Test at the end of 3.1 fail-fast**: with `--profile torcs up`, exec into `torcs` and `touch /home/student/workspace/telemetry/test.txt`; then exec into `override` and `cat /app/data/telemetry/test.txt`. If permission-denied, fix by either (a) running `override` as the same UID as `torcs` (`user: "1000:1000"` in compose) or (b) `chmod 0644` from the writer side. Discovery of this at T-24h is bad; discovery at end-of-Week-3 is fine. May also need `loginctl enable-linger $USER` on the deployment VM so containers survive SSH disconnect.
12. **JSONL safe-read in `ingest/torcs_parser.py`.** The live-ingest endpoint reads the JSONL file while `torcs_jm_par.py` may still be appending. The last line is occasionally a partial write (no trailing `\n`). Bake into the parser day-one:
    ```python
    with open(path) as f:
        for line in f:
            if not line.endswith("\n"):
                continue            # skip incomplete tail; gym_torcs is still writing
            try:
                obs = json.loads(line)
            except json.JSONDecodeError:
                continue            # skip malformed; happens during shutdown races
            yield obs
    ```
    Don't add this *later* — the demo will trip it within 5 minutes of judges actually driving.
13. **UDP port 3001 forwarding test (5 min, in 1.1).** Verify the gym_torcs SCR port forwards correctly before committing parser work. **`nc -u` is fire-and-forget and returns useless exit codes** — a naïve `nc -u -l & echo ping | nc -u && echo OK` will pass even when forwarding is broken. Use a tee-to-file pattern that actually reads the payload back:
    ```bash
    podman run -d --name udptest -p 13001:3001/udp docker.io/library/alpine \
      sh -c "nc -u -l -p 3001 | tee /tmp/got"
    sleep 1
    echo "ping" | nc -u -w1 localhost 13001
    sleep 1
    podman logs udptest | grep -q ping && echo "UDP OK" || echo "UDP FAIL"
    podman stop udptest && podman rm udptest
    ```
    **If the test fails:** rootless Podman's default `slirp4netns` networking driver has known UDP forwarding flakiness on certain kernels. Check `podman info | grep -i networkbackend`; if `slirp4netns`, switch to `pasta` (Podman 4.4+, much better UDP semantics) by setting `network_backend = "pasta"` in `~/.config/containers/containers.conf`. If pasta isn't available, fall back to rootful Podman (`sudo podman ...`) for the TORCS service only. Catching this in Week 1 = 30-min config tweak. Catching at T-24h = panic.
14. **Process discipline + branching:**
   - **Feature work lands on `dev` (or feature branches off `dev`).** `main` only updates at the `v1.0.0-submission` tag per `final-lock-checklist.md` T-72h. Avoids force-reset under deadline pressure.
   - **Weekly gate rule:** at the end of each week classify status as **green** (all sub-items shipped → proceed, no cuts), **yellow** (one sub-item slipped to next week → trigger first cut from the list), or **red** (more than one slipped → trigger first two cuts). Mechanical, not aspirational. The 106h slack budget is for *unknown* surprises, not knowable scope creep.

## Execution sequence

### Week 1 (May 11–17) — TORCS + cleanup (~17h)

#### 1.1 — WSL migration + Podman + TORCS install (~3–5h, blocker)
Project is moving to WSL Linux. TORCS does NOT auto-carry over.
- Re-clone repo on WSL side; `python3.12 -m venv .venv`; `pip install -r requirements.txt` (pyarrow/docling may need build tools).
- `.venv/bin/pytest -q -m "not network"` — expect 231 green.
- `scripts/test_watsonx.py` — re-confirm G-1.
- `cd ui && npm install && npm run typecheck && npm run build`.
- `grep -rn "/Users/patrick" docs/ scripts/ ui/` — patch any macOS-hardcoded paths.
- **Podman version + Ubuntu version check FIRST (~2 min).** Gotcha #13's pasta networking fallback requires Podman 4.4+. Ubuntu 22.04 LTS ships Podman 3.x by default; Ubuntu 24.04 LTS ships Podman 4.x. The deploy VM (3.7) is Ubuntu 24.04 — **match it in WSL** so dev = deploy:
  ```bash
  podman --version           # need 4.4+ for pasta backend
  lsb_release -a             # Ubuntu version
  ```
  If Podman is 3.x: cleanest fix is `wsl --install -d Ubuntu-24.04` and re-run 1.1 from the start. Alternatives: install Podman 4.x from the Kubic OBS repo onto 22.04, OR accept rootful Podman (`sudo podman ...`) for the `torcs` service only — note rootful Podman changes the UID-remap test (gotcha #11) shape.
- **Install Podman + TORCS** per `hands-on-labs/01_torcs_lab/02_setup_guides/02.2_torcs_container_setup_guide.pdf` + the Podman section in `hands-on-labs/01_torcs_lab/RESULTS.md`:
  ```bash
  sudo apt-get update && sudo apt-get -y install podman
  # Verify Compose V2 support (built into Podman 4.x). If `podman compose
  # version` is missing, fall back to: pip install podman-compose
  podman compose version
  # Pull the TORCS image once (~10 GB; do this off the critical path)
  podman pull docker.io/johnsloe/torcs-competition:amd64
  # UDP forwarding test (gotcha #13, 5 min) — must pass before parser work.
  # Uses tee-to-file because `nc -u` exit codes are useless; see gotcha #13 for the
  # slirp4netns→pasta fallback if this fails.
  podman run -d --name udptest -p 13001:3001/udp docker.io/library/alpine \
    sh -c "nc -u -l -p 3001 | tee /tmp/got"
  sleep 1 && echo "ping" | nc -u -w1 localhost 13001 && sleep 1
  podman logs udptest | grep -q ping && echo "UDP OK" || echo "UDP FAIL — see gotcha #13"
  podman stop udptest && podman rm udptest
  # Pin the TORCS image's real entrypoint path NOW so 3.1b's init script can chain to it
  podman inspect --format '{{json .Config.Entrypoint}}' docker.io/johnsloe/torcs-competition:amd64
  podman inspect --format '{{json .Config.Cmd}}' docker.io/johnsloe/torcs-competition:amd64
  # Record both in docs/plans/torcs-entrypoint.md (deleted on PR merge). 3.1b uses this.
  ```
- **Verify the host's subuid/subgid mapping** for rootless Podman (gotcha #11): `cat /etc/subuid /etc/subgid` — should list the current user with range. Missing means containers can't write to bind mounts as `student`; fix via `sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 $USER && podman system migrate`. Also `loginctl enable-linger $USER` on the deployment VM.
- **Skim the webinar materials** (~15 min) — `hands-on-labs/01_torcs_lab/05_webiner/torcs-transcript.txt` may flag a sensor gotcha, calibration ratio, or established pattern that saves debugging time later. Read; don't watch the 60 MB webm unless something in the transcript is unclear.
- **Fallback** (gotcha #9): if Podman/WSLg blocks past 5h, capture telemetry on the existing macOS environment and copy JSONL files to WSL — the parser is platform-agnostic.
- **Create `dev` branch off `main`** if not already present. All Week 1–3 commits land here.

#### 1.1b — RaceYourCode in the repo + .gitignore tightening (~20 min)
Per the locked repo-layout decision, gym_torcs lives in the repo root, not in `~/RaceYourCode`:
```bash
# If your existing capture-dir lives outside the repo, move it in
mv ~/RaceYourCode /home/patrick/overdrive-may-2026/RaceYourCode
# Or, on a fresh clone, extract from the lab's zip:
mkdir -p RaceYourCode && cd RaceYourCode
unzip ../hands-on-labs/01_torcs_lab/04_files/gym_torcs.zip
cd ..
```
Commit the unzipped `RaceYourCode/gym_torcs/*` (the canonical lab files, including `torcs_jm_par.py`). Add to `.gitignore`:
```
RaceYourCode/gym_torcs/__pycache__/
RaceYourCode/gym_torcs/*.pyc
RaceYourCode/gym_torcs/telemetry/    # runtime JSONL captures live in the shared volume, not the repo
RaceYourCode/gym_torcs/results/      # per-run TORCS artifacts
```
This makes the compose mount `./RaceYourCode:/home/student/workspace:Z` work out of the box on a fresh clone — no manual unzip step required of judges who pull `--profile torcs`.

**License attribution check (~5 min, review #8).** Committing `RaceYourCode/gym_torcs/*` redistributes the IBM lab files. The `hands-on-labs` repo is open and intended for participant use, but spend 30 seconds confirming the LICENSE in `hands-on-labs/01_torcs_lab/04_files/` (or repo root) permits redistribution. If permissive (MIT/Apache/etc.): add a one-line attribution to the README's "Acknowledgements" section ("gym_torcs files derived from IBM SkillsBuild hands-on-labs / 01_torcs_lab; see `LICENSE-LAB.md`"). If restrictive: revert this commit, keep `gym_torcs.zip` in `hands-on-labs/`, and add a `scripts/setup_torcs.sh` that judges run once before `--profile torcs up` to unzip into `RaceYourCode/`.

#### 1.2 — TORCS telemetry logger (~1h)
Edit `hands-on-labs/01_torcs_lab/04_files/gym_torcs/torcs_jm_par.py` to add an env-gated 3-line writer:
```python
if os.getenv("OVERRIDE_LOG_TELEMETRY"):
    with open(os.environ["OVERRIDE_LOG_TELEMETRY"], "a") as f:
        f.write(json.dumps(observation) + "\n")
```
Default write target inside the lab container is `/home/student/workspace/telemetry/<run_id>.jsonl`, which maps via the shared `torcs-telemetry` volume to `/app/data/telemetry/<run_id>.jsonl` inside the OVERRIDE container (per the compose architecture). This single path lets the same logger feed both the Week 1 fixture capture AND the Week 3 live-ingest endpoint — no schema change between the two paths.

Run twice with different settings, save outputs:
- `OVERRIDE_LOG_TELEMETRY=/home/student/workspace/telemetry/baseline.jsonl python torcs_jm_par.py` (defaults — Lab Task 1)
- `OVERRIDE_LOG_TELEMETRY=/home/student/workspace/telemetry/modified.jsonl ...` after `TARGET_SPEED = 150` (Lab Task 3)

Confirm `fuel`, `distFromStart`, `distRaced`, `curLapTime` are in the dumped observations (gotcha #2).

#### 1.3 — Implement `ingest/torcs_parser.py` + calibrate (~3.5h)
Mirror `ingest/fastf1_parser.py:1-340` (reference). Input: TORCS JSONL replay. Output: `list[LapFeatures]`.
- **JSONL safe-read** (gotcha #12) — skip incomplete tail lines and `json.JSONDecodeError` malformed lines silently. Don't add later; the live-ingest path will trip this within 5 minutes of judges driving.
- Lap segmentation from `distFromStart` start-line crossings.
- Sector splits from `distFromStart` against track length (1/3 / 2/3 fractions; pull per-track from a small `tracks.json` if time).
- Derive `harvest_mj` / `deploy_mj` from brake-on-time + throttle≥95% time, **scaled by calibrated constants** (below). Use `fuel` as cross-check.
- `soc_start = 1.0`, `soc_end = clamp(soc_start + (harvest - deploy)/BATTERY_CAPACITY_MJ, 0, 1)`, `soc_source = "derived"`.
- `override_uses = 0`, `boost_uses = 0`, `recharge_zones` derived post-hoc from per-sector harvest.
- Emit `note`: "Energy state derived from throttle/brake telemetry (TORCS has no native MGU-K data)."

**Calibration substep (~30 min, gotcha #1).** Run captured baseline through the parser; eyeball per-lap harvest/deploy totals against the 8.5 MJ cap parsed by `core/regs.extract_harvest_cap_mj`. Scale `HARVEST_KJ_PER_BRAKE_SECOND` / `DEPLOY_KJ_PER_FULL_THROTTLE_SECOND` until values land in the 4–7 MJ/lap range. Commit the chosen constants with a comment citing the calibration run. **Test gate locked in 1.6.**

#### 1.4 — `analysis/torcs_energy.py` (~3h)
Extract the 2026 hybrid bookkeeping (SoC/harvest/deploy synthesis) into a separate module so constants and derivation are testable independent of TORCS parsing. Future shared use with fastf1_parser (currently duplicates this math). *Cut candidate if Week 1 runs hot — see cuts list for the consequence.*

#### 1.5 — Commit the two pre-captured fixtures (~30 min)
- `data/samples/torcs_baseline.json` (from Lab Task 1 capture)
- `data/samples/torcs_modified.json` (from Lab Task 3, `TARGET_SPEED=150`)
- Update `api/main.py:_parse_upload` for `source=torcs` so it tries `torcs_parser` first and falls back to canonical-schema passthrough for backward compat with the existing `sample_torcs.json`.
- `mkdir -p data/samples/` first (dir doesn't exist).

#### 1.6 — Tests + calibration regression gate (~1.5h)
- `tests/test_torcs_parser.py` — golden tests against the two captured fixtures; assert lap counts, sector splits non-zero, SoC monotone where expected.
- **Calibration regression test** (locks gotcha #1 permanently):
  ```python
  def test_torcs_baseline_energy_calibration():
      laps = parse_torcs_session("data/samples/torcs_baseline.json")
      harvests = [L.harvest_mj for L in laps]
      deploys = [L.deploy_mj for L in laps]
      assert all(0 <= h <= 8.5 for h in harvests), "harvest violates 8.5 MJ cap"
      assert 3.0 <= statistics.median(harvests) <= 7.0, "median harvest out of realistic range"
      assert 3.0 <= statistics.median(deploys) <= 7.0, "median deploy out of realistic range"
      assert all(0 <= L.soc_end <= 1 for L in laps), "SoC out of bounds"
  ```
  Fires if anyone later tweaks the constants for the wrong reason. ~10 min to write.
- Extend `tests/test_api.py` — POST `torcs_baseline.json` to `/api/sessions?source=torcs` (mocked watsonx clients), verify clean Session round-trips.

#### 1.7 — `docs/adrs/ADR-002-torcs-as-primary-sandbox.md` (~1h)
TORCS is a learning-lab sandbox for proving decision logic; energy model is synthetic; FastF1 path complements with real data but lacks native MGU-K. Cite Sutton-Barto on RL sims as decision-proving environments.

#### 1.8 — Concurrency fix for fan-mode save (~1.5h, **in hard floor**)
`api/main.py:351-372` currently does load → modify → save_session for the whole session per fan request. Two parallel calls clobber each other. Fix:
- Add `save_recommendations_only(session_id, recommendations)` to `api/storage.py` that writes just `recommendations.json` via `tempfile + os.replace` (atomic on POSIX).
- Replace the full `save_session` call in `get_zone` with the new helper.
- Add a per-session `asyncio.Lock` using `setdefault` (gotcha #3) to serialize fan-mode writes against the same session.
- Test: `tests/test_api.py` — fire 5 concurrent `?mode=fan` requests on the same session, assert all 5 fan fields land.

#### 1.9 — Stale plan deletion (~5 min)
Delete in the same PR as the TORCS work (per `.bob/rules.md`):
- `docs/plans/phase-1-foundation-implementation.md` (P1 shipped)
- `docs/plans/zone-patterns.md` (P2.1 shipped)
- `docs/plans/p2.5-docling-kicker.md` (G-4 closed)
- `docs/plans/discord-pitch-feedback.md` (P1.2 closed)
- `docs/plans/quick-follow-up-on-github-invite.md` (moot now that lab is in repo)

Keep `docs/plans/previous-co-work-conversations.md` (transparency about development process — rubric-positive). Already in `.dockerignore`.

#### 1.10 — Post-rename stale-text scan (~5–10 min)
The Torx→TORCS rename (commit f4191df) may have left stale visible text in screenshots. Scan only — actual re-captures defer to Week 3 (so we don't re-shoot the same screenshot twice once FR-8 changes the Engineer card).
```bash
grep -rn -i "torx" ui/ assets/ recordings/ 2>&1 | grep -v node_modules
```
Document which assets need re-capture in Week 3 step 3.5.

#### 1.11 — TTM-R2 deferral cleanup (~30 min)
- Replace 0-byte `core/forecasting.py` with the docstring stub (3 lines, references roadmap P2.2 + ADR-001).
- Update `ui/src/components/EnergyCurve.tsx` empty-state — currently "No lap data to chart." When `forecast === null` AND laps are present, render "5-lap forecast (TTM-R2) deferred to v1.1 — pipeline runs end-to-end without forecasting per the graceful-degradation guardrail."
- README "Limitations": add "TTM-R2 5-lap SoC forecasting (FR-3): deferred to v1.1 per the graceful-degradation guardrail."
- `docs/03-prd.md` FR-3: append "v1.0 ships with forecast=None; v1.1 wires TTM-R2 inference."
- `docs/02-ai-and-technical-approach.md` and `docs/02-problem-and-solution.md`: change "six IBM technologies" → "five" with TTM-R2 in a "v1.1" row.

### Week 2 (May 18–24) — What-if FR-8 + LLM abstraction + observability (~33h: 25h sub-tasks + 8h integration contingency)

Week 2 is the integration-heavy block (FR-8 touches schema + perturbation + endpoint + UI + tests + cache; the LLM abstraction touches reasoning + fan_mode + env config). The +8h contingency above sub-task totals is honest budget for realistic integration friction. Track it explicitly so the buffer doesn't burn silent.

#### 2.1 — `docs/plans/whatif-semantics.md` (~30 min, **blocking 2.2**)
Write BEFORE coding. Resolve the three ambiguities:
- `delay_first_deploy(n)`: if the first deploy IS on lap 1, perturbation **shifts** it to lap 1+n (energy budget conserved), not skipped.
- `skip_harvest_zone(zone_id)`: harvest in that zone is zeroed; SoC trajectory recomputes downstream from the perturbation point (energy is **lost**, not deferred).
- `extend_override(zone_id, laps=1)`: default duration 1 lap; deploys an additional 0.5 MJ in the lap after the original zone.
- Schema-hashable WhatIfRequest payload for caching.

#### 2.2 — Schema + perturbation functions (~4h)
- Add `WhatIfRequest`, `WhatIfResult` to `ingest/schema.py` (Pydantic, frozen).
- New module `analysis/perturbations.py` — three pure functions `apply_<name>(laps, request) → laps`. No pipeline knowledge. Unit-test each in isolation.
- **If 1.4 was cut:** import energy helpers from `ingest/torcs_parser.py` directly; document the cross-domain coupling in the module docstring; tag for v1.1 cleanup.

#### 2.3 — Endpoint (~3h)
`POST /api/sessions/{session_id}/what-if` in `api/main.py`:
- Validate session exists, load it.
- Apply perturbation function to `session.laps`.
- Hash the request per gotcha #4 → check disk cache at `data/sessions/{id}/whatif/{hash}.json`.
- If miss: call `run_pipeline(perturbed_laps, ...)` (reuse `core/pipeline.py:269-310` — do NOT write a parallel pipeline). Persist result to cache.
- Return `WhatIfResult` with original + perturbed Recommendation pairs.
- Reuses existing watsonx clients via `api/main.py:112-121` dependency providers.

#### 2.4 — UI (~6h)
- `ui/src/components/WhatIfPanel.tsx`: three radio options for perturbation type + parameter input + "Run scenario" button.
- `ui/src/components/WhatIfDiff.tsx`: side-by-side Recommendation cards (original vs perturbed). NO animation; clear "Before / After" labeling per UI doc §4.3.
- Wire into `SessionPage.tsx` Engineer mode only (FR-8.3); hide in Fan mode.
- `ui/src/api/client.ts` adds `runWhatIf(sessionId, request)` including fixture-mode synthesis for offline UI dev.

#### 2.5 — Tests (~3h)
- `tests/test_perturbations.py` — golden tests for each perturbation function.
- `tests/test_api.py` — what-if endpoint happy path + cache hit + invalid zone_id 404.

#### 2.6 — P3.6 observability screenshot (~2h)
- `OVERRIDE_TRACING=otlp OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317` with local Jaeger (`podman compose --profile observability up jaeger`).
- POST `data/samples/torcs_baseline.json` → capture `assets/screenshots/jaeger-trace.png` showing reason → validate → guardian → regs.
- README: add to "What it looks like" table.
- Delete `docs/plans/p3.6-jaeger-trace-capture.md` in the same PR (plan-file lifecycle).

#### 2.7 — Sessions list discipline cleanup (~30 min)
Don't wire `GET /api/sessions` (Tier-2 stays Tier-2). Update `ui/src/pages/SessionsPage.tsx` body to match the FR-8/TTM v1.1 framing pattern — explicit, intentional, not "coming soon".

#### 2.8 — Regenerate engineer_happy_demo fixture against real TORCS (~1h, **high-value add**)
After 2.3 lands, pipe `data/samples/torcs_baseline.json` through the full pipeline (reasoning + Pass-1 + Pass-2 + Fan + one what-if) and save as `tests/fixtures/torcs_engineer_demo.json`. Update `ui/src/api/client.ts` `fixtureNameForSessionId` routing so `s_torcs_engineer_demo` resolves to it. Upgrades rubric story from "we have a TORCS parser, here's a synthetic demo" → "the demo you're watching is a real lab session piped through the full pipeline." Watsonx cost: ~$0.05–0.10 (pipeline + Fan translation across 5 zones).

#### 2.9 — Pre-record Segment 3 retake (~1h)
End of Week 2, immediately after FR-8 UI lands. Record the what-if click flow once. If anything looks off (cross-fade, layout, timing), discover it now — not during the Week 3 video block when retake time is at a premium.

#### 2.10 — Ollama runtime abstraction + .env switch (~4h)
The lab's TORCS container ships granite4:350m via Ollama at port 11434. User direction: keep it shipped, route the OVERRIDE chat path through it when `OVERRIDE_LLM_RUNTIME=ollama`, default to watsonx. `core/reasoning.py` already defines a `WatsonxChatClient` Protocol; this is structural extension, not architectural overhaul.

- **New module `core/llm_clients/ollama.py`** — implements the existing `WatsonxChatClient` Protocol against Ollama's `/api/chat` endpoint. Honors `OVERRIDE_OLLAMA_BASE_URL` (default `http://torcs:11434` in compose, `http://localhost:11434` for non-compose dev), `OVERRIDE_OLLAMA_MODEL` (default `granite4:350m`).
- **Response-shape adapter is load-bearing**: Ollama's `/api/chat` returns `{"message": {"content": "..."}}`; watsonx's chat API returns `{"choices": [{"message": {"content": "..."}}]}`. The `OllamaChatClient` normalizes to the same `ChatResponse` Pydantic shape `WatsonxAIChatClient` produces, so `core/reasoning.py` and `core/fan_mode.py` see identical types. Write the shape adapter test first; the rest of the client is plumbing.
- **Factory in `api/main.py`** — `get_chat_client()` reads `OVERRIDE_LLM_RUNTIME` (default `"watsonx"`); returns `OllamaChatClient()` if `"ollama"`, else the existing watsonx impl. Same Protocol means zero call-site changes in `core/reasoning.py`, `core/fan_mode.py`.
- **Fail-loud startup probe** (review #2): when `OVERRIDE_LLM_RUNTIME=ollama`, on app boot the factory probes `GET {OVERRIDE_OLLAMA_BASE_URL}/api/tags` with a 2-second timeout. If unreachable, refuse to boot with a clear error: *"OVERRIDE_LLM_RUNTIME=ollama requires `podman compose --profile torcs up` or `OVERRIDE_OLLAMA_BASE_URL` pointing at a reachable ollama instance. Got connection error: {err}"*. Catches the silent 60-second-connection-refused failure mode at the front door, not inside the first reasoning call.
- **Constraints documented**: Guardian (`core/guardian.py`) and Embedding (`core/regs.py`) stay watsonx-only — granite4:350m doesn't expose the Guardian BYOC scoring API and the multilingual embedding model isn't trivially swappable. **`WATSONX_API_KEY` is required even in ollama mode.** Full ollama-only mode is v1.1.
- **`.env.example` additions**:
  ```
  # LLM runtime — chat (reasoning + Fan Mode) only. Guardian + embedding stay on watsonx.
  # NOTE: ollama mode covers chat only. Guardian (Pass-2 safety) and Embedding
  # (regulation retrieval) still call watsonx — WATSONX_API_KEY remains required.
  # Full ollama-only mode is v1.1. Without watsonx creds, ollama mode boots but
  # the pipeline fails at Pass-2 / regulation grounding.
  OVERRIDE_LLM_RUNTIME=watsonx          # or "ollama" to route chat to the TORCS container's granite4:350m
  OVERRIDE_OLLAMA_BASE_URL=http://torcs:11434
  OVERRIDE_OLLAMA_MODEL=granite4:350m
  ```
- **Tests** — `tests/test_llm_clients_ollama.py` mocks the HTTP layer (Ollama API responses), asserts request shape, response-shape normalization, and the startup probe refusing to boot on connection error. Smoke-only; no live ollama dependency in CI-equivalent local pytest runs.
- **End-to-end manual gate (~30 min inside the 4h)** (review #10): after the unit tests pass, run a real `ollama serve` locally (or use the TORCS container), set `OVERRIDE_LLM_RUNTIME=ollama`, POST `data/samples/torcs_baseline.json` to `/api/sessions`, verify the resulting `Recommendation.reasoning` is structurally valid (cause/consequence/recommendation/confidence/chain). Smaller model + lower confidence acceptable; structural mismatch is not. **This is the only end-to-end test of the ollama path; the unit tests are mock-only and won't catch a JSON-shape mismatch with the real Ollama API.**
- **ADR-003** — `docs/adrs/ADR-003-llm-runtime-abstraction.md`: document hybrid posture, the v1.1 all-ollama migration path, and why Guardian/Embedding stay on watsonx.
- **Demo invariant**: the video uses `OVERRIDE_LLM_RUNTIME=watsonx` (default). The ollama path is for the v1.1 migration story and for offline development inside the TORCS container.

### Week 3 (May 25–28) — Podman compose (with TORCS) + video + VM dry-run + submit (~29h)

#### 3.1 — Multi-stage Containerfile/Dockerfile + podman-compose (~5–7h)
**Containerfile** (Podman's name for Dockerfile; either works since the syntax is identical, but `Containerfile` is the Podman convention — pick one and document):

Stage 1 `docker.io/node:20-alpine` (gotcha #7 — full image path):
- Copy `ui/package*.json`; `npm ci`; copy `ui/`; `npm run build` → `ui/dist/`.

Stage 2 `docker.io/python:3.12-slim` (gotcha #5):
- `RUN apt-get update && apt-get install -y --no-install-recommends build-essential` first. Fall back to `python:3.12` if pyarrow/docling wheels still fail.
- pip install from `requirements.txt`.
- Copy `core/`, `api/`, `ingest/`, `analysis/`, `prompts/`, `data/regs/extracted_chunks.sample.json`, `models.json`, `core/validator.yaml`, `guardian/byoc_criteria.yaml`.
- Copy `ui/dist/` from stage 1 into `/app/ui/dist/`.
- Mount `ui/dist/` via `StaticFiles` in `api/main.py` so single image serves both API and UI at port 8000.
- `HEALTHCHECK CMD curl -f http://localhost:8000/api/health || exit 1` per `docs/04-api.md` §8.
- `ENTRYPOINT ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

**`docker-compose.yml`** — three-service stack per the architectural decision section (gotcha #6 — NO `version:` line):
- `override` service: build context `.`, port `8000:8000`, `env_file: .env`, volumes `./data/sessions:/app/data/sessions` for session persistence + `torcs-telemetry:/app/data/telemetry` for live-ingest path. On `override-net`.
- `torcs` service: `docker.io/johnsloe/torcs-competition:amd64`, ports `5900:5900` + `6080:6080` + `3001:3001/udp` + `11434:11434` (Ollama), volumes `./RaceYourCode:/home/student/workspace:Z` + `torcs-telemetry:/home/student/workspace/telemetry:Z` + `./scripts/torcs_container_init.sh:/usr/local/bin/torcs_init.sh:Z,ro`, entrypoint override to the init script (fixes Ollama chown + VS Code hang per gotcha #10). **`profiles: [torcs]`** so default `up` skips the 10 GB pull (gotcha #8). On `override-net`.
- `jaeger` service: `docker.io/jaegertracing/all-in-one`, ports `16686:16686` + `4317:4317`, **`profiles: [observability]`**.
- Top-level `volumes: { torcs-telemetry: {} }` and `networks: { override-net: {} }`.

**`.containerignore`** (Podman's name; `.dockerignore` also works — Podman reads both):
```
.git
.venv
.venv-langflow
ui/node_modules
ui/dist
__pycache__
*.pyc
.pytest_cache
recordings/
data/regs/*.pdf
data/regs/extracted/
.env
hands-on-labs/
docs/plans/previous-co-work-conversations.md
*.DS_Store
```
*Note:* `hands-on-labs/` is excluded from the build context (it's huge and the TORCS image pulls itself via compose), but the directory is bind-mounted at runtime into the `torcs` service for `gym_torcs/` access. Excluding from build ≠ excluding from runtime mounts.

Delete empty `.github/workflows/ci.yml` (empty placeholder is misleading; CI not in scope).

README quickstart now has three modes:
```bash
cp .env.example .env  # fill WATSONX_API_KEY + WATSONX_PROJECT_ID

# Mode 1 — OVERRIDE only (fast; default; uses pre-captured TORCS fixtures)
podman compose up

# Mode 2 — OVERRIDE + live TORCS (drive in noVNC at :6080; ~10 GB image pull first time)
podman compose --profile torcs up

# Mode 3 — OVERRIDE + Jaeger (for trace capture)
podman compose --profile observability up
```
Note: "Local-venv path still documented below for hacking on the code. macOS/Mac Silicon: substitute `:arm64` for `:amd64` in the TORCS image tag."

#### 3.1b — `scripts/torcs_container_init.sh` (~30 min, part of 3.1)
Wraps the lab's container entrypoint to absorb the two known bugs (gotcha #10) before TORCS itself starts. **The real entrypoint path was pinned in 1.1 via `podman inspect`** — no late discovery here:
```bash
#!/usr/bin/env bash
set -e
# Fix the Ollama directory ownership bug from RESULTS.md (ships broken on every fresh start)
chown -R student:student /opt/ollama 2>/dev/null || true
# Narrow chown on /tmp — only Ollama's own paths; never the whole tree (review #5)
chown student:student /tmp/ollama.log /tmp/ollama-* 2>/dev/null || true
# Suppress the VS Code extension install hang — we don't edit code inside the container
pkill -f "code.*install-extension" 2>/dev/null || true
grep -q DONT_PROMPT_WSL_INSTALL /etc/environment || \
  echo "DONT_PROMPT_WSL_INSTALL=1" >> /etc/environment
# Chain to the image's original entrypoint (path pinned in docs/plans/torcs-entrypoint.md from 1.1).
# Default below is the lab image's documented path; substitute if the 1.1 inspect found different.
exec /entrypoint.sh "$@"
```
Make executable (`chmod +x`), commit. Compose mounts it read-only into `/usr/local/bin/torcs_init.sh` and overrides the container's `entrypoint` to invoke it. Delete `docs/plans/torcs-entrypoint.md` in the same PR (plan-file lifecycle — it served its purpose).

#### 3.2 — Realtime TORCS-live ingest endpoint (~2h, with volume-permission test)
*(Moved adjacent to compose for narrative locality; was 3.6 in v4.)*

New endpoint `POST /api/sessions/torcs-live` in `api/main.py`:
- Body: `{ "run_id": "<run>" }` (Pydantic-validated; pattern `^[A-Za-z0-9_-]+$`).
- Reads `/app/data/telemetry/<run_id>.jsonl` (404 if missing, 400 if empty). Uses the gotcha #12 safe-read.
- Calls `ingest.torcs_parser.parse_torcs_session(jsonl_path)` → `list[LapFeatures]`.
- Pipes through `run_pipeline(...)` (same call site as `POST /api/sessions`, same dependency providers).
- Calls `save_session(session)`; returns the full Session.
- Reuses chat/embedding/guardian clients via `Depends()`.

New helper endpoint `GET /api/torcs-status` (~15 min):
- Lists `*.jsonl` files in `/app/data/telemetry/` (sorted by mtime desc).
- Returns `{ "available": true|false, "runs": [{"run_id": "...", "size_bytes": N, "lap_count_estimate": N}] }`.
- 200 always (no 404 when empty — just `available: false`).
- Used by the UI to enable/disable the "Ingest live TORCS run" button without polling.

UI addition (`ui/src/pages/UploadPage.tsx`, ~30 min):
- Below the upload drop zone, conditional banner: "Live TORCS detected — N runs available" with a button per run that posts to `/api/sessions/torcs-live`.
- Banner only shows when `GET /api/torcs-status` returns `available: true`.
- Pure progressive enhancement: zero impact when `--profile torcs` isn't running.

**Volume-permission UID-remap test (~20 min, gotcha #11)** — fail-fast at the end of 3.2:
```bash
podman compose --profile torcs up -d
podman exec torcs sh -c "touch /home/student/workspace/telemetry/test.txt && ls -la /home/student/workspace/telemetry/test.txt"
podman exec override sh -c "ls -la /app/data/telemetry/test.txt && cat /app/data/telemetry/test.txt"
```
If permission-denied: pin `user: "1000:1000"` on the `override` service in compose, OR add `chmod 0644` to the gym_torcs telemetry-logger snippet, OR document the workaround. Discovery here = absorbable; discovery at T-24h = panic.

Tests (`tests/test_api.py`, ~30 min):
- Mount a temp dir as the telemetry path via env var; write a known JSONL fixture (with one intentionally-incomplete tail line per gotcha #12); POST `/api/sessions/torcs-live`; verify session round-trips and the malformed line is silently skipped.
- `GET /api/torcs-status` happy/empty cases.

**True streaming** (SSE pushing per-lap zone detections as gym_torcs writes them) is **out of scope for v1** — documented in README "What's coming next" as v1.1 alongside TTM-R2.

#### 3.3 — README + docs final polish (~2h)
- Refresh the live-performance table with current measurements after FR-8 + Docker.
- "What's coming next" section: TTM-R2 v1.1, Sessions list v1.1, CI v1.1, Section B Sporting Regs v1.1.
- Verify zero hardcoded FIA article numbers: `grep -rE "C5\.18|article [0-9]" --include="*.py" --include="*.tsx" --include="*.md"`.
- One line: "CI workflows planned for v1.1. Current quality gate: pytest -q (231/231 unit + 4/4 network) + npm run typecheck && npm run build per docs/plans/final-lock-checklist.md T-72h pre-flight."

#### 3.4 — `recordings/` git policy decision (~10 min)
Decide before video re-record:
- `recordings/*.mov` (masters, ~200 MB total) — `.gitignore` them; not part of the repo deliverable.
- `recordings/voiceover-seg-*.m4a` (stems, ~10 MB) — track them; submission-grade evidence a reviewer might want.
- `recordings/final.mp4` — track if it fits; reference the YouTube URL otherwise.
Add the chosen rules to `.gitignore` and commit.

#### 3.5 — Submission portal copy refresh (~30 min)
`docs/plans/submission-portal-copy.md` was drafted pre-TORCS, pre-FR-8. Walk through with current truth before T-2h paste:
- "How it works" paragraph — mention TORCS as primary lab data source alongside FastF1.
- Tech stack section — five IBM technologies (TTM-R2 v1.1 row), Podman compose with TORCS in the stack as the shipping shape.
- "What we built" framing — include what-if interactive counterfactuals.
- **If the VM dry-run in 3.7 provisions a hosted demo URL**, paste it alongside the GitHub URL in the BeMyApp portal "How to try it" section. Note: ephemeral — tear-down after May 31.

#### 3.6 — Video re-record (~12h, with retake buffer) + asset re-captures (~30 min)
Per the locked 2:55 script in `docs/plans/video-script.md`, re-shoot:
- Segment 3 (demo flow): include the what-if toggle moment — pick a zone, run a perturbation, see the side-by-side diff. (Pre-recorded in 2.9; redo only if retake required.)
- Segment 4 (explainability): refresh against current Engineer Mode card + new Jaeger screenshot beat.
- Segment 7 (closing): voiceover pace check; tighten if it positions OVERRIDE smaller than what's now shipped.
- Audit every cursor stroke for stale filenames (`sample_torx` etc. — should be `torcs` everywhere post-f4191df).
- Final cut ≤2:55; upload to YouTube **unlisted** with public switch reserved for T-0.

**Asset re-captures** (deferred from 1.10): re-shoot the screenshots flagged in the Week 1 scan, now that the FR-8 what-if rail is in its active state (not the disabled stub).
- `assets/screenshots/upload.png` (post-rename text)
- `assets/screenshots/dashboard.png` + `engineer-mode.png` (now showing the what-if panel active)
- `assets/demo.gif` (re-export only if visible `sample_torx` text found)

Budget breakdown for video: rewrite voiceover lines (~30 min) + pace check (~15 min) + voiceover record with retakes (~45 min) + Segment 3 screen-capture retakes (~45 min) + Segment 4 (~30 min) + edit timeline (~1.5h) + export MP4 (~20 min) + YouTube upload (~20 min) + retake-of-retakes contingency (~3–4h). Total ~12h realistic.

#### 3.7 — Ephemeral Ubuntu Linux VM deployment dry-run (~1.5h)
Per the locked deployment-target decision, OVERRIDE ships as an **ephemeral hosted demo** for the judging window. **Hetzner CX32 confirmed** (4 vCPU / 8 GB RAM / 80 GB NVMe, ~$11.40/mo prorated ≈ $1.50–2.00 for the 4–5 day window). CX32 handles the 10 GB TORCS image + everything else with margin and supports `--profile torcs up` hosted (CX22 would have been default-profile-only).

```bash
# On the fresh VM (Ubuntu 22.04 LTS or 24.04 LTS to match WSL)
ssh user@vm-public-ip
sudo apt-get update && sudo apt-get -y install podman git
loginctl enable-linger $USER     # so containers survive SSH disconnect
git clone https://github.com/<user>/overdrive-may-2026.git
cd overdrive-may-2026
cp .env.example .env             # paste WATSONX_API_KEY + WATSONX_PROJECT_ID
podman compose up -d             # default profile; verify :8000 responds
# Optional: bring up live TORCS path (10–15 min first pull is expected, documented in README)
podman compose --profile torcs up -d
# Verify noVNC at :6080 lands the XFCE desktop (only reachable from the VM itself — see firewall below)
```

**Firewall rules (review #5 — noVNC has no auth):**
- **Open externally:** port 80 + 443 (Caddy → 8000). That's it.
- **Closed externally:** 8000, 5900, 6080, 3001/udp, 11434, 16686. Live-TORCS noVNC desktop is **only reachable via SSH tunnel from the VM operator's laptop** (`ssh -L 6080:localhost:6080 user@vm`). Judges hitting the public URL get the fixture-driven OVERRIDE UI only.
- README states explicitly: *"The hosted demo URL exposes the fixture-driven path only. Judges who want to drive live TORCS clone the repo and `podman compose --profile torcs up` locally."*
- Closes a real attack surface — noVNC over the open internet with no auth is a takeover vector.

**TLS — skip-TLS for ephemeral (review #7).** A 4–5 day demo on a non-production system doesn't justify domain + cert lifecycle. Decision: judges access `http://<vm-public-ip>:8000` directly (or `http://override-demo-N.example.com` if a static A record is cheap to set up). HTTP-not-HTTPS is acceptable for a hackathon submission; the rubric scores architecture, not certificate management. If a polished URL is wanted, **DuckDNS + Caddy auto-issuance** is the 10–30 min path (typically ~10 min when DNS propagates fast and Let's Encrypt's HTTP-01 challenge succeeds first try; can stretch to ~30 min if DNS is slow or the challenge retries). `override.duckdns.org` → A record to VM IP, `caddy reverse-proxy --from override.duckdns.org --to localhost:8000` — note: foreground/ephemeral, cert re-acquires on Caddy restart (rate-limited but fine for a 4–5 day window); a proper `Caddyfile` is v1.1. **Fallback** if the cert challenge fails: ship `http://<vm-public-ip>:8000` directly, no TLS — covers any hiccup without slipping the dry-run budget.

**Post-smoke snapshot (review #6).** After `podman compose up` succeeds and the fresh-clone smoke is green, take a VM snapshot. If the VM dies mid-judging window (rare but real), recovery is `restore snapshot` not `re-walk the entire 3.7 procedure under pressure`. Hetzner snapshots are ~$0.012/GB/month — call it $1 for the window. Record snapshot ID in `docs/07-deployment.md`.

**Document in `docs/07-deployment.md`:** VM size (CX32), OS (Ubuntu 22.04 / 24.04), firewall rules (per above), TLS choice (skip / DuckDNS / Caddy), snapshot ID, tear-down command (`podman compose down -v; cd ~; rm -rf overdrive-may-2026`), tear-down date (post-May-31).

**Total cost check:** VM ~$2 + snapshot ~$1 + watsonx burn ~$1–10 = **~$4–13 USD total** for the 19-day build + judging window. CA$10 watsonx budget alerts on Runtime + Studio cover surprises.

### Final lock (May 29–31) — Phase 5 (~6h)

Execute `docs/plans/final-lock-checklist.md` as-written, plus these additions:

- **T-72h (May 29):** Code freeze. `pytest -q -m "not network"` green. `npm run build` green. No credentials in git. All stale plan files deleted. Tag `v1.0.0-submission`.
  - **NEW:** Fresh-clone smoke — `git clone <your repo> /tmp/override-fresh && cd /tmp/override-fresh && podman compose up`; verify port 8000 serves UI; upload a TORCS sample → end-to-end clean. Then `podman compose --profile torcs up` once to confirm the live-TORCS path also works post-clone. Catches "I forgot to commit a file" failure.
  - **NEW:** `git ls-files | xargs wc -c 2>/dev/null | sort -rn | head -20` — catches large files accidentally tracked (rogue .mov, brand asset bloat).
  - **NEW:** Risk register sweep — walk `docs/05-risk-register.md`; mark resolved (R1, R3, R4, R13, R14, R16) closed; update likelihood on de-risked items (R5 not triggered, R18 mitigated via Essentials upgrade). ~15 min; signals to judges that risk discipline was maintained through the build.
  - **NEW:** Watsonx burn check — expected total over the 19-day window: $1–10 USD on Essentials (Week 2 retesting + Jaeger captures the hot spot). CA$10 budget alerts on Runtime + Studio cover surprises.
  - **NEW:** Merge `dev` → `main` only at this gate. Tag from `main`.
- **T-24h (May 30):** Clean-machine walk with `podman compose up` on a fresh user account. README cold-read. All 7 screenshots present and current. Optionally run `podman compose --profile torcs up` once to confirm the live path works on a fresh user account too.
- **T-2h (May 31 afternoon):** BeMyApp portal copy from `docs/plans/submission-portal-copy.md` (already refreshed in 3.4). Banner, logo, demo GIF uploaded. Video URL switched public. Preview page read in incognito.
- **T-0 (May 31 8 PM ET):** **Publish.** Confirmation email check. Lock at 11 PM ET (1h buffer before 11:59 PM deadline).

## Critical files modified (by area)

| Area | Paths |
|---|---|
| TORCS data path | `hands-on-labs/01_torcs_lab/torcs_jm_par.py`, `ingest/torcs_parser.py`, `analysis/torcs_energy.py`, `api/main.py:_parse_upload`, `data/samples/torcs_*.json` (new), `tests/test_torcs_parser.py` (new), `docs/adrs/ADR-002-torcs-as-primary-sandbox.md` (new) |
| FR-8 what-if | `ingest/schema.py` (+WhatIfRequest/Result), `analysis/perturbations.py` (new), `api/main.py` (new endpoint), `api/storage.py` (whatif cache helpers), `ui/src/components/WhatIfPanel.tsx` + `WhatIfDiff.tsx` (new), `ui/src/api/client.ts`, `ui/src/pages/SessionPage.tsx`, `tests/test_perturbations.py` (new), `tests/test_api.py` (extend), `docs/plans/whatif-semantics.md` (new, deleted on PR merge) |
| Concurrency fix | `api/main.py:351-372`, `api/storage.py` (new `save_recommendations_only`), `tests/test_api.py` |
| TTM-R2 deferral | `core/forecasting.py` (stub docstring), `ui/src/components/EnergyCurve.tsx` (empty-state text), `README.md`, `docs/03-prd.md`, `docs/02-ai-and-technical-approach.md`, `docs/02-problem-and-solution.md` |
| Podman compose | `Containerfile` (or `Dockerfile`), `docker-compose.yml` (new — three services: override / torcs / jaeger; two profiles: torcs / observability; one shared volume: torcs-telemetry; `./RaceYourCode` mount), `.containerignore` (new), `api/main.py` (mount StaticFiles + new live-ingest endpoint + status helper), `scripts/torcs_container_init.sh` (new — Ollama chown + VS Code hang fixes), `README.md` |
| Realtime live-ingest | `api/main.py` (`POST /api/sessions/torcs-live`, `GET /api/torcs-status`), `ingest/torcs_parser.py` (parametrize file-path entry point + JSONL safe-read), `ui/src/pages/UploadPage.tsx` (live-TORCS detection banner), `ui/src/api/client.ts` (`runTorcsLive`, `torcsStatus`), `tests/test_api.py` (live-ingest happy + empty + invalid-run-id + malformed-tail-line) |
| LLM runtime abstraction | `core/llm_clients/ollama.py` (new — `OllamaChatClient` impl of the existing Protocol), `api/main.py:get_chat_client` (factory reads `OVERRIDE_LLM_RUNTIME`), `.env.example` (new env vars), `docs/adrs/ADR-003-llm-runtime-abstraction.md` (new), `tests/test_llm_clients_ollama.py` (new, mocked HTTP) |
| RaceYourCode in repo | `RaceYourCode/gym_torcs/*` (committed unzip of `hands-on-labs/01_torcs_lab/04_files/gym_torcs.zip`), `.gitignore` (telemetry/, results/, __pycache__) |
| VM deployment | `docs/07-deployment.md` (refresh — VM size, OS, firewall rules, TLS via Caddy, tear-down command) |
| Cleanup | Delete `.github/workflows/ci.yml`, `docs/plans/phase-1-foundation-implementation.md`, `docs/plans/zone-patterns.md`, `docs/plans/p2.5-docling-kicker.md`, `docs/plans/discord-pitch-feedback.md`, `docs/plans/quick-follow-up-on-github-invite.md`, `docs/plans/p3.6-jaeger-trace-capture.md` (after Week 2), `docs/plans/torcs-entrypoint.md` (created in 1.1, deleted in 3.1b after init script chains to the pinned entrypoint), `docs/plans/whatif-semantics.md` (created in 2.1, deleted when FR-8 merges) |
| Observability | `assets/screenshots/jaeger-trace.png` (new), `README.md` (link it) |
| SessionsPage discipline | `ui/src/pages/SessionsPage.tsx` (v1.1 framing) |
| Asset refresh (Week 3) | `assets/screenshots/upload.png`, `dashboard.png`, `engineer-mode.png`, `assets/demo.gif` (conditional) |
| Demo fixture upgrade | `tests/fixtures/torcs_engineer_demo.json` (new), `ui/src/api/client.ts` (routing) |
| Submission assets | `recordings/` (new takes per 3.3 policy), `docs/plans/submission-portal-copy.md` (refresh), YouTube (unlisted → public), BeMyApp portal |

## Existing utilities to reuse (don't reinvent)

- **Parser pattern:** `ingest/fastf1_parser.py:1-340` — copy its derivation constants and `parse_fastf1_lap` shape for torcs_parser. **Then calibrate** (gotcha #1).
- **Pipeline orchestration:** `core/pipeline.py:269-310` `run_pipeline(...)` — already accepts `forecast_fn=None`; what-if just calls it with perturbed laps.
- **Watsonx client deps:** `api/main.py:112-121` `get_chat_client / get_embedding_client / get_guardian_client` — reuse via `Depends()` in the what-if endpoint.
- **Storage atomic write pattern:** none today (gap); model the new `save_recommendations_only` after `api/storage.py:51-84` + tempfile/os.replace.
- **Session/Recommendation Pydantic shapes:** `ingest/schema.py` — extend, don't fork.
- **UI fixture switching:** `ui/src/api/client.ts:166-185` — what-if needs the same `{ fixture }` pattern; add a `runWhatIf` method that synthesizes a diff from the fan_mode fixture in fixture mode.
- **Empty-state component:** `ui/src/components/EmptyStates.tsx` — already used for grounding-pending banner; reuse for TTM-R2 deferral badge and SessionsPage v1.1 framing.

## Verification (weekly gates with green/yellow/red rule)

**End of Week 1:**
- `.venv/bin/pytest -q -m "not network"` — expect ~241 green (231 baseline + 10 new TORCS tests).
- Launch `uvicorn api.main:app --port 8000` + `cd ui && npm run dev`.
- Drop `data/samples/torcs_baseline.json` on the upload page → session lands on dashboard, recommendations render, regulation citation links work.
- Toggle Fan mode on all zones simultaneously; verify all fans persist (concurrency fix).
- UDP port 3001 forwarding test (gotcha #13) green from 1.1.
- `RaceYourCode/gym_torcs/` exists in repo with the lab files; `.gitignore` covers runtime artifacts.
- `git log --oneline -8` on `dev` shows the five stale plans deleted alongside the features shipping them.
- **Apply green/yellow/red rule** (gotcha #14): green → proceed; yellow → trigger cut #1; red → trigger cuts #1+#2.

**End of Week 2:**
- ~270 tests green (~241 from Week 1 + perturbations + what-if endpoint + ollama-client mocked).
- POST a what-if request via curl: get a perturbed Recommendation diff back.
- UI: pick a zone, change `delay_first_deploy` to 2, see the Before/After cards diff correctly.
- Run with `OVERRIDE_TRACING=otlp` + Jaeger; screenshot captured.
- Set `OVERRIDE_LLM_RUNTIME=ollama` against a locally-running ollama+granite4:350m; verify reasoning endpoint still produces a structured Recommendation (slower, smaller model, lower confidence acceptable).
- Segment 3 retake recorded (2.9) — review for cross-fade / layout / timing issues.
- **Apply green/yellow/red rule.**

**End of Week 3:**
- `podman compose up` on a fresh clone → port 8000 serves both UI and API → upload a TORCS fixture → end-to-end clean.
- `podman compose --profile torcs up` → noVNC at `:6080` lands the XFCE desktop; `torcs_jm_par.py` writes JSONL; UI "Ingest live TORCS run" button fires; session lands on dashboard.
- `podman compose --profile observability up` → Jaeger UI at `:16686` shows the pipeline trace.
- Video timed at ≤2:55.
- YouTube unlisted URL plays in incognito.
- **Apply green/yellow/red rule.** Final week — yellow/red here means a same-day catch-up rather than a cut.

**Final lock day:** `final-lock-checklist.md` walked end-to-end + the four NEW T-72h sub-steps (fresh-clone smoke, large-file scan, risk register sweep, watsonx burn check).

## Cuts if time slips

In order of what gets dropped first:
1. **Second TORCS fixture** (`torcs_modified.json`) — ship just the baseline; one fixture is enough for the video.
2. **WhatIfPanel UI polish** (animation, parameter sliders) — ship radios + button only.
3. **Demo fixture regeneration** (2.8) — keep the existing engineer_happy_demo synthetic fixture.
4. **Hosted demo URL** (3.7) — skip cloud-VM provisioning; README-only deploy with `podman compose up` on a local machine. Judges still run it; rubric loses the "implementation & feasibility" hosted-demo bullet.
5. **Live-ingest UI button + status endpoint** (parts of 3.2) — keep `POST /api/sessions/torcs-live` (architectural promise), cut `GET /api/torcs-status` discovery helper and the upload-page banner. Judges fall back to curl for the live ingest.
6. **Jaeger screenshot** (2.6) — fall back to a code-only mention in README "Observability" section.
7. **Ollama runtime abstraction** (2.10) — defer the `OllamaChatClient` impl entirely to v1.1; ship just the doc + ADR-003 noting the planned migration path. **Consequence:** the `OVERRIDE_LLM_RUNTIME=ollama` env var documented but raises NotImplementedError; the lab container's ollama stays present for the AI driver only.
8. **`analysis/torcs_energy.py` extraction** (1.4) — keep the derivation inline in `ingest/torcs_parser.py` if time-boxed. **Consequence:** `analysis/perturbations.py` (2.2) then imports energy helpers directly from `ingest/torcs_parser.py` — accept the cross-domain coupling, document in module docstring, plan v1.1 cleanup.
9. **`tracks.json` per-track sector splits** — hardcode 1/3 / 2/3 across all TORCS tracks.

**Hard floor** (cannot cut without missing vision):
- TORCS parser running end-to-end (with the calibration regression test from 1.6)
- FR-8 all three perturbations
- `podman compose up` working (OVERRIDE-only mode at minimum)
- `POST /api/sessions/torcs-live` endpoint shipped (the architectural realtime promise — even if the UI affordance is cut, the endpoint is the load-bearing piece)
- Concurrency fix for fan-mode save (1.8)
- Video re-recorded with the what-if beat
- TORCS container init script (`scripts/torcs_container_init.sh`) absorbing the Ollama chown + VS Code hang bugs — without it, `--profile torcs up` is broken; even if `--profile torcs` is "strongly preferred" rather than "floor," shipping it broken when someone tries is worse than not shipping it

**Strongly preferred** (not in hard floor, but defended against cuts):
- `podman compose --profile torcs up` succeeds end-to-end — TORCS reachable at `:6080`, telemetry shared-volume verified writable across containers (UID-remap test green). Cut to "README documents the live path; manual TORCS install path supported" if it fails in the dry-run.
- Ephemeral hosted demo URL (3.7) — see cut #4.
- Live-ingest UI banner (3.2) — see cut #5.

The two tiers exist because v4 over-loaded the hard floor with operationally-risky items. The endpoint is an architectural promise (in floor); the wired-up-and-working compose service is convenience (strongly preferred). Discovering the live-TORCS compose service is broken at T-24h shouldn't violate the floor — it should trigger graceful degradation to "the architecture is right; the live path is documented and the fixture path works."

## Out of scope (defer to v1.1, document not implement)

- TTM-R2 forecasting (graceful-degradation guardrail makes it optional).
- GET /api/sessions list endpoint + real SessionsPage.
- Section B Sporting Regulations grounding (only Section C Technical lands in v1).
- GitHub Actions CI.
- **True streaming TORCS ingest** — SSE pushing per-lap zone detections as `torcs_jm_par.py` writes them. v1 ships `POST /api/sessions/torcs-live` as lap-paced batch ingest only.
- Live TORCS-during-demo capture in the **video** (logger is committed and the compose stack supports the live path; the *video* still uses pre-captured fixtures for determinism).
- Authentication / multi-user (single-user replay-first per `05-security.md`).
