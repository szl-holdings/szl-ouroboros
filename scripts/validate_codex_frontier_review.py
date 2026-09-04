#!/usr/bin/env python3
"""Validate and receipt one Codex frontier-review proposal.

Validation is deterministic and independent of the model. Every cited handle must
exist in the exact input snapshot, all authority fields must remain review-only,
and unsafe command/secrets patterns are rejected before a GitHub review issue can
be created.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "szl.ouroboros.codex-frontier-review/v1"
STATE = "PROPOSAL_REVIEW_REQUIRED"
ALLOWED_REPOSITORIES = {
    "szl-holdings/szl-second-brain",
    "szl-holdings/anatomy",
    "szl-holdings/a11oy",
    "szl-holdings/szl-formulas",
    "szl-holdings/szl-forge",
    "szl-holdings/szl-nemo",
    "szl-holdings/szl-ouroboros",
}
ALLOWED_SCOPES = {
    "DOCUMENTATION",
    "TEST",
    "READ_ONLY_RUNTIME",
    "VISUALIZATION",
    "EVALUATION",
    "RESEARCH_PROPOSAL",
}
ALLOWED_RISKS = {"LOW", "MEDIUM", "HIGH"}
HANDLE = re.compile(r"^frontier:[0-9a-f]{32}$")
REC_ID = re.compile(r"^REC-[0-9]{3}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
PROHIBITED_ACTION_PATTERNS = (
    re.compile(r"\b(?:sudo|curl|wget)\s+", re.IGNORECASE),
    re.compile(r"\bgit\s+(?:push|merge|rebase|reset|commit)\b", re.IGNORECASE),
    re.compile(r"\b(?:rm\s+-rf|chmod\s+777|chown\s+)\b", re.IGNORECASE),
    re.compile(r"\b(?:deploy|publish|delete|destroy)\s+(?:now|directly|automatically)\b", re.IGNORECASE),
    re.compile(r"\b(?:bypass|disable)\s+(?:security|protection|review|approval)\b", re.IGNORECASE),
)


class ReviewValidationError(RuntimeError):
    """The model output failed the fixed review contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(payload)
        handle.flush()
        temporary = Path(handle.name)
    temporary.replace(path)


