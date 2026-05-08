# Overdrive Rules for Bob

> Loaded into every conversation in this repo. These rules govern how Bob behaves.

## 1. Plans clutter the repo (Session advice)

- All plan files must live in `docs/plans/`. They are referenced via `@docs/plans/...` during a feature's life.
- After the feature ships, delete the plan file in the same PR. Don't leave dead plans around they confuse future Bob conversations.

## 2. ADRs are cumulative

Architecture Decision Records (`docs/adrs/`) capture cumulative state, not deltas. If we change a decision, edit the ADR rather than appending "but actually." Deltas-as-history confuses agents (Session advice).