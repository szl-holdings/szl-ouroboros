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

## Continuous frontier review

`Ouroboros continuous frontier review` runs every two hours. It binds one
read-only model review to the exact current Second Brain frontier candidate set.
The provider chain is explicit:

1. use the existing pinned Codex action when `OPENAI_API_KEY` or
   `CODEX_API_KEY` is configured;
2. otherwise run the public, exact-revision
   `SZLHOLDINGS/SZL-Khipu-1.5B-GGUF` locally through a verified
   `llama-cpp-python` CPU wheel;
3. fail closed if neither reviewer produces output that passes the independent
   schema, evidence, and authority validator.

The loop is:

```text
Second Brain protected main
        ↓ exact revision + candidate SHA-256
schema and authority replay
        ↓
Codex OR exact public Khipu GGUF
        ↓ untrusted evidence-linked structured JSON
independent deterministic validation
        ↓
Ouroboros timing + termination + receipt closure
        ↓
90-day secret-free artifact
```

The keyless lane pins all model and runtime identity:

- model repository: `SZLHOLDINGS/SZL-Khipu-1.5B-GGUF`;
- model revision: `67d60ec577730747055491640cfb91fc4a4b5d25`;
- model file: `SZL-Khipu-1.5B-Q4_K_M.gguf`;
- model bytes: `986047904`;
- model SHA-256:
  `13c1a1993063e1dff92f7413ccf48eaca6d48efc8801ae9af35961ae3396623a`;
- runtime wheel: `llama-cpp-python 0.3.35` official manylinux CPU wheel;
- wheel SHA-256:
  `d172f3d3c8cdd194c3c47c71cb077ed6e61354a2d0f939ceeac0c8fd29999596`;
- temperature `0`, seed `749`, one reviewer attempt, bounded context and output.

No Hugging Face token is required to retrieve the public model. A local
OpenAI-compatible endpoint can also be selected through `OPEN_MODEL_BASE_URL`;
this supports self-hosted Ollama, vLLM, or a llama.cpp-compatible server without
changing the receipt contract. `OPEN_MODEL_API_KEY` is optional and is never
recorded.

The Codex lane remains pinned to `openai/codex-action`, Codex CLI `0.138.0`,
`permission-profile: :read-only`, `safety-strategy: drop-sudo`, and the same
output schema. The open-weight lane does not weaken or replace the deterministic
validator. Model-generated JSON is always treated as untrusted.

A reviewer can propose at most twelve evidence-linked recommendations across the
approved Brain, Anatomy, A11oy, Formula, Forge, Nemo, and Ouroboros repositories.
The keyless prompt narrows this to at most five recommendations from a
deterministically selected, source-diverse candidate projection. Neither provider
can edit files, use repository credentials, train weights, promote candidates,
execute tools, merge pull requests, mutate providers, reveal secrets, or load the
private Second Brain graph. The output is an advisory artifact, not accepted
truth.

The finalizer measures the reviewer attempt window and total wall time through
the active `szl_ouroboros.build_loop_trace` kernel. Each receipt must prove:

- `steps <= maxBudget`;
- a terminal loop exit;
- `receiptsInEqOut = true` as a doctrine invariant;
- exact Second Brain source and candidate-set digests;
- valid candidate evidence IDs;
- zero training, promotion, execution, merge, and provider-mutation authority;
- exact model/runtime identity for the keyless lane;
- independent validation before any terminal review state is accepted.

## What this is NOT

- Hub `model.joblib` is **QUARANTINED** executable serialization. Do not `joblib.load` it. GitHub source is the approved path.
- Not the `ouroboros` TypeScript product runtime.
- Not trained weights.
- Not an autonomous merge or deployment agent.
- No measured CUDA benches are claimed here.
- Lambda is not upgraded by loop execution or model output.
- No shared, leaked, scraped, or fabricated API key is used.

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
        "provider": "llama-cpp-python",
        "model": "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF",
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
