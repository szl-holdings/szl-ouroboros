"""Invalid observations cannot become measured timing evidence."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "timing_kernel", ROOT / "torch-ext/szl_ouroboros/__init__.py"
)
ou = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ou)

INVALID = [
    pytest.param(-1, id="negative"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
    pytest.param("12.5", id="numeric-text"),
    pytest.param([], id="array"),
    pytest.param(10**400, id="unrepresentable-int"),
]


@pytest.mark.parametrize("value", INVALID)
@pytest.mark.parametrize("entry", ["sum_attempt_ms", "peak_attempt_ms", "dead_hop_ms"])
def test_window_helpers_reject_invalid_observations(entry, value):
    with pytest.raises(ValueError, match="latency_ms.*finite.*nonnegative"):
        getattr(ou, entry)([{"ok": False, "latency_ms": value}])


@pytest.mark.parametrize("value", INVALID)
@pytest.mark.parametrize("entry", ["loop_tax", "build_loop_trace"])
def test_trace_rejects_invalid_attempt_after_served_hop(entry, value):
    attempts = [{"ok": True, "latency_ms": 1}, {"ok": False, "latency_ms": value}]
    with pytest.raises(ValueError, match="latency_ms.*finite.*nonnegative"):
        getattr(ou, entry)(attempts, wall_ms=10)


@pytest.mark.parametrize("value", INVALID)
@pytest.mark.parametrize("entry", ["loop_tax", "build_loop_trace"])
def test_trace_rejects_invalid_wall_even_without_attempts(entry, value):
    with pytest.raises(ValueError, match="wall_ms.*finite.*nonnegative"):
        getattr(ou, entry)([], wall_ms=value)


@pytest.mark.parametrize("entry", ["sum_attempt_ms", "dead_hop_ms", "loop_tax", "build_loop_trace"])
def test_finite_windows_cannot_overflow_into_timing_evidence(entry):
    attempts = [{"ok": False, "latency_ms": sys.float_info.max}] * 2
    call = getattr(ou, entry)
    kwargs = {"wall_ms": None} if entry in {"loop_tax", "build_loop_trace"} else {}
    with pytest.raises(ValueError, match="sum.*finite"):
        call(attempts, **kwargs)


def test_large_but_representable_windows_and_zero_remain_valid():
    largest = sys.float_info.max
    attempts = [{"ok": False, "latency_ms": largest / 2}] * 2
    trace = ou.build_loop_trace(attempts, wall_ms=largest)
    assert trace["modelMs"] == largest
    assert trace["deadHopMs"] == largest
    assert trace["overheadMs"] == 0
    assert math.isfinite(trace["serializationTaxMs"])
    json.dumps(trace, allow_nan=False)
    assert ou.build_loop_trace([{"ok": True, "latency_ms": 0}], wall_ms=0)["modelMs"] == 0


def test_missing_wall_and_inconsistent_finite_wall_keep_existing_meanings():
    attempts = [{"ok": True, "latency_ms": 0.5}]
    missing = ou.loop_tax(attempts, wall_ms=None)
    assert missing["overheadMs"] is None
    assert missing["labels"]["wallMs"] == "UNAVAILABLE"
    inconsistent = ou.loop_tax(attempts, wall_ms=0.25)
    assert inconsistent["wallLessThanModel"] is True
    assert inconsistent["overheadMs"] == 0


def test_build_mirror_is_exact_and_rejects_invalid_timing():
    canonical = ROOT / "torch-ext/szl_ouroboros/__init__.py"
    mirror = ROOT / "build/torch-universal/szl_ouroboros/__init__.py"
    assert canonical.read_bytes() == mirror.read_bytes()
    spec = importlib.util.spec_from_file_location("timing_build_mirror", mirror)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="latency_ms.*finite.*nonnegative"):
        module.build_loop_trace([{"ok": True, "latency_ms": float("nan")}], wall_ms=0)
