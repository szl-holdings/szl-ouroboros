# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings · Stephen P. Lutar · ORCID 0009-0001-0110-4173
"""szl_ouroboros — bounded-loop trace + loop-tax accounting, honestly labelled.

============================ HONEST SCOPE BOX ============================
This is NOT a trained model. There are NO weights (.safetensors/.bin/.pt/.gguf).
It is a pure-Python, stdlib-only governance kernel that reconstructs the a11oy
agent-loop trace and its LOOP-TAX decomposition from a run's provider-attempt
windows. `get_kernel`-discoverable purely so the family loads the same way; it
uses no tensors and does no arithmetic beyond sums, max, and subtraction.

WHAT IS MEASURED vs DERIVED (mirrors backbone.ts LOOP_TIMING_BASIS, verbatim
carried on every trace):
  - modelMs         = MEASURED — Σ of every provider-attempt wall window
                      (network + provider time, success AND failed hops).
  - peakAttemptMs   = MEASURED — the single slowest attempt window observed.
  - overheadMs      = DERIVED  — max(0, runWall − modelMs): everything Alloy
                      itself did around the model calls; NOT pure CPU time.
  - serializationTaxMs = DERIVED — max(0, modelMs − peak): a COUNTERFACTUAL
                      (what a perfectly-parallel loop could save), NEVER a
                      realized saving. Alloy's loop is strictly sequential.
  - deadHopMs       = DERIVED — Σ of failed-attempt windows BEFORE the served
                      hop (the upper bound speculative warming could hide).
                      Alloy does NOT prefetch.

Wall time and each attempt window are MEASURED upstream; the SPLIT is honest
arithmetic on those measurements — never a new claim. Demo runs make no model
call, so modelMs / peak / deadHop are honestly 0.

LOOP_DOCTRINE = "bounded, terminating, receipt-closed" — the Ouroboros closes
on its own tail. `receiptsInEqOut` is a DOCTRINE invariant (one receipt trail
in, one out), NOT a mathematical proof; it is labelled as such. This kernel
does not touch Λ, which stays Conjecture 1.
=========================================================================

Quickstart:

    from kernels import get_kernel
    ou = get_kernel("SZLHOLDINGS/szl-ouroboros", revision="main", trust_remote_code=True)

    attempts = [
        {"provider": "sovereign", "model": "own-metal", "ok": False, "latency_ms": 220, "node": "tower"},
        {"provider": "sovereign", "model": "own-metal", "ok": True,  "latency_ms": 900, "node": "laptop"},
    ]
    trace = ou.build_loop_trace(attempts, wall_ms=1300, exit="converged", max_budget=4)
    print(trace["modelMs"], trace["overheadMs"], trace["deadHopMs"])   # 1120 180 220
    print(ou.explain(trace["labels"]))     # per-field MEASURED/DERIVED provenance
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "build_loop_trace",
    "loop_tax",
    "sum_attempt_ms",
    "peak_attempt_ms",
    "dead_hop_ms",
    "classify_exit",
    "explain",
    "selfcheck",
    "LOOP_DOCTRINE",
    "LOOP_TIMING_BASIS",
    "LOOP_EXITS",
    "MAX_ALTERNATES",
    "LABELS",
    "PROVENANCE",
    "DOCTRINE_FOOTER",
    "__version__",
]

__version__ = "0.1.0"

# Verbatim from artifacts/api-server/src/lib/backbone.ts.
LOOP_DOCTRINE = "bounded, terminating, receipt-closed"

LOOP_TIMING_BASIS = (
    "modelMs = MEASURED Σ provider-attempt wall windows (network + provider time, "
    "not pure compute); overheadMs = DERIVED (run wall − modelMs): Alloy's own "
    "orchestration around the model calls, incl. energy-meter samples and any "
    "self-verification pass. peakAttemptMs = MEASURED max single attempt window "
    "(peak-vs-sum, AirLLM ingest); serializationTaxMs = DERIVED (modelMs − peak), "
    "a counterfactual never a realized saving; deadHopMs = DERIVED Σ failed-attempt "
    "windows before the served hop — Alloy does NOT prefetch. Demo runs have no "
    "model window."
)

# LoopExit union from backbone.ts.
LOOP_EXITS = ("converged", "budgetExhausted", "aborted", "error")

# Bounded budget: at most 1 primary + MAX_ALTERNATES fallbacks per provider,
# but the real per-run ceiling is targets.length (multi-node sovereign expands).
MAX_ALTERNATES = 2

# Per-field honesty labels — the whole point of this kernel.
LABELS: Dict[str, str] = {
    "modelMs": "MEASURED",
    "peakAttemptMs": "MEASURED",
    "overheadMs": "DERIVED",
    "serializationTaxMs": "DERIVED",
    "deadHopMs": "DERIVED",
    "steps": "MEASURED",
    "maxBudget": "DECLARED",
    "exit": "REPORTED",
    "receiptsInEqOut": "DOCTRINE",
    "wallMs": "MEASURED",
}

PROVENANCE = {
    "mirrors": "a11oy backbone loop tax (artifacts/api-server/src/lib/backbone.ts buildLoopTrace)",
    "timing_basis_ingest": "NVIDIA Vera (sequential agent loop) + AirLLM (peak-vs-sum)",
    "lambda_status": "Conjecture 1 (open) — untouched by loop-tax accounting",
    "trained_weights_present": False,
}

DOCTRINE_FOOTER = (
    "SZL Holdings · Ouroboros = bounded, terminating, receipt-closed · modelMs/peak "
    "MEASURED, the rest DERIVED · serializationTax is a counterfactual, never a saving "
    "· Λ untouched = Conjecture 1 · honesty over checklist"
)


# --------------------------------------------------------------------------- #
# Core windows — EXACTLY mirror backbone.ts sumAttemptMs/peakAttemptMs/deadHopMs
# --------------------------------------------------------------------------- #
def _lat(attempt: Dict[str, Any]) -> float:
    v = attempt.get("latency_ms")
    if v is None:
        raise ValueError("each attempt must carry a MEASURED latency_ms window")
    return float(v)


def sum_attempt_ms(attempts: Sequence[Dict[str, Any]]) -> float:
    """MEASURED model window: Σ of every attempt's wall window (success AND
    failed — a failed provider call still occupied the loop)."""
    return sum(_lat(a) for a in attempts)


def peak_attempt_ms(attempts: Sequence[Dict[str, Any]]) -> float:
    """MEASURED slowest single hop; 0 when there were no attempts (demo run —
    no model call, honestly no peak)."""
    return max((_lat(a) for a in attempts), default=0.0)


def dead_hop_ms(attempts: Sequence[Dict[str, Any]]) -> float:
    """DERIVED Σ of failed-attempt windows BEFORE the served one. Attempts are
    in loop order; everything before the first ok row is a dead hop. When
    nothing served, every hop was dead. Never counts the serving attempt."""
    acc = 0.0
    for a in attempts:
        if a.get("ok"):
            break
        acc += _lat(a)
    return acc


def classify_exit(
    attempts: Sequence[Dict[str, Any]],
    max_budget: int,
    aborted: bool = False,
) -> str:
    """Honest exit classification from the attempt trace:
      - aborted=True → 'aborted' (caller signalled a hard stop).
      - any served (ok) hop → 'converged'.
      - no served hop and every one of max_budget targets was tried → 'budgetExhausted'.
      - no served hop with budget remaining → 'error' (all reached targets failed early).
    """
    if aborted:
        return "aborted"
    if any(a.get("ok") for a in attempts):
        return "converged"
    if len(attempts) >= max_budget:
        return "budgetExhausted"
    return "error"


# --------------------------------------------------------------------------- #
# Loop-tax accounting                                                          #
# --------------------------------------------------------------------------- #
def loop_tax(
    attempts: Sequence[Dict[str, Any]],
    wall_ms: Optional[float],
) -> Dict[str, Any]:
    """Decompose a run's timing into the honest MEASURED/DERIVED loop-tax split.

    `wall_ms=None` → the run wall was not measured, so overheadMs is UNAVAILABLE
    (never fabricated); the peak/serialization/deadHop split still holds because
    it needs only the attempt windows.
    """
    attempts = list(attempts)
    model_ms = sum_attempt_ms(attempts)
    peak = peak_attempt_ms(attempts)
    serialization_tax = max(0.0, model_ms - peak)
    dead_hop = dead_hop_ms(attempts)
    if wall_ms is None:
        overhead: Optional[float] = None
        overhead_label = "UNAVAILABLE"
        wall_lt_model = None
    else:
        wall_ms = float(wall_ms)
        overhead = max(0.0, wall_ms - model_ms)
        overhead_label = "DERIVED"
        # Honest flag: sequential loop ⇒ wall should be ≥ modelMs; a smaller
        # wall means a measurement inconsistency (surfaced, not hidden).
        wall_lt_model = wall_ms + 1e-9 < model_ms
    return {
        "modelMs": model_ms,
        "peakAttemptMs": peak,
        "serializationTaxMs": serialization_tax,
        "deadHopMs": dead_hop,
        "overheadMs": overhead,
        "wallMs": wall_ms,
        "attemptCount": len(attempts),
        "servedHopIndex": next(
            (i for i, a in enumerate(attempts) if a.get("ok")), None
        ),
        "wallLessThanModel": wall_lt_model,
        "labels": {
            "modelMs": "MEASURED",
            "peakAttemptMs": "MEASURED",
            "serializationTaxMs": "DERIVED (counterfactual — never a realized saving)",
            "deadHopMs": "DERIVED (no prefetch — upper bound only)",
            "overheadMs": overhead_label,
            "wallMs": "MEASURED" if wall_ms is not None else "UNAVAILABLE",
        },
        "timingBasis": LOOP_TIMING_BASIS,
    }


def build_loop_trace(
    attempts: Sequence[Dict[str, Any]],
    wall_ms: Optional[float],
    exit: Optional[str] = None,
    max_budget: Optional[int] = None,
    steps: Optional[int] = None,
    aborted: bool = False,
    trace_labels: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Reconstruct the full LoopTrace (mirror of backbone.ts buildLoopTrace) with
    the loop-tax split and honesty labels attached.

    - `steps=None` defaults to the number of attempts (each attempt is a loop hop).
    - `max_budget=None` defaults to len(attempts) (unknown ceiling ⇒ report the
      hops actually taken; never invent a larger budget).
    - `exit=None` is classified honestly from the trace via classify_exit.
    - `withinBudget` surfaces the bounded-loop guarantee (steps ≤ maxBudget); a
      False here is a real bound VIOLATION, never silently clamped.
    """
    attempts = list(attempts)
    n = len(attempts)
    steps = n if steps is None else int(steps)
    max_budget = n if max_budget is None else int(max_budget)
    if exit is None:
        exit = classify_exit(attempts, max_budget, aborted=aborted)
    if exit not in LOOP_EXITS:
        raise ValueError(f"exit must be one of {LOOP_EXITS}, got {exit!r}")
    tax = loop_tax(attempts, wall_ms)
    within_budget = steps <= max_budget
    trace: List[Dict[str, Any]]
    if trace_labels is not None:
        trace = [{"n": i + 1, "label": lbl} for i, lbl in enumerate(trace_labels)]
    else:
        trace = [
            {
                "n": i + 1,
                "provider": a.get("provider"),
                "model": a.get("model"),
                "node": a.get("node"),
                "ok": bool(a.get("ok")),
                "latencyMs": _lat(a),
                "latencyLabel": "MEASURED",
            }
            for i, a in enumerate(attempts)
        ]
    return {
        "steps": steps,
        "maxBudget": max_budget,
        "withinBudget": within_budget,
        "boundedDoctrine": "steps ≤ maxBudget (bounded, terminating)",
        "exit": exit,
        "trace": trace,
        "doctrine": LOOP_DOCTRINE,
        "receiptsInEqOut": True,
        "receiptsInEqOutBasis": "DOCTRINE invariant (one receipt trail in, one out) — NOT a mathematical proof",
        "modelMs": tax["modelMs"],
        "overheadMs": tax["overheadMs"],
        "peakAttemptMs": tax["peakAttemptMs"],
        "serializationTaxMs": tax["serializationTaxMs"],
        "deadHopMs": tax["deadHopMs"],
        "wallMs": tax["wallMs"],
        "servedHopIndex": tax["servedHopIndex"],
        "wallLessThanModel": tax["wallLessThanModel"],
        "labels": dict(LABELS),
        "timingBasis": LOOP_TIMING_BASIS,
    }


