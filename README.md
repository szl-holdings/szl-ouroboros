# szl-ouroboros
<!-- szl:header v1 -->
[![base-python-ci](https://github.com/szl-holdings/szl-ouroboros/actions/workflows/base-python-ci.yml/badge.svg)](https://github.com/szl-holdings/szl-ouroboros/actions/workflows/base-python-ci.yml)
[![continuous frontier](https://github.com/szl-holdings/szl-ouroboros/actions/workflows/codex-continuous-frontier.yml/badge.svg)](https://github.com/szl-holdings/szl-ouroboros/actions/workflows/codex-continuous-frontier.yml)
[![org: szl-holdings](https://img.shields.io/badge/org-szl--holdings-black)](https://github.com/szl-holdings)
[![doctrine](https://img.shields.io/badge/doctrine-control%20before%20action%20%C2%B7%20evidence%20after-blue)](https://a-11-oy.com)

**Control before action. Evidence after.**

Part of the [szl-holdings](https://github.com/szl-holdings) estate ·
Product: [a-11-oy.com](https://a-11-oy.com) ·
Proof: [a11oy.net](https://a11oy.net)
<!-- /szl:header -->

Kernel-twin repo for the Ouroboros bounded-loop package. **Not the TypeScript
product** [`szl-holdings/ouroboros`](https://github.com/szl-holdings/ouroboros).
**Not a model. No weights.**

Hub mirror: [`kernels/SZLHOLDINGS/szl-ouroboros`](https://huggingface.co/kernels/SZLHOLDINGS/szl-ouroboros).
Card: [`SZLHOLDINGS/szl-ouroboros`](https://huggingface.co/SZLHOLDINGS/szl-ouroboros).

## Continuous Codex frontier loop

`Ouroboros Codex continuous frontier review` runs every two hours. It binds a
read-only Codex review to the exact current Second Brain frontier candidate set.
The loop is:

```text
Second Brain protected main
        ↓ exact revision + candidate SHA-256
schema and authority replay
        ↓
Codex read-only advisory review
        ↓ evidence-linked structured JSON
Ouroboros timing + termination + receipt closure
        ↓
90-day secret-free artifact
```

The workflow uses the official `openai/codex-action` pinned to an exact commit,
Codex CLI `0.138.0`, `permission-profile: :read-only`, `safety-strategy:
drop-sudo`, an exact output schema, and at most one model attempt per run.

A configured `OPENAI_API_KEY` or `CODEX_API_KEY` enables the model review. If no
key exists, the loop still completes honestly with
`CODEX_UNAVAILABLE_MISSING_SECRET`; it does not fabricate an analysis or turn the
repository red for an absent optional provider.

Codex can propose at most twelve evidence-linked recommendations across the
approved Brain, Anatomy, A11oy, Formula, Forge, Nemo, and Ouroboros repositories.
It cannot edit files, use the network directly, train weights, promote candidates,
execute tools, merge pull requests, mutate providers, reveal secrets, or load the
private Second Brain graph. The output is an advisory artifact, not accepted truth.

The finalizer measures the Codex attempt window and total wall time through the
active `szl_ouroboros.build_loop_trace` kernel. Each receipt must prove:

- `steps <= maxBudget`;
- a terminal loop exit;
- `receiptsInEqOut = true` as a doctrine invariant;
- exact Second Brain source and candidate-set digests;
- valid candidate evidence IDs;
- zero training, promotion, execution, merge, and provider-mutation authority.

## What this is NOT

- Hub `model.joblib` is **QUARANTINED** executable serialization. Do not `joblib.load` it. GitHub source is the approved path.
- Not the `ouroboros` TypeScript product runtime.
- Not trained weights.
- Not an autonomous merge or deployment agent.
- No measured CUDA benches are claimed here.
- Lambda is not upgraded by loop execution or Codex output.

## Load

```python
from kernels import get_kernel

ouroboros = get_kernel(
    "SZLHOLDINGS/szl-ouroboros",
    revision="main",
    trust_remote_code=True,
)
trace = ouroboros.build_loop_trace(
    [{
        "provider": "openai",
        "model": "codex-cli-default",
        "ok": True,
        "latency_ms": 1200,
        "node": "scheduled-frontier-review",
    }],
    wall_ms=1450,
    exit="converged",
    max_budget=1,
)
assert trace["withinBudget"] is True
assert trace["receiptsInEqOut"] is True
```

Doctrine v11. Lambda = Conjecture 1, advisory and never a theorem. Apache-2.0.
Owner: Stephen Lutar / SZL Holdings.
