from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.finalize_codex_frontier_review import ReviewError, finalize
from scripts.prepare_codex_frontier_review import PacketError, validate_packet


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def candidate(candidate_id: str = "frontier:" + "a" * 32) -> dict[str, object]:
    content = "Formula review candidate with Lambda retained as Conjecture 1."
    return {
        "schema": "szl.second-brain.frontier-candidate/v1",
        "id": candidate_id,
        "title": "Formula boundary",
        "content": content,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "source_repository": "szl-holdings/szl-formulas",
        "source_revision": "1" * 40,
        "source_path": "atlas/formula-atlas.v1.json",
        "source_kind": "formula-authority",
        "admission": "REFERENCE_AND_CONSTRAINT_INPUT_ONLY",
        "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
        "content_access": "CONTROLLER_ONLY",
    }


def packet_bytes() -> tuple[bytes, bytes, str]:
    row = candidate()
    candidates = canonical_bytes(row) + b"\n"
    digest = hashlib.sha256(candidates).hexdigest()
    state = {
        "schema": "szl.second-brain.frontier-state/v1",
        "state": "REVIEW_REQUIRED",
        "candidate_count": 1,
        "candidate_set_sha256": digest,
        "source_count": 6,
        "public_content_access": "HANDLES_ONLY",
        "controller_content_access": "AUTHORIZED_CONTROLLER_ONLY",
        "private_graph_nodes_loaded": 0,
        "raw_graph_nodes_admitted_to_gradients": 0,
        "training_authority": "NONE",
        "promotion_authority": "NONE",
        "execution_authority": "NONE",
        "merge_authority": "NONE",
        "lambda": "CONJECTURE_1",
        "state_sha256": "b" * 64,
    }
    return json.dumps(state).encode(), candidates, digest


def write_finalize_fixture(root: Path) -> tuple[Path, Path, Path, str]:
    state_raw, candidates_raw, digest = packet_bytes()
    _ = state_raw
    candidates = root / "frontier-candidates.public.jsonl"
    candidates.write_bytes(candidates_raw)
    source = root / "source-receipt.json"
    source.write_text(
        json.dumps(
            {
                "schema": "szl.ouroboros.codex-frontier-source/v1",
                "source_repository": "szl-holdings/szl-second-brain",
                "source_ref": "main",
                "source_revision": "2" * 40,
                "state_path": "data/frontier-state.v1.json",
                "state_sha256": "3" * 64,
                "candidates_path": "data/frontier-candidates.public.jsonl",
                "candidates_sha256": hashlib.sha256(candidates_raw).hexdigest(),
                "candidate_count": 1,
                "candidate_set_sha256": digest,
                "source_count": 6,
                "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
                "content_scope": "PUBLIC_SOURCE_REVIEW_MATERIAL",
                "authority": {
                    "training": "NONE",
                    "promotion": "NONE",
                    "execution": "NONE",
                    "merge": "NONE",
                    "provider_mutation": "NONE",
                },
                "receipt_sha256": "4" * 64,
            }
        ),
        encoding="utf-8",
    )
    review = root / "review.json"
    return source, candidates, review, digest


def test_prepare_validates_exact_candidate_digest_and_authority() -> None:
    state_raw, candidates_raw, digest = packet_bytes()
    state, rows = validate_packet(state_raw, candidates_raw)
    assert state["candidate_set_sha256"] == digest
    assert rows == [candidate()]


def test_prepare_rejects_candidate_promotion() -> None:
    state_raw, _candidates_raw, _digest = packet_bytes()
    row = candidate()
    row["candidate_state"] = "ACCEPTED"
    candidates = canonical_bytes(row) + b"\n"
    state = json.loads(state_raw)
    state["candidate_set_sha256"] = hashlib.sha256(candidates).hexdigest()
    with pytest.raises(PacketError, match="promoted"):
        validate_packet(json.dumps(state).encode(), candidates)


def test_prepare_rejects_secret_like_candidate_without_echoing_it() -> None:
    state_raw, _candidates_raw, _digest = packet_bytes()
    row = candidate()
    secret = "sk-" + "A" * 32
    row["content"] = secret
    row["content_sha256"] = hashlib.sha256(secret.encode()).hexdigest()
    candidates = canonical_bytes(row) + b"\n"
    state = json.loads(state_raw)
    state["candidate_set_sha256"] = hashlib.sha256(candidates).hexdigest()
    with pytest.raises(PacketError, match="secret-like material") as error:
        validate_packet(json.dumps(state).encode(), candidates)
    assert secret not in str(error.value)


