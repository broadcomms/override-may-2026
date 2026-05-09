# Demo Assets and Notes

Verified. P2.6 Pass-2 Guardian is shipped and architecturally sound. The "demo run caught its own mistake" moment is the single most important thing in this round — that's not just a passing test, that's a captured demo asset. **Strong endorse P2.7 next.** A few specifics to make the orchestrator clean.

## Verified ✅

| Element | State |
|---|---|
| `core/guardian.py` | 550 lines — protocol + real impl + parser + 2 criterion-renderers + parallel orchestrator |
| `GuardianResult` | line 85 — defined in `core/guardian.py` per the schema-ownership rule (correct) |
| Bug fix 1 (Yes/No primary) | line 195: *"`Yes` → risk → score 0.0 → fails. `No` → safe → score 1.0 → passes."* + graded JSON kept as forward-compat fallback |
| Bug fix 2 (single chunk, not corpus) | regulation_consistency now passes only the `cited_chunk` per YAML phrasing |
| Bug fix 3 (`_chunk_for_prompt` strips embedding) | line 269 — strips 768-dim float array (~19KB JSON per chunk) |
| Parallelism | line 506 — `ThreadPoolExecutor(max_workers=2)` over the two criteria; observed 0.47s parallel vs ~1s sequential = real win |
| Tests | **161 test functions** across 6 files (with parametrization → 178 unit + 3 network = 181) |
| Empty stubs left in core/ | `fan_mode.py` (P3.4) and `forecasting.py` (P2.2 optional). That's it. |
| `core/__init__.py` | clean exports of all four implemented modules |

The three bugs are exactly the kind of integration-time discoveries that would have been miserable at P2.7. **8K context window vs 19K tokens** is the kind of thing that quietly fails in production months later — catching it now during single-zone testing is a clean win.

## The "system catches its own mistake" moment is demo gold

This deserves its own callout:

> *Reasoning fabricated a citation that doesn't appear verbatim in the retrieved chunk. Pass-1 deterministic validator flagged `citation_existence`. Pass-2 Guardian said both criteria "No risk" (topical alignment passed). The architecture's layered-defense fired exactly as designed.*

This is the **2:10–2:42 Explainability segment** in `00-abstract.md` writing itself. The demo video script can now be specific:

- *"Watch what happens when Granite hallucinates a citation. Pass 1 — deterministic validator — catches it: the cited passage doesn't appear verbatim in the retrieved chunk. Pass 2 — Granite Guardian — says both criteria 'No risk' because topical alignment is fine. The system catches its own mistake. The engineer sees the failure mode, not a black-box rejection. Two complementary safety layers. Defense in depth."*

That's a 30-second segment that *concretely demonstrates* the explainability story the rubric rewards. **Capture this exact run as a fixture and a screenshot before P2.7 makes the run reproducible-but-different**. Save it to:
- `tests/fixtures/layered_defense_demo.json` — the captured session output for use in `tests/test_pipeline.py`
- `assets/screenshots/guardian-rejection.png` — already on the asset list (per `04-ui-ux-design.md §11`)

This is the single most defensible artifact in the submission. Don't lose it to a stochastic regen.

