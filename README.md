# szl-ouroboros

Canonical GitHub source for **SZLHOLDINGS/szl-ouroboros**.

**GitHub is the source of truth.** The Hugging Face Hub kernel package is a **publish mirror** of this tree. Do not treat the Hub copy as canonical.

ATELIER owns Hub cards. This README is a source face for the Git repository. It is **not** a second model card.

## What this is

A **software kernel**: executable loop-trace reconstruction and loop-tax accounting over provider-attempt windows. Pure Python, stdlib-only. **Not** trained weights. **Not** CUDA benches.

- MEASURED: `modelMs` (sum of attempt windows), `peakAttemptMs`.
- DERIVED: `overheadMs`, `serializationTaxMs` (counterfactual, never a realized saving), `deadHopMs` (no prefetch).
- Doctrine: bounded, terminating, receipt-closed. `receiptsInEqOut` is a doctrine invariant, not a proof.
- **Λ = Conjecture 1**, never a theorem. Loop-tax arithmetic does not touch Λ.
- Doctrine v11.
- License: Apache-2.0.

## Load (via the Hub publish mirror)

```python
from kernels import get_kernel
ou = get_kernel("SZLHOLDINGS/szl-ouroboros", revision="main", trust_remote_code=True)
```

Hub package: https://huggingface.co/SZLHOLDINGS/szl-ouroboros

## Layout

- `build.toml` — kernel-builder manifest (`universal = true`)
- `build/torch-universal/szl_ouroboros/` — kernel module
- `tests/test_ouroboros.py` — honest MEASURED/DERIVED arithmetic tests
- `LICENSE` — Apache-2.0
