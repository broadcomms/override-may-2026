# Coder Handoff — Podman Compose Docs Correction — 2026-05-16

## Goal

Update the repo's user-facing startup and deployment documentation so it reflects the operator path that works reliably right now: `podman-compose`, not `podman compose`. The docs should be easy for a non-technical user to follow without hitting a hidden Docker Desktop / WSL integration dependency or broken `--profile` examples.

## Why

The current docs over-promise portability and currently misstate the working startup commands.

Verified locally on 2026-05-16 in this repo environment:

- `podman --version` → `4.9.3`
- `podman compose version` fails and delegates to an external compose provider:
  - it tries to execute `/mnt/c/Program Files/Docker/Docker/resources/bin/docker-compose`
  - it then errors because `docker-compose` is not available in this WSL distro / Docker Desktop WSL integration is not configured
- `podman-compose --version` works: `1.0.6`
- `podman-compose --dry-run up override torcs` resolves correctly for the OVERRIDE + TORCS stack
- `podman-compose --dry-run up override jaeger` resolves correctly for the OVERRIDE + Jaeger stack
- `podman-compose --dry-run up override langflow` resolves correctly for the OVERRIDE + Langflow stack

So the repo should stop telling users that `podman compose up` works "off the bat" or that profile-based startup is the default supported path.

## Scope

- update the Quickstart / startup instructions to make `podman-compose` the primary documented path
- replace `podman compose --profile ... up` examples with the verified `podman-compose` service-selection equivalents
- remove or narrow claims that Docker compose and Podman's built-in compose path are equivalent if we are not verifying them in this task
- update deployment / architecture / reproducibility language so the documented operator contract matches reality
- keep the docs simple enough for a non-technical user to follow

## Non-goals

- do not change `docker-compose.yml` behavior in this task
- do not redesign the container topology
- do not add new runtime dependencies or installation scripts
- do not sweep old historical `docs/plans/` artifacts unless there is a strong reason; prioritize the living docs

## Findings To Encode In The Docs

Use these verified command shapes in the docs unless you discover a better tested path during the task:

- default app only:
  - `podman-compose up`
- app + TORCS:
  - `podman-compose up override torcs`
- app + observability:
  - `podman-compose up override jaeger`
- app + Langflow:
  - `podman-compose up override langflow`
- full stack:
  - `podman-compose up override torcs jaeger langflow`

Important nuance:

- `podman-compose up torcs` starts only `torcs`, not `override + torcs`
- the old `podman compose --profile torcs up` examples should not remain as the primary user guidance
- if you keep any mention of `podman compose`, it must be explicitly demoted as unverified / environment-dependent rather than presented as the recommended path

## Constraints

- preserve accuracy over breadth; do not promise startup paths we did not verify
- prioritize the easiest copy/paste path for a cold-start user
- keep language aligned with repo guardrails in `AGENTS.md`
- if changing docs that describe architecture, keep them consistent with the actual compose topology
- if a doc currently says "Docker compose works equivalently", remove or soften that unless you independently verify it in this task

## Likely Files

- `README.md`
- `docs/07-deployment.md`
- `docs/03-prd.md`
- `docs/02-ai-and-technical-approach.md`
- `docs/03-architecture.md`
- `docs/06-roadmap.md`

Secondary review targets if they still expose the wrong operator contract and are meant to be current:

- `docs/adrs/ADR-001-watsonx-runtime.md`
- `docs/adrs/ADR-002-torcs-as-primary-sandbox.md`
- `docs/adrs/ADR-003-llm-runtime-abstraction.md`
- `docs/adrs/ADR-004-torcs-control-plane.md`

## Acceptance

- the README Quickstart uses `podman-compose` as the primary supported startup path
- no current user-facing doc tells a fresh user to rely on `podman compose --profile ... up` as the default path
- commands for OVERRIDE-only, TORCS, Jaeger, and Langflow are copy/pasteable and internally consistent across the main docs
- any previous "Docker compose works equivalently" claim is either removed or clearly qualified
- deployment and architecture docs no longer imply a no-extra-setup built-in `podman compose` workflow if that is not what we support
- the docs read cleanly for a non-technical operator

## Verify

- `rg -n "podman compose|--profile|Docker compose works equivalently|podman-compose" README.md docs/07-deployment.md docs/03-prd.md docs/02-ai-and-technical-approach.md docs/03-architecture.md docs/06-roadmap.md`
- manually read the updated Quickstart section in `README.md`
- ensure the command set is consistent everywhere:
  - `podman-compose up`
  - `podman-compose up override torcs`
  - `podman-compose up override jaeger`
  - `podman-compose up override langflow`

## Report Back With

- summary of doc changes
- files touched
- exact commands now documented as the supported startup paths
- any remaining docs that still mention the old `podman compose` profile workflow and why they were left unchanged
