# szl-ouroboros

Kernel-twin repo for the ouroboros kernel package. **Not the TypeScript product** [`szl-holdings/ouroboros`](https://github.com/szl-holdings/ouroboros). **Not a model. No weights.**

Hub mirror: [`kernels/SZLHOLDINGS/szl-ouroboros`](https://huggingface.co/kernels/SZLHOLDINGS/szl-ouroboros). Card: [`SZLHOLDINGS/szl-ouroboros`](https://huggingface.co/SZLHOLDINGS/szl-ouroboros).

## What this is NOT

- Not the `ouroboros` TypeScript service
- Not trained weights
- No MEASURED CUDA benches here

## Load

```python
from kernels import get_kernel
get_kernel("SZLHOLDINGS/szl-ouroboros", revision="main", trust_remote_code=True)
```

Doctrine v11. Λ = Conjecture 1 (advisory, never a theorem). Apache-2.0. Owner: Stephen Lutar / SZL Holdings.
