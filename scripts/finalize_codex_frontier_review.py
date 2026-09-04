#!/usr/bin/env python3
"""Validate a scheduled Codex review and close it with an Ouroboros receipt.

Codex is advisory. This operator accepts only schema-constrained, evidence-linked
recommendations over the exact Second Brain candidate set. It records measured
model and wall windows through the active szl_ouroboros loop-tax kernel. Missing
credentials remain explicit UNAVAILABLE evidence; invalid model output fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "torch-ext"))

import szl_ouroboros as ouroboros  # noqa: E402

REVIEW_SCHEMA = "szl.codex.frontier-review/v1"
SOURCE_SCHEMA = "szl.ouroboros.codex-frontier-source/v1"
RECEIPT_SCHEMA = "szl.ouroboros.codex-frontier-loop/v1"
CANDIDATE_ID = re.compile(r"^frontier:[0-9a-f]{32}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
RECOMMENDATION_ID = re.compile(r"^R[0-9]{2}$")
ALLOWED_STATES = {"REVIEW_PROPOSED", "NO_ACTION_RECOMMENDED", "BLOCKED"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_REPOSITORIES = {
    "szl-holdings/szl-second-brain",
    "szl-holdings/anatomy",
    "szl-holdings/a11oy",
    "szl-holdings/szl-formulas",
    "szl-holdings/szl-forge",
    "szl-holdings/szl-nemo",
    "szl-holdings/szl-ouroboros",
}
ALLOWED_CHANGE_TYPES = {
    "TEST",
    "DOCUMENTATION",
    "OBSERVABILITY",
    "INTEGRATION",
    "PERFORMANCE_EXPERIMENT",
    "SECURITY_HARDENING",
    "RESEARCH_EXPERIMENT",
    "NO_CHANGE",
}
NONE_AUTHORITY = {
    "training": "NONE",
    "promotion": "NONE",
    "execution": "NONE",
    "merge": "NONE",
    "provider_mutation": "NONE",
}
FORBIDDEN_TEXT = (
    re.compile(r"\bbypass(?:ing|ed)?\b", re.I),
    re.compile(r"\bdisable\s+(?:branch protection|signature|approval|authorization|safety)\b", re.I),
    re.compile(r"\bauto(?:matic(?:ally)?|nomous(?:ly)?)?[- ]?merge\b", re.I),
    re.compile(r"\bsilent(?:ly)?\s+(?:train|fine[- ]?tune|promote|deploy)\b", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
)


class ReviewError(RuntimeError):
    """The Codex review crossed a schema, evidence, or authority boundary."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"invalid JSON input: {path.name}") from exc
    if not isinstance(value, dict):
        raise ReviewError(f"JSON object required: {path.name}")
    return value


def load_candidate_ids(path: Path) -> set[str]:
    candidates: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReviewError("candidate corpus is unavailable") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReviewError(f"candidate line {line_number} is invalid") from exc
        candidate_id = str(row.get("id") or "") if isinstance(row, dict) else ""
        if not CANDIDATE_ID.fullmatch(candidate_id) or candidate_id in candidates:
            raise ReviewError(f"candidate identity failed at line {line_number}")
        candidates.add(candidate_id)
    if not candidates:
        raise ReviewError("candidate corpus is empty")
    return candidates


def _bounded_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ReviewError(f"{field} must be a string")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ReviewError(f"{field} is empty or exceeds {maximum} characters")
    for pattern in FORBIDDEN_TEXT:
        if pattern.search(text):
            raise ReviewError(f"{field} crossed the advisory boundary")
    return text


