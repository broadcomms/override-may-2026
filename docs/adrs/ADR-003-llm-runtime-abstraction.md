# ADR-003 — Hybrid LLM runtime (watsonx primary, ollama optional via env switch)

- **Status**: Accepted
- **Date**: 2026-05-11

## Context

ADR-001 migrated Granite Instruct, Guardian, and Embedding from local Ollama
to **IBM watsonx.ai (US-South)** for latency reasons — local 8B inference on
laptop CPU was ~60 s per forward pass vs ~3 s for the watsonx-hosted variant,
well outside the `docs/04-api.md` §5 30-second pipeline budget.

That decision was right for v1.0. It did, however, leave behind one thread the
IBM SkillsBuild lab container ships with: **the lab image bundles
`granite4:350m` via Ollama at port 11434** (verified via
`podman exec torcs ollama list` on 2026-05-11). Students populate
`/opt/ollama/models/` via `ollama pull granite4:350m` on first start (per
`hands-on-labs/01_torcs_lab/RESULTS.md`); the image ships with the directory
present but empty, and the lab's `Continue.dev` extension is pre-configured
to use this Ollama for the lab's coding assistant story.

Two questions land at v6 plan task 2.10:

1. **Should we keep granite4:350m available inside the TORCS container?** Yes —
   the lab depends on it. Removing it would break the "extending the IBM TORCS
   Learning Lab" framing in the README and in `docs/00-abstract-b-torcs-study.md`.
2. **Should OVERRIDE's chat path optionally route through that Ollama?** Yes —
   it gives us a clean v1.1 migration path back to local inference once
   small-model quality catches up (Granite 4 series is improving fast at the
   350M tier), and it's a meaningful "we run on local hardware" rubric beat for
   judges who want to clone-and-run without watsonx credentials. **Not the
   default for v1.0** — the demo video uses watsonx.

## Decision

Ship a **hybrid LLM runtime, switched at app boot via the `OVERRIDE_LLM_RUNTIME`
environment variable**:

| Value | Behavior |
|---|---|
| `watsonx` (default) | `core.reasoning.WatsonxAIChatClient` against `https://us-south.ml.cloud.ibm.com/ml/v1/text/chat`. ADR-001 path, unchanged. |
| `ollama` | `core.llm_clients.OllamaChatClient` against `OVERRIDE_OLLAMA_BASE_URL` (default `http://torcs:11434`). Fails LOUD at boot if unreachable. |

The factory in `api/main.py:get_chat_client` routes per env var. **Guardian
(`core/guardian.py`) and Embedding (`core/regs.py`) stay watsonx-only
regardless of `OVERRIDE_LLM_RUNTIME`** — granite4:350m doesn't expose the
BYOC scoring API or a substitute for the 278M multilingual embedding model.
`WATSONX_API_KEY` is required even in ollama mode.

The `OllamaChatClient` implements the existing `core.reasoning.WatsonxChatClient`
Protocol verbatim: `chat(system: str, user: str, *, temperature, max_tokens) -> str`.
Zero call-site changes in `core/reasoning.py` or `core/fan_mode.py`. The
**response-shape adapter** is the load-bearing piece — Ollama returns
`{"message": {"content": "..."}}` and watsonx returns
`{"choices": [{"message": {"content": "..."}}]}`; both impls unwrap to the
plain string the Protocol promises.

## Fail-loud startup probe

`OVERRIDE_LLM_RUNTIME=ollama` triggers `probe_ollama_reachable()` at the first
`get_chat_client()` invocation (typically uvicorn startup via the FastAPI
dependency injection). The probe issues `GET {base_url}/api/tags` with a 2-second
timeout and refuses to boot the app on failure:

> *"OVERRIDE_LLM_RUNTIME=ollama but Ollama at 'http://torcs:11434' is not
> reachable: ConnectError: ... . Either bring up the TORCS lab container
> (`podman-compose up override torcs` or `./scripts/run_torcs_lab.sh`), or
> point OVERRIDE_OLLAMA_BASE_URL at a reachable ollama instance, or set
> OVERRIDE_LLM_RUNTIME=watsonx (default)."*

The alternative — letting Ollama-mode boot then fail at the first reasoning
call with a 60-second connection-refused — is hostile to debugging. Catch
misconfiguration at the front door.

## What the manual end-to-end gate verifies (v6 plan task 2.10)

After unit tests pass, the manual gate runs against a real `ollama serve`:

