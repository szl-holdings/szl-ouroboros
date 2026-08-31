# szl-ouroboros
<!-- szl:header v1 -->
<!-- badges: add this repo's CI / release / status badges here -->
[![org: szl-holdings](https://img.shields.io/badge/org-szl--holdings-black)](https://github.com/szl-holdings)
[![doctrine](https://img.shields.io/badge/doctrine-control%20before%20action%20%C2%B7%20evidence%20after-blue)](https://a-11-oy.com)

**Control before action. Evidence after.**

Part of the [szl-holdings](https://github.com/szl-holdings) estate ·
Product: [a-11-oy.com](https://a-11-oy.com) ·
Proof: [a11oy.net](https://a11oy.net)
<!-- /szl:header -->

Kernel-twin repo for the ouroboros kernel package. **Not the TypeScript product** [`szl-holdings/ouroboros`](https://github.com/szl-holdings/ouroboros). **Not a model. No weights.**

Hub mirror: [`kernels/SZLHOLDINGS/szl-ouroboros`](https://huggingface.co/kernels/SZLHOLDINGS/szl-ouroboros). Card: [`SZLHOLDINGS/szl-ouroboros`](https://huggingface.co/SZLHOLDINGS/szl-ouroboros).

## What this is NOT

- Hub `model.joblib` is **QUARANTINED** executable serialization. Do not `joblib.load` it. GitHub source is the approved path.

- Not the `ouroboros` TypeScript service
- Not trained weights
- No MEASURED CUDA benches here

## Load

```python
from kernels import get_kernel
get_kernel("SZLHOLDINGS/szl-ouroboros", revision="main", trust_remote_code=True)
```

Doctrine v11. Λ = Conjecture 1 (advisory, never a theorem). Apache-2.0. Owner: Stephen Lutar / SZL Holdings.