def validate_review(
    value: dict[str, Any],
    *,
    expected_candidate_digest: str,
    candidate_ids: set[str],
) -> dict[str, Any]:
    expected_keys = {
        "schema",
        "state",
        "candidate_set_sha256",
        "summary",
        "recommendations",
        "authority",
    }
    if set(value) != expected_keys:
        raise ReviewError("review top-level fields do not match the schema")
    if value.get("schema") != REVIEW_SCHEMA:
        raise ReviewError("review schema mismatch")
    if value.get("state") not in ALLOWED_STATES:
        raise ReviewError("review state is not allowed")
    digest = str(value.get("candidate_set_sha256") or "")
    if digest != expected_candidate_digest or not HEX_64.fullmatch(digest):
        raise ReviewError("review candidate-set digest mismatch")
    value["summary"] = _bounded_text(value.get("summary"), "summary", 2000)
    if value.get("authority") != NONE_AUTHORITY:
        raise ReviewError("Codex review claimed mutation authority")

    recommendations = value.get("recommendations")
    if not isinstance(recommendations, list) or len(recommendations) > 12:
        raise ReviewError("recommendations must be a list of at most twelve items")
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    expected_recommendation_keys = {
        "id",
        "priority",
        "target_repository",
        "title",
        "rationale",
        "evidence_candidate_ids",
        "recommended_change_type",
        "validation",
        "risk",
    }
    for index, recommendation in enumerate(recommendations):
        if not isinstance(recommendation, dict):
            raise ReviewError(f"recommendation {index} must be an object")
        if set(recommendation) != expected_recommendation_keys:
            raise ReviewError(f"recommendation {index} fields do not match the schema")
        recommendation_id = str(recommendation.get("id") or "")
        if not RECOMMENDATION_ID.fullmatch(recommendation_id) or recommendation_id in seen_ids:
            raise ReviewError(f"recommendation {index} identity is invalid")
        seen_ids.add(recommendation_id)
        priority = recommendation.get("priority")
        repository = recommendation.get("target_repository")
        change_type = recommendation.get("recommended_change_type")
        if priority not in ALLOWED_PRIORITIES:
            raise ReviewError(f"recommendation {index} priority is invalid")
        if repository not in ALLOWED_REPOSITORIES:
            raise ReviewError(f"recommendation {index} repository is outside the allowlist")
        if change_type not in ALLOWED_CHANGE_TYPES:
            raise ReviewError(f"recommendation {index} change type is invalid")
        evidence_ids = recommendation.get("evidence_candidate_ids")
        if (
            not isinstance(evidence_ids, list)
            or not 1 <= len(evidence_ids) <= 8
            or len(set(evidence_ids)) != len(evidence_ids)
            or any(candidate_id not in candidate_ids for candidate_id in evidence_ids)
        ):
            raise ReviewError(f"recommendation {index} evidence binding failed")
        validation = recommendation.get("validation")
        if not isinstance(validation, list) or not 1 <= len(validation) <= 8:
            raise ReviewError(f"recommendation {index} validation list is invalid")
        normalized_validation = [
            _bounded_text(step, f"recommendation {index} validation", 300)
            for step in validation
        ]
        normalized.append(
            {
                "id": recommendation_id,
                "priority": priority,
                "target_repository": repository,
                "title": _bounded_text(
                    recommendation.get("title"),
                    f"recommendation {index} title",
                    180,
                ),
                "rationale": _bounded_text(
                    recommendation.get("rationale"),
                    f"recommendation {index} rationale",
                    1200,
                ),
                "evidence_candidate_ids": list(evidence_ids),
                "recommended_change_type": change_type,
                "validation": normalized_validation,
                "risk": _bounded_text(
                    recommendation.get("risk"),
                    f"recommendation {index} risk",
                    600,
                ),
            }
        )
    if value["state"] == "NO_ACTION_RECOMMENDED" and normalized:
        raise ReviewError("no-action state cannot carry recommendations")
    if value["state"] == "REVIEW_PROPOSED" and not normalized:
        raise ReviewError("review-proposed state requires recommendations")
    value["recommendations"] = normalized
    return value