def test_finalize_accepts_evidence_bound_advisory_review(tmp_path: Path) -> None:
    source, candidates, review_path, digest = write_finalize_fixture(tmp_path)
    review_path.write_text(
        json.dumps(
            {
                "schema": "szl.codex.frontier-review/v1",
                "state": "REVIEW_PROPOSED",
                "candidate_set_sha256": digest,
                "summary": "Add a deterministic formula-boundary test.",
                "recommendations": [
                    {
                        "id": "R01",
                        "priority": "P1",
                        "target_repository": "szl-holdings/szl-second-brain",
                        "title": "Prove formula-boundary readback",
                        "rationale": "The cited candidate records the exact advisory boundary.",
                        "evidence_candidate_ids": ["frontier:" + "a" * 32],
                        "recommended_change_type": "TEST",
                        "validation": ["Run the focused source test."],
                        "risk": "A stale fixture could mask source drift.",
                    }
                ],
                "authority": {
                    "training": "NONE",
                    "promotion": "NONE",
                    "execution": "NONE",
                    "merge": "NONE",
                    "provider_mutation": "NONE",
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "loop-receipt.json"
    receipt = finalize(
        source_receipt_path=source,
        candidate_path=candidates,
        review_path=review_path,
        output_path=output,
        codex_attempted=True,
        codex_outcome="success",
        model="codex-default",
        latency_ms=1250.0,
        wall_ms=1500.0,
    )
    assert receipt["state"] == "REVIEW_PROPOSED"
    assert receipt["ouroboros"]["exit"] == "converged"
    assert receipt["ouroboros"]["withinBudget"] is True
    assert receipt["ouroboros"]["receiptsInEqOut"] is True
    assert receipt["ouroboros"]["modelMs"] == 1250.0
    assert receipt["ouroboros"]["overheadMs"] == 250.0
    assert receipt["codex"]["review_sha256"]
    assert receipt["claims"]["recommendations_executed"] is False
    assert receipt["authority"]["execution"] == "NONE"
    assert output.is_file()


def test_finalize_missing_key_is_explicit_and_receipt_closed(tmp_path: Path) -> None:
    source, candidates, review_path, _digest = write_finalize_fixture(tmp_path)
    output = tmp_path / "loop-receipt.json"
    receipt = finalize(
        source_receipt_path=source,
        candidate_path=candidates,
        review_path=review_path,
        output_path=output,
        codex_attempted=False,
        codex_outcome="not_attempted",
        model="codex-default",
        latency_ms=0.0,
        wall_ms=20.0,
    )
    assert receipt["state"] == "CODEX_UNAVAILABLE_MISSING_SECRET"
    assert receipt["codex"]["review"] is None
    assert receipt["ouroboros"]["exit"] == "aborted"
    assert receipt["ouroboros"]["withinBudget"] is True
    assert receipt["ouroboros"]["receiptsInEqOut"] is True
    assert receipt["authority"] == {
        "training": "NONE",
        "promotion": "NONE",
        "execution": "NONE",
        "merge": "NONE",
        "provider_mutation": "NONE",
    }


def test_finalize_rejects_unknown_evidence_candidate(tmp_path: Path) -> None:
    source, candidates, review_path, digest = write_finalize_fixture(tmp_path)
    review_path.write_text(
        json.dumps(
            {
                "schema": "szl.codex.frontier-review/v1",
                "state": "REVIEW_PROPOSED",
                "candidate_set_sha256": digest,
                "summary": "A bounded recommendation.",
                "recommendations": [
                    {
                        "id": "R01",
                        "priority": "P2",
                        "target_repository": "szl-holdings/anatomy",
                        "title": "Add an observation",
                        "rationale": "Use source-bound evidence only.",
                        "evidence_candidate_ids": ["frontier:" + "f" * 32],
                        "recommended_change_type": "OBSERVABILITY",
                        "validation": ["Run a deterministic test."],
                        "risk": "Unknown evidence must block the review.",
                    }
                ],
                "authority": {
                    "training": "NONE",
                    "promotion": "NONE",
                    "execution": "NONE",
                    "merge": "NONE",
                    "provider_mutation": "NONE",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReviewError, match="evidence binding"):
        finalize(
            source_receipt_path=source,
            candidate_path=candidates,
            review_path=review_path,
            output_path=tmp_path / "loop-receipt.json",
            codex_attempted=True,
            codex_outcome="success",
            model="codex-default",
            latency_ms=100.0,
            wall_ms=120.0,
        )


def test_finalize_rejects_mutation_authority(tmp_path: Path) -> None:
    source, candidates, review_path, digest = write_finalize_fixture(tmp_path)
    review_path.write_text(
        json.dumps(
            {
                "schema": "szl.codex.frontier-review/v1",
                "state": "NO_ACTION_RECOMMENDED",
                "candidate_set_sha256": digest,
                "summary": "No bounded change is justified by the current evidence.",
                "recommendations": [],
                "authority": {
                    "training": "NONE",
                    "promotion": "NONE",
                    "execution": "GRANTED",
                    "merge": "NONE",
                    "provider_mutation": "NONE",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReviewError, match="mutation authority"):
        finalize(
            source_receipt_path=source,
            candidate_path=candidates,
            review_path=review_path,
            output_path=tmp_path / "loop-receipt.json",
            codex_attempted=True,
            codex_outcome="success",
            model="codex-default",
            latency_ms=100.0,
            wall_ms=120.0,
        )
