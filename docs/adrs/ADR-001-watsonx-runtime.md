# ADR-001 — watsonx.ai for Granite serving

- **Status**: Accepted
- **Date**: 2026-05-08

## Context

Roadmap P1.1 originally pulled Granite 4.x Instruct and Granite Guardian via local Ollama (verified gate **G-1**, recorded in `models.json` with manifest digests + SHA256). After the pulls completed (~12 GB total), inference latency on the local laptop CPU was prohibitive — a single 8 B-parameter forward pass took on the order of a minute, well outside the 30 s end-to-end pipeline budget defined in `04-api.md` §5.

We have access to **IBM watsonx.ai** (US-South region) with credentials in `.env` and a project ID:

```
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_PROJECT_ID=<configured in .env>
GRANITE_INSTRUCT=ibm/granite-4-h-small
GRANITE_GUARDIAN=ibm/granite-guardian-3-8b
```

Smoke-tested both models on 2026-05-08 (`scripts/test_watsonx.py`).

## Decision

Migrate Granite Instruct and Granite Guardian to **watsonx.ai cloud serving**. TTM-R2 and Docling continue to run locally.

## Consequences

### Positive

- Inference is fast enough to meet the 30 s end-to-end pipeline budget; reasoning per zone returns in low seconds.
- No 12 GB local model download in the Quickstart — judges can `podman-compose up` and immediately use the system once their `.env` has watsonx credentials.
- Granite versions are managed by IBM and pinned by model ID in `models.json` and `.env`.
- Aligns with the IBM SkillsBuild challenge's emphasis on IBM technologies — watsonx.ai is the canonical IBM serving stack.

### Negative

- Submission requires a working watsonx.ai project to demo. Mitigation: provide a recorded video walkthrough; include canned sample outputs in the repo for offline review.
- Network dependency in the production runtime (was a local-only stack). The pipeline cannot run fully offline.
- API call cost / rate limits apply (watsonx tier-dependent).
- Auth surface (`WATSONX_API_KEY`) becomes a deployment concern. Already gitignored in `.env`.

### Implications for the pipeline

- `core/reasoning.py` calls watsonx.ai chat API (`/ml/v1/text/chat`) with model `ibm/granite-4-h-small`. The legacy `/ml/v1/text/generation` API is deprecated; use chat.
- `core/guardian.py` calls watsonx.ai with `ibm/granite-guardian-3-8b` using the Guardian-specific scoring contract (not free-form generation).
- `core/fan_mode.py` reuses the Instruct model with a higher temperature.
- `core/forecasting.py` continues to load TTM-R2 from HuggingFace and runs locally.
- `core/regs.py` runs Docling locally.

### Embeddings for retrieval (decided 2026-05-08)

Regulation chunk retrieval uses **`ibm/granite-embedding-278m-multilingual`** on watsonx.ai. Output dimension: **768** (verified via `scripts/test_watsonx_embedding.py`).

Why this and not `ibm/slate-30m-english-rtrvr` (the original candidate above): slate-30m is deprecated in the watsonx catalog. Granite-embedding-278m is the current generation, multilingual (handles English regulation text and any future non-English material), and keeps the entire AI surface on the watsonx Granite stack.

`sentence-transformers` was rejected — would add a ~500 MB local download and create a second embedding source of truth. Only revisit if watsonx rate limits or offline determinism become a concern.

`RegulationChunk.embedding` in `04-schema.md` §6 is `Optional[list[float]]` of length 768 when populated.

### Model deprecation watch

- `ibm/granite-guardian-3-8b` is in deprecated state on watsonx (2026-05-05 → 2026-08-08 withdrawn). The submission window (May 31) is well inside the deprecation window — we're safe for submission. Post-submission, migrate to whichever Guardian replacement IBM publishes.
- Track via `https://dataplatform.cloud.ibm.com/docs/content/wsj/analyze-data/fm-model-lifecycle.html`.

## What this supersedes

- The Ollama path in roadmap P1.1, gate **G-1**, and the corresponding `ollama pull` instructions in `README.md` and `docs/plans/phase-1-foundation-implementation.md`.
- `scripts/record_ollama_digests.sh` was deleted (obsolete with this migration).
- The `ollama.*` block in `models.json` is replaced by `watsonx.*`.

## Related files

- `models.json` — pinning watsonx model IDs.
- `.env.example` — documents the required watsonx variables.
- `scripts/test_watsonx.py` — smoke test that closes G-1.
- `scripts/find_watsonx_region.py` — diagnostic when project lookup fails.