def parse_json_result(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
            if text.startswith("json\n"):
                text = text[5:]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReviewValidationError("Codex output was not a single JSON object") from exc
    if not isinstance(value, dict):
        raise ReviewValidationError("Codex output must be an object")
    return value


def require_exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ReviewValidationError(
            f"{context} keys differ: missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )


def require_text(value: Any, *, context: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ReviewValidationError(f"{context} must be non-empty text <= {maximum} characters")
    return value.strip()


def reject_unsafe_text(value: str, *, context: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            raise ReviewValidationError(f"secret-like material rejected in {context}")
    for pattern in PROHIBITED_ACTION_PATTERNS:
        if pattern.search(value):
            raise ReviewValidationError(f"direct execution language rejected in {context}")


def validate(
    input_payload: dict[str, Any],
    review: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    require_exact_keys(
        review,
        {
            "schema",
            "candidate_set_sha256",
            "state",
            "summary",
            "recommendations",
            "authority",
        },
        "review",
    )
    if review["schema"] != SCHEMA or review["state"] != STATE:
        raise ReviewValidationError("review schema or state mismatch")
    candidate_set = str(review["candidate_set_sha256"])
    expected_set = str(input_payload.get("source", {}).get("candidate_set_sha256") or "")
    if not HEX_64.fullmatch(candidate_set) or candidate_set != expected_set:
        raise ReviewValidationError("candidate-set identity mismatch")
    summary = require_text(review["summary"], context="summary", maximum=1600)
    reject_unsafe_text(summary, context="summary")

    authority = review["authority"]
    if not isinstance(authority, dict):
        raise ReviewValidationError("authority must be an object")
    require_exact_keys(
        authority,
        {"mode", "execution", "merge", "provider_mutation", "training", "promotion"},
        "authority",
    )
    expected_authority = {
        "mode": "REVIEW_ONLY",
        "execution": "NONE",
        "merge": "NONE",
        "provider_mutation": "NONE",
        "training": "NONE",
        "promotion": "NONE",
    }
    if authority != expected_authority:
        raise ReviewValidationError("authority escaped the review-only boundary")

    candidates = input_payload.get("candidates")
    if not isinstance(candidates, list):
        raise ReviewValidationError("input candidates are missing")
    allowed_handles = {
        str(candidate.get("handle"))
        for candidate in candidates
        if isinstance(candidate, dict) and HANDLE.fullmatch(str(candidate.get("handle") or ""))
    }
    if not allowed_handles:
        raise ReviewValidationError("input has no admitted handles")

    recommendations = review["recommendations"]
    if not isinstance(recommendations, list) or len(recommendations) > 12:
        raise ReviewValidationError("recommendations must be an array with at most 12 items")
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, recommendation in enumerate(recommendations):
        context = f"recommendation[{index}]"
        if not isinstance(recommendation, dict):
            raise ReviewValidationError(f"{context} must be an object")
        require_exact_keys(
            recommendation,
            {
                "id",
                "title",
                "rationale",
                "source_handles",
                "target_repository",
                "scope",
                "risk",
                "verification",
                "claims",
            },
            context,
        )
        recommendation_id = str(recommendation["id"])
        if not REC_ID.fullmatch(recommendation_id) or recommendation_id in seen_ids:
            raise ReviewValidationError(f"{context} id is malformed or duplicated")
        seen_ids.add(recommendation_id)
        title = require_text(recommendation["title"], context=f"{context}.title", maximum=180)
        rationale = require_text(
            recommendation["rationale"], context=f"{context}.rationale", maximum=1600
        )
        reject_unsafe_text(title, context=f"{context}.title")
        reject_unsafe_text(rationale, context=f"{context}.rationale")

        handles = recommendation["source_handles"]
        if (
            not isinstance(handles, list)
            or not 1 <= len(handles) <= 12
            or len(handles) != len(set(map(str, handles)))
        ):
            raise ReviewValidationError(f"{context}.source_handles is invalid")
        normalized_handles = [str(handle) for handle in handles]
        if any(not HANDLE.fullmatch(handle) or handle not in allowed_handles for handle in normalized_handles):
            raise ReviewValidationError(f"{context} cites an unknown source handle")

        repository = str(recommendation["target_repository"])
        scope = str(recommendation["scope"])
        risk = str(recommendation["risk"])
        if repository not in ALLOWED_REPOSITORIES:
            raise ReviewValidationError(f"{context}.target_repository is not allowed")
        if scope not in ALLOWED_SCOPES or risk not in ALLOWED_RISKS:
            raise ReviewValidationError(f"{context} scope or risk is not allowed")

        verification = recommendation["verification"]
        if not isinstance(verification, list) or not 1 <= len(verification) <= 12:
            raise ReviewValidationError(f"{context}.verification is invalid")
        normalized_verification: list[str] = []
        for item_index, item in enumerate(verification):
            text = require_text(
                item,
                context=f"{context}.verification[{item_index}]",
                maximum=300,
            )
            reject_unsafe_text(text, context=f"{context}.verification[{item_index}]")
            normalized_verification.append(text)

        claims = recommendation["claims"]
        expected_claims = {
            "execution_performed": False,
            "weights_trained": False,
            "claim_promoted": False,
            "private_graph_used": False,
            "human_review_required": True,
        }
        if claims != expected_claims:
            raise ReviewValidationError(f"{context}.claims escaped the proposal boundary")

        normalized.append(
            {
                "id": recommendation_id,
                "title": title,
                "rationale": rationale,
                "source_handles": normalized_handles,
                "target_repository": repository,
                "scope": scope,
                "risk": risk,
                "verification": normalized_verification,
                "claims": expected_claims,
            }
        )

    normalized_review = {
        "schema": SCHEMA,
        "candidate_set_sha256": candidate_set,
        "state": STATE,
        "summary": summary,
        "recommendations": normalized,
        "authority": expected_authority,
    }
    source = input_payload.get("source") or {}
    receipt: dict[str, Any] = {
        "schema": "szl.ouroboros.codex-frontier-review-receipt/v1",
        "state": "VERIFIED_REVIEW_PROPOSAL",
        "source_repository": source.get("repository"),
        "source_revision": source.get("revision"),
        "candidate_set_sha256": candidate_set,
        "input_sha256": input_payload.get("input_sha256"),
        "review_sha256": sha256_bytes(canonical_bytes(normalized_review)),
        "recommendation_count": len(normalized),
        "cited_handle_count": len(
            {handle for recommendation in normalized for handle in recommendation["source_handles"]}
        ),
        "authority": expected_authority,
        "claims": {
            "model_output_is_analysis_not_execution": True,
            "human_review_required": True,
            "weights_trained": False,
            "claim_promoted": False,
            "private_graph_used": False,
        },
        "loop": [
            {"sequence": 1, "stage": "OBSERVE", "state": "EXACT_SOURCE_SNAPSHOT"},
            {"sequence": 2, "stage": "ORIENT", "state": "FIXED_AUTHORITY_BOUNDARY"},
            {"sequence": 3, "stage": "PROPOSE", "state": "CODEX_REVIEW_OUTPUT"},
            {"sequence": 4, "stage": "VERIFY", "state": "DETERMINISTIC_SCHEMA_AND_HANDLE_REPLAY"},
            {"sequence": 5, "stage": "HOLD", "state": "HUMAN_REVIEW_REQUIRED"},
        ],
    }
    previous = "0" * 64
    for step in receipt["loop"]:
        step["previous_sha256"] = previous
        step["step_sha256"] = sha256_bytes(
            canonical_bytes({key: value for key, value in step.items() if key != "step_sha256"})
        )
        previous = step["step_sha256"]
    receipt["loop_head_sha256"] = previous
    receipt["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))
    return normalized_review, receipt


def render_issue(review: dict[str, Any], receipt: dict[str, Any]) -> str:
    lines = [
        "## SZL Ouroboros · Codex frontier review",
        "",
        f"**State:** `{review['state']}`",
        f"**Candidate set:** `{review['candidate_set_sha256']}`",
        f"**Review receipt:** `{receipt['receipt_sha256']}`",
        f"**Loop head:** `{receipt['loop_head_sha256']}`",
        "",
        review["summary"],
        "",
    ]
    if not review["recommendations"]:
        lines.extend(
            [
                "No bounded recommendation met the evidence threshold in this pass.",
                "",
            ]
        )
    for recommendation in review["recommendations"]:
        lines.extend(
            [
                f"### {recommendation['id']} · {recommendation['title']}",
                "",
                f"- Target: `{recommendation['target_repository']}`",
                f"- Scope: `{recommendation['scope']}`",
                f"- Risk: `{recommendation['risk']}`",
                f"- Evidence handles: `{', '.join(recommendation['source_handles'])}`",
                "",
                recommendation["rationale"],
                "",
                "**Verification**",
            ]
        )
        lines.extend(f"- {item}" for item in recommendation["verification"])
        lines.append("")
    lines.extend(
        [
            "### Authority boundary",
            "",
            "This record is a review proposal. Codex did not edit code, execute tools, merge, deploy, mutate a provider, train weights, promote a claim, or use the private graph. Human review remains required.",
            "",
            "Lambda remains Conjecture 1. The locked-proven formula count remains exactly eight.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--issue-body", type=Path, required=True)
    args = parser.parse_args()
    input_payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(input_payload, dict):
        raise ReviewValidationError("frontier input must be an object")
    review = parse_json_result(args.result.read_text(encoding="utf-8"))
    normalized, receipt = validate(input_payload, review)
    atomic_write(
        args.normalized,
        (json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    atomic_write(
        args.receipt,
        (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    atomic_write(args.issue_body, render_issue(normalized, receipt).encode("utf-8"))
    print(
        json.dumps(
            {
                "state": receipt["state"],
                "recommendation_count": receipt["recommendation_count"],
                "review_sha256": receipt["review_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
