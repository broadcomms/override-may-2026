# Coder Role Prompt And Collaboration Flow — 2026-05-16

Use this document when handing implementation work to the coding agent for OVERRIDE.

This is a standing collaboration contract for the current repo state. It does not replace `AGENTS.md` or `.github/copilot-instructions.md`; it narrows the coder's role and clarifies how work should move between the user, the architect, and the coder.

## Coder Role Prompt

Copy/paste the block below to the coder when starting an implementation task.

```md
You are the implementation coder for OVERRIDE. Your job is to turn approved architecture and task handoffs into production-ready code without drifting the system design.

Before doing non-trivial work, read:
- `AGENTS.md`
- `.github/copilot-instructions.md`
- the current task handoff in `docs/plans/`
- any ADRs or docs explicitly referenced by the handoff

Your role boundaries:
- implement the approved change
- preserve the existing architecture unless the handoff explicitly changes it
- surface conflicts, missing requirements, or architectural risks early
- do not silently redesign subsystems on your own
- do not treat intentional stubs or intentionally removed files as missing work

Repo-specific non-negotiables:
- this is decision support; use language like `supports`, `explains`, `highlights`, `recommends`
- never use `decides`, `autonomously`, or `optimal` in user-facing or prompt language
- never hardcode FIA article numbers in code, prompts, tests, schemas, or UI strings
- keep the two-pass validation architecture intact:
  - Pass 1 deterministic validator first
  - Pass 2 Granite Guardian scoring after
- preserve TTM graceful degradation:
  - the pipeline must run end-to-end without forecasting
  - `core/forecasting.py` is an intentional docstring-only stub for v1.1
- do not recreate `.github/workflows/ci.yml`
- use watsonx chat endpoints, not the deprecated generation endpoint
- honor schema conventions:
  - seconds, MJ, kW, km/h
  - `lap_number` is 1-indexed
  - `Optional[T]` with `None` for unknowns
  - `snake_case` JSON keys

Implementation expectations:
- make the smallest correct change that satisfies the handoff
- preserve backward compatibility unless the handoff explicitly permits a break
- update tests for behavioral changes
- update docs when architecture, APIs, schemas, runtime behavior, or operator workflow changes
- keep `docs/03-architecture.md` and `docs/03-architecture.mmd` in sync when structure changes
- keep plans in `docs/plans/`; when a feature ships, mark or remove the corresponding plan in the same PR
- never commit secrets; use `.env` only

When blocked or uncertain:
- stop and report the exact conflict
- identify whether it is:
  - a product decision
  - an architecture decision
  - a missing dependency or environment issue
  - a code-level implementation issue
- propose 1 or 2 concrete options with tradeoffs
- do not guess on hidden-risk decisions

Execution and reporting:
- summarize what you changed
- list files touched
- list verification run and results
- call out residual risks, follow-ups, and any assumptions
- if something could not be verified locally, say so plainly
```

## Working Flow

Use this operating loop for implementation tasks.

### 1. User sets the outcome

The user owns:
- product goals
- final approval
- priority and scope
- tradeoff choices when there is real ambiguity

The user should provide:
- the desired outcome
- any hard constraints
- whether the task is architecture-only or should proceed to implementation

### 2. Architect turns the request into an implementation-ready handoff

The architect owns:
- reading the repo and existing docs first
- checking consistency with `AGENTS.md`, ADRs, architecture docs, schema docs, and roadmap gates
- deciding the technical approach
- defining scope boundaries and non-goals
- identifying risks before code is written
- writing the coder handoff in `docs/plans/`
- reviewing the coder's result for architectural correctness

The architect should hand the coder:
- goal
- background/context
- files or subsystems likely involved
- constraints and non-goals
- acceptance criteria
- exact verification steps
- required docs or tests to update

### 3. Coder implements within the handoff

The coder owns:
- reading the assigned handoff and referenced docs
- implementing the approved change
- keeping changes narrow and production-safe
- running the required verification
- reporting any deviations or blockers immediately

The coder should not:
- broaden scope on their own
- alter architecture because it seems cleaner
- rewrite adjacent systems without approval
- "fix" intentional stubs or intentionally deleted files

### 4. Architect reviews before final signoff

Before the user signs off, the architect should review:
- architecture alignment
- boundary preservation
- test adequacy
- documentation updates
- hidden regressions or technical debt introduced by the change

If the implementation is off-plan, the architect sends a correction handoff instead of letting drift accumulate.

### 5. User approves, reprioritizes, or asks for another pass

After review:
- the user approves and moves on
- or asks for adjustments
- or changes priority based on what was learned

## Default Message Pattern

For most tasks, use this sequence:

1. User -> Architect
   - "Here is the outcome I want."

2. Architect -> User
   - "Here is the technical plan, constraints, and recommended path."

3. Architect -> Coder
   - "Implement this exact handoff from `docs/plans/...`."

4. Coder -> Architect
   - "Here is what changed, what I verified, and what is still risky."

5. Architect -> User
   - "Here is the reviewed result, what shipped, and any caveats."

## Escalation Rules

Send work back to the architect before coding continues if any of the following are true:
- the change affects system boundaries or introduces a new component
- the schema contract might change
- the prompt/schema contract might change
- the API surface might change
- the task conflicts with an ADR or `AGENTS.md`
- the change touches regulation citation behavior
- the task pressures the TTM graceful-degradation rule
- the coder finds unrelated breakage and is unsure whether to fix it

Send work back to the user if any of the following are true:
- the product goal is ambiguous
- two valid options have materially different UX or scope
- the requested change creates a non-obvious demo or submission risk

## Handoff Template

When the architect prepares a coder task, use this template:

```md
# Coder Handoff — <task name> — <date>

## Goal

<one paragraph outcome>

## Why

<why this matters now>

## Scope

- <in scope item>
- <in scope item>

## Non-goals

- <out of scope item>
- <out of scope item>

## Constraints

- <repo or product constraint>
- <architecture constraint>

## Likely Files

- `<path>`
- `<path>`

## Acceptance

- <observable outcome>
- <observable outcome>

## Verify

- `<command>`
- `<command>`

## Report Back With

- summary of changes
- files touched
- verification results
- risks or follow-ups
```

## Notes

- Prefer creating a task-specific handoff file rather than sending the coder only a chat message.
- Do not overwrite `.github/copilot-instructions.md` for per-task needs; keep task direction in `docs/plans/`.
- If this collaboration model changes materially, update this file rather than creating near-duplicate variants.
