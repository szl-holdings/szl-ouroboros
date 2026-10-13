# SPDX-License-Identifier: Apache-2.0
"""Smoke hook for hf-kernel-publish (szl-ouroboros).

`smoke(kernel)` receives the module that the `kernels` loader imported, from a local
build (check-local) or from the Hub (verify). Raise, or return False, to fail the run.
CPU-only, deterministic, stdlib arithmetic. The result's repr is written to the receipt.
"""
from __future__ import annotations


def smoke(kernel):
    check = kernel.selfcheck()
    if check.get("arithmetic_ok") is not True or check.get("withinBudget") is not True:
        raise AssertionError(f"selfcheck failed: {check}")
    attempts = [
        {"provider": "sovereign", "model": "m", "ok": False, "latency_ms": 220, "node": "tower"},
        {"provider": "sovereign", "model": "m", "ok": True, "latency_ms": 900, "node": "laptop"},
    ]
    trace = kernel.build_loop_trace(attempts, wall_ms=1300, max_budget=4)
    expected = {"modelMs": 1120.0, "overheadMs": 180.0, "peakAttemptMs": 900.0,
                "serializationTaxMs": 220.0, "deadHopMs": 220.0, "exit": "converged",
                "withinBudget": True, "servedHopIndex": 1}
    got = {key: trace[key] for key in expected}
    if got != expected:
        raise AssertionError(f"loop trace arithmetic differs: {got} != {expected}")
    unmeasured = kernel.loop_tax(attempts, wall_ms=None)
    if unmeasured["overheadMs"] is not None or unmeasured["labels"]["overheadMs"] != "UNAVAILABLE":
        raise AssertionError("an unmeasured wall must leave overheadMs UNAVAILABLE")
    return {"version": check["version"], "doctrine": check["doctrine"], **got}