def explain(labels: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Human-readable provenance for each loop-tax field (MEASURED vs DERIVED)."""
    base = {
        "modelMs": "MEASURED — Σ provider-attempt wall windows (network + provider time, not pure compute)",
        "peakAttemptMs": "MEASURED — the single slowest attempt window observed",
        "overheadMs": "DERIVED — max(0, runWall − modelMs); Alloy's own orchestration, NOT pure CPU time",
        "serializationTaxMs": "DERIVED — max(0, modelMs − peak); a COUNTERFACTUAL, never a realized saving",
        "deadHopMs": "DERIVED — Σ failed windows before the served hop; no prefetch, upper bound only",
        "receiptsInEqOut": "DOCTRINE invariant — one receipt trail in, one out; NOT a proof",
        "exit": "REPORTED — converged / budgetExhausted / aborted / error",
        "maxBudget": "DECLARED — per-run attempt ceiling (targets.length); steps ≤ maxBudget is the bound",
    }
    if labels:
        base = {**base, **{k: f"{v}" for k, v in labels.items() if k not in base}}
    return base


def selfcheck() -> Dict[str, Any]:
    """One-shot CPU health check: build a trace with a known dead hop and verify
    the MEASURED/DERIVED arithmetic (falsifiable — wrong math would flip these).
    Does NOT touch Λ (Conjecture 1)."""
    attempts = [
        {"provider": "sovereign", "model": "m", "ok": False, "latency_ms": 220, "node": "tower"},
        {"provider": "sovereign", "model": "m", "ok": True, "latency_ms": 900, "node": "laptop"},
    ]
    t = build_loop_trace(attempts, wall_ms=1300, exit="converged", max_budget=4)
    return {
        "version": __version__,
        "doctrine": LOOP_DOCTRINE,
        "modelMs": t["modelMs"],  # 1120 MEASURED
        "peakAttemptMs": t["peakAttemptMs"],  # 900 MEASURED
        "overheadMs": t["overheadMs"],  # 180 DERIVED (1300-1120)
        "serializationTaxMs": t["serializationTaxMs"],  # 220 DERIVED (1120-900)
        "deadHopMs": t["deadHopMs"],  # 220 DERIVED (first failed hop)
        "withinBudget": t["withinBudget"],  # True (2 <= 4)
        "arithmetic_ok": (
            t["modelMs"] == 1120
            and t["overheadMs"] == 180
            and t["serializationTaxMs"] == 220
            and t["deadHopMs"] == 220
        ),
        "lambda_status": "Conjecture 1 (open) — untouched by loop-tax accounting",
    }
