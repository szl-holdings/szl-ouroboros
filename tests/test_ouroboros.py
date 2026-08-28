# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings · honest tests — MEASURED/DERIVED loop-tax arithmetic.
"""Tests for szl_ouroboros.

Honest: the arithmetic is FALSIFIABLE — a wrong split would flip these asserts.
Nothing is fabricated: an unmeasured wall yields overheadMs UNAVAILABLE (None).
"""
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "torch-ext"),
)

import szl_ouroboros as ou  # noqa: E402


def _attempts():
    return [
        {"provider": "sovereign", "model": "m", "ok": False, "latency_ms": 220, "node": "tower"},
        {"provider": "sovereign", "model": "m", "ok": True, "latency_ms": 900, "node": "laptop"},
    ]


def test_model_ms_is_sum_of_all_windows():
    assert ou.sum_attempt_ms(_attempts()) == 1120  # success AND failed hops


def test_peak_is_max_window():
    assert ou.peak_attempt_ms(_attempts()) == 900


def test_dead_hop_is_failed_before_served():
    assert ou.dead_hop_ms(_attempts()) == 220  # only the failed first hop


def test_dead_hop_stops_at_served():
    # A failed hop AFTER the served one is not a dead hop (loop already exited).
    attempts = [
        {"ok": True, "latency_ms": 100},
        {"ok": False, "latency_ms": 500},
    ]
    assert ou.dead_hop_ms(attempts) == 0


def test_full_trace_arithmetic():
    t = ou.build_loop_trace(_attempts(), wall_ms=1300, exit="converged", max_budget=4)
    assert t["modelMs"] == 1120       # MEASURED
    assert t["peakAttemptMs"] == 900  # MEASURED
    assert t["overheadMs"] == 180     # DERIVED 1300-1120
    assert t["serializationTaxMs"] == 220  # DERIVED 1120-900
    assert t["deadHopMs"] == 220      # DERIVED
    assert t["withinBudget"] is True  # 2 <= 4
    assert t["doctrine"] == "bounded, terminating, receipt-closed"
    assert t["timingBasis"] == ou.LOOP_TIMING_BASIS


def test_unmeasured_wall_is_unavailable_not_fabricated():
    t = ou.build_loop_trace(_attempts(), wall_ms=None, exit="converged", max_budget=4)
    assert t["overheadMs"] is None
    assert t["labels"]["overheadMs"] == "DERIVED"  # label stays; value honestly None
    tax = ou.loop_tax(_attempts(), wall_ms=None)
    assert tax["overheadMs"] is None
    assert tax["labels"]["overheadMs"] == "UNAVAILABLE"
    # the peak/serialization/deadHop split still holds (needs no wall)
    assert tax["serializationTaxMs"] == 220


def test_wall_less_than_model_is_flagged_not_hidden():
    t = ou.build_loop_trace(_attempts(), wall_ms=500, exit="converged", max_budget=4)
    assert t["overheadMs"] == 0        # clamped max(0, 500-1120)
    assert t["wallLessThanModel"] is True  # inconsistency surfaced, not hidden


def test_demo_run_has_no_model_window():
    t = ou.build_loop_trace([], wall_ms=50, exit="converged", max_budget=4)
    assert t["modelMs"] == 0
    assert t["peakAttemptMs"] == 0
    assert t["deadHopMs"] == 0
    assert t["overheadMs"] == 50  # all overhead — demo made no model call


def test_exit_classification():
    served = [{"ok": True, "latency_ms": 10}]
    assert ou.classify_exit(served, max_budget=4) == "converged"
    all_failed_full = [{"ok": False, "latency_ms": 10}] * 4
    assert ou.classify_exit(all_failed_full, max_budget=4) == "budgetExhausted"
    all_failed_partial = [{"ok": False, "latency_ms": 10}]
    assert ou.classify_exit(all_failed_partial, max_budget=4) == "error"
    assert ou.classify_exit(served, max_budget=4, aborted=True) == "aborted"


def test_budget_violation_is_surfaced():
    t = ou.build_loop_trace(_attempts(), wall_ms=1300, exit="converged", max_budget=1)
    assert t["withinBudget"] is False  # steps(2) > maxBudget(1) — bound VIOLATED, surfaced


def test_bad_exit_raises():
    try:
        ou.build_loop_trace(_attempts(), wall_ms=1300, exit="teleported", max_budget=4)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_missing_latency_raises_never_coerced():
    try:
        ou.sum_attempt_ms([{"ok": True}])  # no latency_ms
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_selfcheck_arithmetic_ok():
    sc = ou.selfcheck()
    assert sc["arithmetic_ok"] is True
    assert "Conjecture 1" in sc["lambda_status"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"OK — {len(fns)}/{len(fns)} szl_ouroboros tests passed.")