1. `podman-compose up override torcs` (or `./scripts/run_torcs_lab.sh`)
2. `OVERRIDE_LLM_RUNTIME=ollama OVERRIDE_OLLAMA_BASE_URL=http://localhost:11434 \
    .venv/bin/uvicorn api.main:app --port 8000`
3. POST `data/samples/torcs_baseline.jsonl` to `/api/sessions` with `source=torcs`
4. Verify the resulting `Recommendation.reasoning` parses cleanly into the
   `ReasoningOutput` Pydantic shape (cause / consequence / recommendation /
   confidence / chain present and non-empty).

If `Recommendation.reasoning` is structurally valid most of the time, the
abstraction ships. **This is the only test of the real Ollama API shape;
the unit tests in `tests/test_llm_clients_ollama.py` are mock-only.**

## Known limitations (v1.1 follow-ups)

1. **Structured-JSON reliability at 350M — confirmed empirically.** v6 plan
   task 2.10 manual gate, 2026-05-11: POSTed `data/samples/torcs_baseline.jsonl`
   through the pipeline with `OVERRIDE_LLM_RUNTIME=ollama`. The probe + simple
   chat both succeeded (clean "The answer is 4." for "What is 2+2?"). The
   reasoning call, however, returned **completely off-topic content** — the
   model interpreted the prompt as a Python code analysis task and returned
   *"The provided code is a Python function named `generate_random_numbers`
   that generates a list of random floating-point numbers..."* — not just
   malformed JSON, full topic hallucination. `ReasoningParseError` after
   ~140 s of generation. This is a fundamental capacity gap (350M params
   can't sustain the multi-constraint reasoning prompt OVERRIDE uses),
   not a prompt-tuning or timeout-bump issue.

   v1.1 candidates:
     - Migrate to `granite-4-h-small` (8B) via Ollama once that tag ships.
       This is the path of least resistance — watsonx-hosted-8B is the model
       the rest of the system is calibrated against, so prompt/parsing all
       continue to work.
     - Function-calling format with structured-output mode (if Ollama exposes
       `format: "json"` strictly enough). granite4:350m supports the
       parameter but enforcement is weaker than watsonx's.
     - Outlines / Instructor constrained-decoding wrapper to grammar-force
       the `ReasoningOutput` schema.
     - Hybrid retry: detect off-topic / non-JSON output, fall through to
       a single watsonx call as backup. Defeats the "fully local" framing
       but preserves demo determinism.

   v1.0 demo intentionally avoids this path — `OVERRIDE_LLM_RUNTIME=watsonx`
   (default) uses 8B granite-4-h-small via cloud and produces structurally
   valid `ReasoningOutput` JSON every time.
2. **No Guardian path.** Even with ollama mode active, Pass-2 BYOC scoring
   still requires `WATSONX_API_KEY`. Full ollama-only mode would need a
   Guardian-equivalent BYOC scorer implementation that the existing Granite
   models on Ollama don't expose. v1.1 candidate: build a Granite-Instruct-
   prompted Guardian-shim for ollama-only mode, accepting lower scoring
   reliability.
3. **No embedding path.** Same constraint — `OVERRIDE_OLLAMA_MODEL` defaults
   to a chat model, not an embedding model. Regulation retrieval stays
   watsonx-only. v1.1 candidate: ollama serves multiple model tags; pull
   `granite-embedding:278m-multilingual` (when that tag exists) and route
   embeddings to it.

## Demo invariant

The submission video at `https://override-video.patrickndille.com` uses `OVERRIDE_LLM_RUNTIME=watsonx` (default). The ollama
path is for:
1. Judges cloning the repo who want to demonstrate the system runs without
   any cloud credentials (sets `OVERRIDE_LLM_RUNTIME=ollama` after bringing
   up the lab container).
2. The v1.1 migration story when small-model quality catches up.

## References

- `core/reasoning.py:WatsonxChatClient` — the Protocol both impls satisfy.
- `core/llm_clients/ollama.py` — `OllamaChatClient` + `probe_ollama_reachable`.
- `api/main.py:get_chat_client` — factory + fail-loud probe wiring.
- `tests/test_llm_clients_ollama.py` — 19 mocked-transport unit tests, response-
  shape adapter first.
- `docs/adrs/ADR-001-watsonx-runtime.md` — original migration to watsonx.
- `hands-on-labs/01_torcs_lab/RESULTS.md` — lab's `ollama pull granite4:350m`
  instruction; granite4:350m tag confirmed canonical via
  `podman exec torcs ollama list` on 2026-05-11.
