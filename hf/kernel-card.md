---
license: apache-2.0
library_name: kernels
tags:
  - kernel
  - szl-holdings
  - governance
  - ouroboros
  - loop-tax
  - provenance
  - doi:10.5281/zenodo.19944926
---

<p><img src="https://raw.githubusercontent.com/szl-holdings/szl-brand/27d12e77fc0f9f1a0e5fae8b34adf2380d51d070/kit/logos/orbit-v2/suite/szl-icon-32.svg" alt="SZL Holdings" width="40" height="40" /></p>


# {{KERNEL_NAME}}

Bounded agent-loop trace and loop-tax accounting as a pure-Python (noarch) kernel,
published from GitHub [{{GITHUB_REPOSITORY}}](https://github.com/{{GITHUB_REPOSITORY}})
by its `hf-kernel-publish` workflow. GitHub is the source of truth; this repository is
written only by that workflow.

> **Scope.** This is not a trained model and holds no weights. It is a stdlib-only
> governance kernel that reconstructs the a11oy agent-loop trace and its loop-tax split
> from a run's provider-attempt windows. `modelMs` and `peakAttemptMs` are MEASURED
> upstream; `overheadMs`, `serializationTaxMs` and `deadHopMs` are DERIVED arithmetic on
> those measurements. `serializationTaxMs` is a counterfactual, never a realized saving.
> Lambda is not touched and stays Conjecture 1 (open).

## Load it

```python
# pip install "kernels>=0.17.2" torch
from kernels import get_kernel

ouroboros = get_kernel("{{REPO_ID}}", version={{KERNEL_VERSION}}, trust_remote_code=True)

attempts = [
    {"provider": "sovereign", "model": "own-metal", "ok": False, "latency_ms": 220, "node": "tower"},
    {"provider": "sovereign", "model": "own-metal", "ok": True, "latency_ms": 900, "node": "laptop"},
]
trace = ouroboros.build_loop_trace(attempts, wall_ms=1300, exit="converged", max_budget=4)
print(trace["modelMs"], trace["overheadMs"], trace["deadHopMs"])  # 1120.0 180.0 220.0
print(ouroboros.explain(trace["labels"]))  # per-field MEASURED/DERIVED provenance
```

- `version={{KERNEL_VERSION}}` resolves the `v{{KERNEL_VERSION}}` branch, the stable API channel. It is
  republished from GitHub by the publish workflow. The `kernels` library refuses a call that
  names neither a version nor a revision.
- `trust_remote_code` is required: SZLHOLDINGS is not a trusted kernel publisher on the Hub.
  The narrowest form is `trust_remote_code=["{{REPO_ID}}"]`.
- CPU hosts load `build/torch-cpu`; CUDA and other hosts load `build/torch-universal`.
  Both variants carry identical code, built from the same GitHub commit. The kernel itself
  uses no tensors.

### Pin an exact build (production)

```python
from huggingface_hub import HfApi
from kernels import get_kernel

refs = HfApi().list_repo_refs("{{REPO_ID}}", repo_type="kernel")
pin = next(b.target_commit for b in refs.branches if b.name == "v{{KERNEL_VERSION}}")
ouroboros = get_kernel("{{REPO_ID}}", revision=pin, trust_remote_code=["{{REPO_ID}}"])
```

Record `pin` (a commit of this kernel repository) in your lockfile, after reviewing that
revision: `trust_remote_code` executes its Python.
`SZL_KERNEL_SOURCE.json` in this repository names the GitHub commit each build came from.
Commits of the model repository
[{{MODEL_TWIN_URL}}]({{MODEL_TWIN_URL}}) are not kernel revisions and do not resolve here.

Doctrine v11. Lambda = Conjecture 1, advisory and never a theorem. Apache-2.0.
Owner: Stephen Lutar / SZL Holdings.

Artwork: SZL Orbit · © 2026 SZL Holdings / Stephen Lutar · [CC BY 4.0](https://github.com/szl-holdings/szl-brand/blob/27d12e77fc0f9f1a0e5fae8b34adf2380d51d070/kit/LICENSE) · [Trademark notice](https://github.com/szl-holdings/szl-brand/blob/27d12e77fc0f9f1a0e5fae8b34adf2380d51d070/NOTICE).
