from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.continuous_frontier_loop as loop


REVISION = "a" * 40
FORMULA_REVISION = "b" * 40


def _candidate(candidate_id: str = "frontier:" + "1" * 32) -> dict:
    content = "Second Brain and Living Anatomy share a source-bound formula handle."
    return {
        "schema": "szl.second-brain.frontier-candidate/v1",
        "id": candidate_id,
        "title": "Source-bound Anatomy formula handle",
        "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "source_repository": "szl-holdings/szl-second-brain",
        "source_revision": REVISION,
        "source_path": "data/example.json",
        "source_kind": "source-document",
        "admission": "DISCOVERED_REVIEW_REQUIRED",
        "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
        "content_access": "CONTROLLER_ONLY",
    }


def _candidate_bytes(rows: list[dict]) -> bytes:
    return b"".join(loop.canonical_bytes(row) + b"\n" for row in rows)


def _context(rows: list[dict]) -> dict:
    candidate_digest = loop.candidate_set_digest(rows)
    value = {
        "schema": "szl.ouroboros.continuous-frontier-context/v1",
        "second_brain": {
            "candidate_set_sha256": candidate_digest,
            "candidate_count": len(rows),
        },
        "authority": dict(loop.AUTHORITY),
    }
    value["context_sha256"] = loop.sha256_bytes(loop.canonical_bytes(value))
    return value


def _proposal(context: dict, candidate_id: str) -> dict:
    return {
        "schema": "szl.ouroboros.codex-frontier-proposal/v1",
        "state": "PROPOSAL",
        "candidate_set_sha256": context["second_brain"]["candidate_set_sha256"],
        "context_sha256": context["context_sha256"],
        "cycles": [
            {
                "cycle": 1,
                "observation": "Anatomy needs a same-origin handle feed.",
                "hypothesis": "Expose the already bounded frontier handles.",
                "challenge": "A duplicate authority surface would be unsafe.",
                "revision": "Add a read-only visualization adapter only.",
                "evidence_handles": [candidate_id],
            }
        ],
        "convergence": {
            "state": "CONVERGED_TO_REVIEW_PROPOSAL",
            "stopping_reason": "One source-owned adapter is the smallest testable delta.",
        },
        "recommendation": {
            "title": "Render Second Brain handles in Living Anatomy",
            "problem": "The source-bound feed is not visible in the holographic organ.",
            "smallest_safe_change": "Add one read-only same-origin adapter and UI panel.",
            "target_repository": "szl-holdings/anatomy",
            "target_paths": ["second_brain_runtime.py", "frontier_anatomy.js"],
            "acceptance_tests": [
                "Public response contains handles and digests but no content field."
            ],
            "risks": ["A stale source revision must remain visibly unavailable."],
        },
        "authority": dict(loop.AUTHORITY),
    }


def test_parse_candidate_lines_replays_content_digest_and_boundaries() -> None:
    rows = [_candidate()]
    parsed = loop.parse_candidate_lines(_candidate_bytes(rows))
    assert parsed == rows
    assert loop.candidate_set_digest(parsed) == hashlib.sha256(
        _candidate_bytes(rows)
    ).hexdigest()


def test_parse_candidate_lines_fails_closed_on_content_tamper() -> None:
    row = _candidate()
    row["content"] += " tampered"
    with pytest.raises(loop.LoopBoundaryError, match="digest does not replay"):
        loop.parse_candidate_lines(_candidate_bytes([row]))


def test_validate_output_accepts_only_known_handles_and_zero_authority() -> None:
    rows = [_candidate()]
    context = _context(rows)
    validated = loop.validate_output(_proposal(context, rows[0]["id"]), context, rows)
    assert validated["state"] == "PROPOSAL"
    assert len(validated["proposal_sha256"]) == 64
    assert validated["authority"] == loop.AUTHORITY
    assert validated["recommendation"]["target_repository"] == "szl-holdings/anatomy"


def test_validate_output_rejects_unknown_handle() -> None:
    rows = [_candidate()]
    context = _context(rows)
    proposal = _proposal(context, "frontier:" + "9" * 32)
    with pytest.raises(loop.LoopBoundaryError, match="unknown evidence handle"):
        loop.validate_output(proposal, context, rows)


