# Changelog

## Unreleased

- Add an optional manual auto/local-gguf reviewer choice. Only manual dispatch
  can force the existing pinned CPU lane; automatic selection remains unchanged.
  Reject invalid manual choices before preparation, suppress Codex authority for
  explicit local runs, and retain a secret-free selection receipt alongside the
  unchanged reviewer admission and terminal gates.
- Bound keyless review generation with a finite ASCII GBNF contract after the
  six-candidate attempt still exhausted its output budget. Preserve the exact
  model/runtime pins, one attempt, token budget and independent admission
  validators. Record the grammar identity; live model qualification is pending.

## 2026-08-28

- Quarantine joblib/pickle: forge no longer dumps `model.joblib`; eval refuses the file; Hub deletion is a dispatched PR with exact parent commit.
Honesty README. Distinguishes this kernel twin from github.com/szl-holdings/ouroboros. No kernel math changed.
