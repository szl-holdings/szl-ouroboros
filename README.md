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
The reviewed packet has ten fixed source identities: the eight repository
sources and public arXiv/Crossref metadata captures. Git revisions remain
40-character SHA-1 object identifiers. Metadata captures carry the explicit
`metadata-capture-sha256` kind and must bind their provider, identifier, canonical
URL, retained metadata digest, bounded response receipt, title, and exact content
projection. They provide metadata for review only; they do not admit paper text
or infer full-text rights, training authority, or independently verified truth.

If input preparation fails, the loop retains a `SOURCE_PREPARATION_FAILED`
receipt with an unavailable source and no reviewer attempt. It does not require
a reviewer timer that was never started. The final enforcement step remains red;
receipt closure records the failure and never substitutes for a valid review.

The default provider chain is explicit:

1. use the existing pinned Codex action when `OPENAI_API_KEY` or
   `CODEX_API_KEY` is configured;
2. otherwise run the public, exact-revision
   `SZLHOLDINGS/SZL-Khipu-1.5B-GGUF` locally through a verified
   `llama-cpp-python` CPU wheel;
3. fail closed if neither reviewer produces output that passes the independent
   schema, evidence, and authority validator.

Manual workflow_dispatch runs also offer an optional reviewer choice:

| Choice | Behavior |
|---|---|
| auto (default) | Use the existing provider chain above. |
| local-gguf | Disable Codex authority for this run and use only the existing exact pinned CPU Khipu lane. |

The choice is honored only for workflow_dispatch; scheduled, push, and other
events retain automatic selection. Invalid manual values fail before source
preparation or either reviewer. The local choice suppresses the API credential
from the selection step and skips the Codex action even if an API key exists in
the repository. It does not change secrets, select an external model endpoint,
or weaken any model, evidence, output, timing, or authority gate.

A secret-free outputs/reviewer-selection.json artifact records the event,
controller revision, normalized request, selected lane, and effective Codex
authority for that run. The existing loop receipt records Codex configured=false
and attempted=false for explicit local runs, plus the actual local attempt and
its outcome. Here configured describes authority enabled for this run; it does
not claim that the repository has no secret. A selected lane is not evidence
that the model completed. The native reviewer still must produce an admitted
terminal result under the unchanged finalizer and enforcement gate.

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
The keyless lane narrows this to **one compact recommendation over six selected
candidate excerpts**, or an explicit no-action review. Selection prefers distinct
sources by deterministic relevance score, and respects the exact requested
candidate limit even when more sources are available. The execution receipt
records the total source candidate count and explicitly limits the review scope
to selected public excerpts. It does not claim a full-portfolio review.

The prompt describes a compact contract and the independent output validator
enforces it:

| Output field | Maximum |
|---|---:|
| Recommendations | 1 |
| Summary | 120 characters |
| Title | 80 characters |
| Rationale | 240 characters |
| Risk | 120 characters |
| Evidence candidate IDs | 2 |
| Validation steps | 2, each 120 characters |
| Canonical complete review | 1,800 UTF-8 bytes |

The earlier packet limits responded to a 24-candidate truncated run, but the
[six-candidate run on 2026-10-05](https://github.com/szl-holdings/szl-ouroboros/actions/runs/37257722108)
also ended with `OUTPUT_TRUNCATED`. A generic JSON-object grammar allowed
unbounded strings and collections despite the prompt's limits.

The local GGUF lane now uses a small, finite GBNF grammar for the exact digest
and selected candidate IDs. It generates one compact ASCII JSON object with
bounded strings, one recommendation, and at most two evidence IDs and validation
steps. Text fields use printable ASCII without quotes or backslashes; model
output remains subject to the unchanged independent validators, including
evidence uniqueness and advisory-text checks. The full JSON Schema is not
automatically compiled into a native grammar. Receipts retain the generation
grammar version and SHA-256.

The workflow keeps its 1,800-token allowance, exact model/runtime pins,
temperature, seed and one-attempt bound. Grammar acceptance and byte limits do
not establish useful model output or a successful live attempt. Any non-stop
completion still fails closed as `OUTPUT_TRUNCATED` or
`COMPLETION_NOT_STOPPED`; an otherwise valid general-schema review that exceeds
the compact contract fails as `OUTPUT_BUDGET_CONTRACT`. No partial output is
repaired or admitted. A new exact-source live replay must retain an admitted
terminal review and loop receipt before this lane is called operational.

Neither provider
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

Set `SZL_OUROBOROS_HF_REVISION` to the immutable **first-class Kernel Hub** commit
from a verified publication of [`kernels/SZLHOLDINGS/szl-ouroboros`](https://huggingface.co/kernels/SZLHOLDINGS/szl-ouroboros). Use the `kernels`
client version qualified with that publication. The GitHub source commit,
model-type mirror commit, and Kernel Hub commit are separate identities.
An observed head, a branch name, or a successful import does not qualify a release.

`trust_remote_code=True` permits execution of the selected repository's Python.
Review that exact revision, its provenance and publication evidence before enabling it.
The format check below only rejects missing or mutable revision inputs; it does not
verify hashes, publisher authorization or compatibility. If that evidence is unavailable,
stop the Hub load and use separately reviewed local source for development.

```python
import os
import re

hf_revision = os.environ.get("SZL_OUROBOROS_HF_REVISION", "")
if re.fullmatch(r"[0-9a-f]{40}", hf_revision) is None:
    raise ValueError("A verified immutable Kernel Hub revision is required")

from kernels import get_kernel

ouroboros = get_kernel(
    "SZLHOLDINGS/szl-ouroboros",
    revision=hf_revision,
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

## Source-only development

Review [`torch-ext/szl_ouroboros/`](https://github.com/szl-holdings/szl-ouroboros/tree/f4c9df3840a84c767b7e5fa1c29aa25f00cc0457/torch-ext/szl_ouroboros)
at that immutable GitHub source revision, separately from any Hub release.
With the source's dependencies already available, run from the reviewed checkout root:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("torch-ext").resolve()))
import szl_ouroboros as local_kernel
```

This selects local Python source rather than calling the Hub loader. Importing local
source also executes Python. This documentation check does not run that import,
install dependencies, qualify a runtime or establish a Hub publication.