def test_validate_output_rejects_authority_escalation() -> None:
    rows = [_candidate()]
    context = _context(rows)
    proposal = _proposal(context, rows[0]["id"])
    proposal["authority"]["merge"] = "AUTOMATIC"
    with pytest.raises(loop.LoopBoundaryError, match="authority boundary drifted"):
        loop.validate_output(proposal, context, rows)


def test_validate_output_rejects_secret_like_text_without_echoing_it() -> None:
    rows = [_candidate()]
    context = _context(rows)
    proposal = _proposal(context, rows[0]["id"])
    secret = "sk-" + "X" * 32
    proposal["recommendation"]["problem"] = "credential=" + secret
    with pytest.raises(loop.LoopBoundaryError, match="secret-like material rejected") as error:
        loop.validate_output(proposal, context, rows)
    assert secret not in str(error.value)


def test_build_context_binds_exact_second_brain_and_formula_revisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_candidate()]
    candidates_raw = _candidate_bytes(rows)
    candidate_digest = loop.candidate_set_digest(rows)
    state = {
        "schema": "szl.second-brain.frontier-state/v1",
        "state": "REVIEW_REQUIRED",
        "candidate_set_sha256": candidate_digest,
        "training_authority": "NONE",
        "promotion_authority": "NONE",
        "execution_authority": "NONE",
    }
    formula = {
        "schema": "szl.formula-quant-atlas/v1",
        "summary": {
            "attributed_formula_count": 30,
            "executable_formula_count": 21,
            "quant_domain_counts": {"trust_aggregation": 5},
        },
        "authority": {
            "locked_proven_count": 8,
            "locked_proven_ids": ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"],
            "lambda_status": "CONJECTURE_1_OPEN_ADVISORY_ONLY",
        },
    }

    def fake_fetch(repository: str, path: str, **_kwargs):
        if repository == loop.SECOND_BRAIN_REPOSITORY and path == loop.SECOND_BRAIN_STATE_PATH:
            return REVISION, json.dumps(state).encode("utf-8")
        if repository == loop.SECOND_BRAIN_REPOSITORY and path == loop.SECOND_BRAIN_CANDIDATES_PATH:
            return REVISION, candidates_raw
        if repository == loop.FORMULA_REPOSITORY and path == loop.FORMULA_PATH:
            return FORMULA_REVISION, json.dumps(formula).encode("utf-8")
        raise AssertionError((repository, path))

    monkeypatch.setattr(loop, "fetch_immutable_source", fake_fetch)
    monkeypatch.setattr(
        loop,
        "inspect_local_kernel",
        lambda: {"state": "LOADED", "selfcheck_state": "COMPLETED"},
    )
    context, observed_rows = loop.build_context(
        token=None,
        anatomy_observer=lambda: [
            {"path": "/api/anatomy/v1/living-health", "state": "REACHABLE"}
        ],
    )
    assert observed_rows == rows
    assert context["state"] == "READY_FOR_READ_ONLY_CODEX_REVIEW"
    assert context["second_brain"]["revision"] == REVISION
    assert context["second_brain"]["candidate_set_sha256"] == candidate_digest
    assert context["formula_quant_atlas"]["revision"] == FORMULA_REVISION
    assert context["formula_quant_atlas"]["summary"]["attributed_formula_count"] == 30
    assert context["formula_quant_atlas"]["authority"]["locked_proven_count"] == 8
    assert context["authority"] == loop.AUTHORITY
    assert len(context["context_sha256"]) == 64


def test_write_blocked_is_an_honest_terminal_receipt(tmp_path: Path) -> None:
    rows = [_candidate()]
    context = _context(rows)
    proposal_path = tmp_path / "proposal.json"
    receipt_path = tmp_path / "receipt.json"
    loop.write_blocked(
        context,
        proposal_path=proposal_path,
        receipt_path=receipt_path,
        reason="CODEX_SECRET_UNAVAILABLE",
        run_id="123",
        run_attempt=2,
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert proposal["state"] == "BLOCKED"
    assert proposal["cycles"] == []
    assert receipt["state"] == "BLOCKED"
    assert receipt["codex_output_validated"] is True
    assert receipt["automatic_merge_performed"] is False
    assert receipt["production_execution_performed"] is False
