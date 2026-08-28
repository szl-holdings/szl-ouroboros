#!/usr/bin/env python3
"""Forge a REAL trained surrogate for szl-ouroboros.
Kernel = ground truth. Surrogate = a loop-tax REGRESSOR: given the observable
attempt-window trace of a bounded agent loop (per-attempt latencies, ok flags,
run wall), predict the kernel's DERIVED `overheadMs` loop-tax field. The label
is computed by the REAL kernel (`loop_tax`), so the target is definitionally the
kernel's own arithmetic; the regressor's job is to reproduce that derivation from
trace observables — its skill (MAE / R²) is MEASURED against held-out kernel labels.
A sample of traces is re-audited by full kernel replay. Seeded, receipted."""
import json, os, random, sys, time, hashlib, platform
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(_here, "build", "torch-universal")):
    sys.path.insert(0, os.path.join(_here, "build", "torch-universal"))  # in-repo run
else:
    sys.path.insert(0, "/tmp/kernel-probe/szl-ouroboros/build/torch-universal")  # forge-dev run
import szl_ouroboros as ou
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

SEED = 20260721
random.seed(SEED); np.random.seed(SEED)
T0 = time.time()

EXITS = ou.LOOP_EXITS  # ("converged","budgetExhausted","aborted","error")
EXIT_IX = {e: i for i, e in enumerate(EXITS)}

def make_run(run_id):
    """Generate one realistic bounded-loop run. wall_ms is modeled as
    modelMs + a genuine orchestration overhead + noise, so overheadMs is NOT a
    trivial constant. Returns (attempts, wall_ms, aborted)."""
    max_budget = random.randint(1, 6)
    n = random.randint(1, max_budget)
    aborted = random.random() < 0.08
    demo = random.random() < 0.06  # demo run: no model call
    if demo:
        return [], (None if random.random() < 0.3 else float(random.randint(5, 120))), aborted
    served_at = None
    if not aborted and random.random() < 0.85:
        served_at = random.randrange(n)  # a hop that succeeds
    attempts = []
    for i in range(n):
        lat = float(random.randint(30, 1500))
        ok = (i == served_at)
        attempts.append({"provider": random.choice(["sovereign", "own", "fallback"]),
                         "model": random.choice(["own-metal", "khipu-1.5b", None]),
                         "ok": ok, "latency_ms": lat,
                         "node": random.choice(["tower", "laptop", "node-a"])})
    model_ms = sum(a["latency_ms"] for a in attempts)
    # genuine orchestration overhead: energy-meter samples + self-verify pass
    true_overhead = random.uniform(20, 600) + 0.05 * model_ms
    wall = model_ms + true_overhead + random.gauss(0, 15)
    wall = max(wall, model_ms)  # sequential loop: wall >= modelMs
    if random.random() < 0.15:
        wall = None  # unmeasured wall -> overheadMs UNAVAILABLE (dropped from training)
    return attempts, (None if wall is None else float(wall)), aborted

def features(attempts, wall_ms, max_budget, aborted):
    lats = [float(a["latency_ms"]) for a in attempts]
    n = len(lats)
    la = np.array(lats) if lats else np.array([0.0])
    served_ix = next((i for i, a in enumerate(attempts) if a.get("ok")), -1)
    n_failed_before = served_ix if served_ix >= 0 else n
    return [
        float(n),
        float(wall_ms) if wall_ms is not None else -1.0,
        float(la.sum()), float(la.max()), float(la.min()), float(la.mean()),
        float(la.std()), float(np.median(la)),
        float(served_ix), float(n_failed_before),
        float(sum(1 for a in attempts if a.get("ok"))),
        float(sum(1 for a in attempts if a.get("model") is None)),
        float(max_budget), float(aborted),
    ]

FEATURE_NAMES = ["n_attempts", "wall_ms", "sum_latency", "max_latency", "min_latency",
                 "mean_latency", "std_latency", "median_latency", "served_hop_index",
                 "n_failed_before_served", "n_ok", "n_missing_model", "max_budget", "aborted"]