def finalize(
    *,
    source_receipt_path: Path,
    candidate_path: Path,
    review_path: Path,
    output_path: Path,
    codex_attempted: bool,
    codex_outcome: str,
    model: str,
    latency_ms: float,
    wall_ms: float,
) -> dict[str, Any]:
    source = read_json(source_receipt_path)
    if source.get("schema") != SOURCE_SCHEMA:
        raise ReviewError("source receipt schema mismatch")
    if source.get("authority") != NONE_AUTHORITY:
        raise ReviewError("source receipt authority drifted")
    candidate_digest = str(source.get("candidate_set_sha256") or "")
    if not HEX_64.fullmatch(candidate_digest):
        raise ReviewError("source candidate digest is malformed")
    candidate_ids = load_candidate_ids(candidate_path)
    if int(source.get("candidate_count") or -1) != len(candidate_ids):
        raise ReviewError("source receipt candidate count mismatch")

    normalized_outcome = codex_outcome.strip().lower()
    if not codex_attempted:
        state = "CODEX_UNAVAILABLE_MISSING_SECRET"
        review: dict[str, Any] | None = None
        review_sha = None
        attempts: list[dict[str, Any]] = []
        exit_state = "aborted"
        steps = 0
    else:
        if normalized_outcome != "success":
            state = "CODEX_FAILED"
            review = None
            review_sha = None
            attempts = [
                {
                    "provider": "openai",
                    "model": model or "codex-default",
                    "ok": False,
                    "latency_ms": max(0.0, latency_ms),
                    "node": "scheduled-frontier-review",
                }
            ]
            exit_state = "error"
            steps = 1
        else:
            review = validate_review(
                read_json(review_path),
                expected_candidate_digest=candidate_digest,
                candidate_ids=candidate_ids,
            )
            review_sha = sha256_bytes(canonical_bytes(review))
            state = str(review["state"])
            attempts = [
                {
                    "provider": "openai",
                    "model": model or "codex-default",
                    "ok": True,
                    "latency_ms": max(0.0, latency_ms),
                    "node": "scheduled-frontier-review",
                }
            ]
            exit_state = "converged"
            steps = 1

    loop = ouroboros.build_loop_trace(
        attempts,
        wall_ms=max(0.0, wall_ms),
        exit=exit_state,
        max_budget=1,
        steps=steps,
        aborted=not codex_attempted,
        trace_labels=["codex-frontier-review"] if attempts else [],
    )
    if loop.get("withinBudget") is not True:
        raise ReviewError("Ouroboros loop exceeded its declared budget")
    if loop.get("receiptsInEqOut") is not True:
        raise ReviewError("Ouroboros receipt closure failed")

    receipt_core: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "state": state,
        "source": source,
        "codex": {
            "attempted": codex_attempted,
            "outcome": normalized_outcome if codex_attempted else "not_attempted",
            "model": model or "codex-default",
            "review_sha256": review_sha,
            "review": review,
        },
        "ouroboros": loop,
        "authority": dict(NONE_AUTHORITY),
        "claims": {
            "candidate_material_is_training_data": False,
            "review_is_accepted_truth": False,
            "recommendations_executed": False,
            "weights_modified": False,
            "private_graph_loaded": False,
            "lambda": "CONJECTURE_1",
        },
    }
    receipt_core["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt_core))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt_core, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt_core


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-receipt", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex-attempted", choices=("true", "false"), required=True)
    parser.add_argument("--codex-outcome", default="not_attempted")
    parser.add_argument("--model", default="")
    parser.add_argument("--latency-ms", type=float, default=0.0)
    parser.add_argument("--wall-ms", type=float, default=0.0)
    args = parser.parse_args()
    receipt = finalize(
        source_receipt_path=args.source_receipt,
        candidate_path=args.candidates,
        review_path=args.review,
        output_path=args.output,
        codex_attempted=args.codex_attempted == "true",
        codex_outcome=args.codex_outcome,
        model=args.model,
        latency_ms=args.latency_ms,
        wall_ms=args.wall_ms,
    )
    print(
        json.dumps(
            {
                "state": receipt["state"],
                "receipt_sha256": receipt["receipt_sha256"],
                "loop_exit": receipt["ouroboros"]["exit"],
                "within_budget": receipt["ouroboros"]["withinBudget"],
            },
            sort_keys=True,
        )
    )
    if receipt["state"] == "CODEX_FAILED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
