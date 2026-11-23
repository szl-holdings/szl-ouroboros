# Domain Leader Study — szl-ouroboros (Muyu bounded-loop frontier-review kernel)

OUROBOROS phase-3, cohort-02 tranche-3, Kimi ruling W26-C2T3-EXEC-20261123 (GO, 7 conditions). PROPOSE-ONLY, DRAFT. Documentation only, no implementation in this PR.

## Current state (repo inspection 2026-11-23, W26G receipts)
Muyu bounded-loop frontier-review kernel; keyless GGUF lane with exact model/wheel pins plus GBNF compact grammar; receipts invariant. Sibling estate lanes actively develop this repo (multiple CI/release branches observed and untouched).

## Domain leaders studied
| Leader | What they have | Key sources |
| --- | --- | --- |
| Outlines (efficient guided generation) | Compiled regular-expression and context-free constraints turned into token-level generation masks, guaranteeing syntactically valid structured output from LLMs | arXiv:2307.09702 (https://arxiv.org/abs/2307.09702) |

## Absorption notes (proposal only)
The repo already pins a GBNF compact grammar for the keyless GGUF lane; Outlines is the reference pattern for constrained decoding from declarative grammars (regex-to-mask compilation, CFG guides). Candidate future absorb: a measured comparison of GBNF grammar coverage versus Outlines-style regex/CFG guides for the same receipts invariants. No code change proposed in this PR.

## Provenance
Pre-write probes 2026-11-23: no docs/LEADERS-STUDY.md on main; branch name docs/leaders-study-c2t3 absent before creation; one open dependabot PR (#66) untouched; source web-verified live 2026-11-23 (W26G citation receipts).

PROPOSE-ONLY: merge requires a separate explicit owner go. Ruling nonce: W26-C2T3-EXEC-20261123.