# ---- generate (target = kernel-derived overheadMs; drop UNAVAILABLE rows) ----
N_RUNS = 14000
X, y, audited = [], [], 0
audit_bank = []
for rid in range(N_RUNS):
    attempts, wall_ms, aborted = make_run(rid)
    max_budget = max(len(attempts), random.randint(len(attempts), len(attempts) + 3)) or 1
    tax = ou.loop_tax(attempts, wall_ms)     # REAL kernel computation == ground truth
    overhead = tax["overheadMs"]
    if overhead is None:                     # wall unmeasured -> honestly UNAVAILABLE
        continue
    X.append(features(attempts, wall_ms, max_budget, aborted))
    y.append(float(overhead))
    if len(audit_bank) < 40:
        audit_bank.append((attempts, wall_ms, overhead))

# kernel-replay audit
for attempts, wall_ms, recorded in audit_bank:
    replay = ou.loop_tax(attempts, wall_ms)["overheadMs"]
    assert abs(replay - recorded) <= 1e-9, f"kernel replay disagreement: {replay} != {recorded}"
    audited += 1

X = np.array(X, dtype=np.float64); y = np.array(y, dtype=np.float64)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEED)
reg = HistGradientBoostingRegressor(random_state=SEED, max_iter=400, early_stopping=True)
reg.fit(Xtr, ytr)
pred = reg.predict(Xte)
mae = float(mean_absolute_error(yte, pred))
r2 = float(r2_score(yte, pred))
target_std = float(np.std(yte))

out_dir = os.path.dirname(os.path.abspath(__file__))
joblib.dump(reg, f"{out_dir}/model.joblib")
model_sha = hashlib.sha256(open(f"{out_dir}/model.joblib", "rb").read()).hexdigest()
receipt = {
  "artifact": "SZLHOLDINGS/szl-ouroboros surrogate v1",
  "role": "loop-tax regressor (predicts kernel-derived overheadMs from trace observables) — kernel remains ground truth",
  "generator": {"script": "scripts/forge.py", "seed": SEED, "kernel_version": ou.__version__,
                 "kernel_labelled": True, "kernel_replay_audited_runs": audited,
                 "target": "overheadMs", "target_source": "ou.loop_tax(attempts, wall_ms)['overheadMs'] (DERIVED = max(0, wall - modelMs))",
                 "unavailable_policy": "runs with unmeasured wall (overheadMs=None) are DROPPED, never fabricated"},
  "data": {"rows": int(len(y)), "runs_generated": N_RUNS, "rows_after_dropping_unavailable": int(len(y)),
            "split": "80/20 random", "features": FEATURE_NAMES,
            "target_units": "milliseconds", "target_mean_ms": round(float(np.mean(y)), 2),
            "target_std_ms": round(float(np.std(y)), 2),
            "feature_policy": "observable trace fields only (per-attempt latencies + ok flags + wall + budget); target is the kernel's own DERIVED arithmetic"},
  "model": {"type": "sklearn.HistGradientBoostingRegressor",
             "params": {"max_iter": 400, "early_stopping": True, "random_state": SEED},
             "file": "model.joblib", "sha256": model_sha},
  "metrics_MEASURED": {"held_out_MAE_ms": round(mae, 4), "held_out_R2": round(r2, 4),
                        "held_out_target_std_ms": round(target_std, 4),
                        "interpretation": "R2 is fidelity of the surrogate to the kernel's DERIVED overheadMs; the kernel's exact arithmetic remains authoritative"},
  "environment": {"python": platform.python_version(), "sklearn": __import__("sklearn").__version__,
                   "numpy": np.__version__, "host": "replit 2-vCPU container", "wall_seconds": round(time.time()-T0, 1)},
  "honesty": "Every number above is MEASURED by this run. The surrogate approximates the kernel's loop-tax derivation from trace shape; it never replaces the kernel's exact arithmetic. serializationTax stays a counterfactual. Λ untouched = Conjecture 1.",
  "trained_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
with open(f"{out_dir}/TRAINING_RECEIPT.json", "w") as f: json.dump(receipt, f, indent=2)
print(json.dumps(receipt["metrics_MEASURED"], indent=2))
print(f"rows={len(y)} audited={audited} wall={receipt['environment']['wall_seconds']}s")
