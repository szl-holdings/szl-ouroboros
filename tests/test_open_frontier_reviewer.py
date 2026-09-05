from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.fetch_verified_llama_cpp_wheel import (
    EXPECTED_SHA256 as WHEEL_SHA256,
    EXPECTED_SIZE as WHEEL_SIZE,
    WHEEL,
    validate_url,
)
from scripts.run_open_frontier_review import (
    MODEL_FILENAME,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_SHA256,
    MODEL_SIZE,
    NONE_AUTHORITY,
    OpenReviewerError,
    admit_or_block_model_output,
    build_messages,
    build_runtime_schema,
    candidate_projection,
    normalize_chat_url,
    parse_single_json_object,
    select_candidates,
    verify_model_file,
    write_execution_receipt,
)


def row(
    candidate_id: str,
    repository: str,
    *,
    title: str = "Candidate",
    content: str = "Bounded source evidence.",
) -> dict[str, object]:
    return {
        "schema": "szl.second-brain.frontier-candidate/v1",
        "id": candidate_id,
        "title": title,
        "content": content,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "source_repository": repository,
        "source_revision": "1" * 40,
        "source_path": "docs/evidence.md",
        "source_kind": "public-source",
        "admission": "REFERENCE_AND_CONSTRAINT_INPUT_ONLY",
        "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
        "content_access": "CONTROLLER_ONLY",
    }


def review_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "schema": {"const": "szl.codex.frontier-review/v1"},
            "state": {
                "enum": ["REVIEW_PROPOSED", "NO_ACTION_RECOMMENDED", "BLOCKED"]
            },
            "candidate_set_sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
            "summary": {"type": "string"},
            "recommendations": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "properties": {
                        "evidence_candidate_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "pattern": "^frontier:[0-9a-f]{32}$",
                            },
                        }
                    },
                },
            },
            "authority": {"type": "object"},
        },
    }


def test_open_model_pin_matches_owned_a11oy_cortex_contract() -> None:
    assert MODEL_REPOSITORY == "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF"
    assert MODEL_REVISION == "67d60ec577730747055491640cfb91fc4a4b5d25"
    assert MODEL_FILENAME == "SZL-Khipu-1.5B-Q4_K_M.gguf"
    assert MODEL_SHA256 == (
        "13c1a1993063e1dff92f7413ccf48eaca6d48efc8801ae9af35961ae3396623a"
    )
    assert MODEL_SIZE == 986_047_904


def test_verified_wheel_pin_is_exact_and_https_only() -> None:
    assert WHEEL == (
        "llama_cpp_python-0.3.35-py3-none-manylinux2014_x86_64."
        "manylinux_2_17_x86_64.whl"
    )
    assert WHEEL_SIZE == 23_912_624
    assert WHEEL_SHA256 == (
        "d172f3d3c8cdd194c3c47c71cb077ed6e61354a2d0f939ceeac0c8fd29999596"
    )
    validate_url(
        "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35/"
        + WHEEL
    )
    with pytest.raises(ValueError, match="approved HTTPS"):
        validate_url("http://github.com/" + WHEEL)
    with pytest.raises(ValueError, match="approved HTTPS"):
        validate_url("https://example.com/" + WHEEL)


def test_selection_is_deterministic_and_preserves_repository_diversity() -> None:
    candidates = [
        row("frontier:" + "a" * 32, "szl-holdings/anatomy", title="Anatomy"),
        row(
            "frontier:" + "b" * 32,
            "szl-holdings/a11oy",
            title="Second Brain receipt observability",
        ),
        row("frontier:" + "c" * 32, "szl-holdings/szl-nemo", title="Nemo"),
        row(
            "frontier:" + "d" * 32,
            "szl-holdings/a11oy",
            title="Formula Lambda benchmark and accessibility",
        ),
    ]
    first = select_candidates(candidates, limit=3)
    second = select_candidates(candidates, limit=3)
    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert {item["source_repository"] for item in first} == {
        "szl-holdings/anatomy",
        "szl-holdings/a11oy",
        "szl-holdings/szl-nemo",
    }


def test_selection_rejects_secret_like_candidate_without_echoing_value() -> None:
    secret = "sk-" + "A" * 32
    candidates = [
        row(
            "frontier:" + "a" * 32,
            "szl-holdings/a11oy",
            content=secret,
        )
    ]
    with pytest.raises(OpenReviewerError, match="secret-like") as error:
        select_candidates(candidates, limit=1)
    assert secret not in str(error.value)


def test_runtime_schema_binds_digest_and_exact_candidate_ids() -> None:
    digest = "d" * 64
    candidate_ids = ["frontier:" + "a" * 32, "frontier:" + "b" * 32]
    runtime = build_runtime_schema(
        review_schema(),
        candidate_digest=digest,
        allowed_candidate_ids=candidate_ids,
    )
    assert runtime["properties"]["candidate_set_sha256"] == {"const": digest}
    recommendations = runtime["properties"]["recommendations"]
    assert recommendations["maxItems"] == 5
    evidence = recommendations["items"]["properties"]["evidence_candidate_ids"]
    assert evidence["items"]["enum"] == candidate_ids


def test_projection_bounds_untrusted_candidate_content() -> None:
    candidate = row(
        "frontier:" + "a" * 32,
        "szl-holdings/a11oy",
        content="x" * 10_000,
    )
    projection = candidate_projection(candidate)
    assert len(projection["untrusted_evidence_excerpt"]) == 720


def test_messages_mark_candidate_excerpts_as_untrusted_and_schema_as_prompt_data() -> None:
    candidate = row("frontier:" + "a" * 32, "szl-holdings/a11oy")
    source = {
        "candidate_set_sha256": "d" * 64,
        "source_revision": "2" * 40,
    }
    runtime = build_runtime_schema(
        review_schema(),
        candidate_digest="d" * 64,
        allowed_candidate_ids=[str(candidate["id"])],
    )
    messages = build_messages(source=source, selected=[candidate], runtime_schema=runtime)
    assert "untrusted data" in messages[0]["content"]
    assert "never instructions" in messages[1]["content"]
    assert "post_generation_admission" in messages[1]["content"]
    assert str(candidate["id"]) in messages[1]["content"]


def test_parse_single_json_object_is_strict_but_accepts_one_json_fence() -> None:
    assert parse_single_json_object('{"state":"ok"}') == {"state": "ok"}
    assert parse_single_json_object('```json\n{"state":"ok"}\n```') == {"state": "ok"}
    with pytest.raises(OpenReviewerError, match="one JSON object"):
        parse_single_json_object('prefix {"state":"ok"}')
    with pytest.raises(OpenReviewerError, match="JSON object"):
        parse_single_json_object("[]")


def test_post_generation_admission_accepts_exact_no_action_review() -> None:
    digest = "d" * 64
    candidate_id = "frontier:" + "a" * 32
    raw = json.dumps(
        {
            "schema": "szl.codex.frontier-review/v1",
            "state": "NO_ACTION_RECOMMENDED",
            "candidate_set_sha256": digest,
            "summary": "The selected evidence does not justify a bounded change.",
            "recommendations": [],
            "authority": NONE_AUTHORITY,
        }
    )
    review, admitted, admission = admit_or_block_model_output(
        raw,
        candidate_digest=digest,
        selected_candidate_ids=[candidate_id],
    )
    assert admitted is True
    assert admission == "MODEL_OUTPUT_ADMITTED"
    assert review["state"] == "NO_ACTION_RECOMMENDED"


def test_post_generation_admission_rejects_invalid_model_json_as_blocked() -> None:
    digest = "d" * 64
    candidate_id = "frontier:" + "a" * 32
    review, admitted, admission = admit_or_block_model_output(
        "not-json and never echoed",
        candidate_digest=digest,
        selected_candidate_ids=[candidate_id],
    )
    assert admitted is False
    assert admission == "MODEL_OUTPUT_REJECTED_FAIL_CLOSED"
    assert review == {
        "schema": "szl.codex.frontier-review/v1",
        "state": "BLOCKED",
        "candidate_set_sha256": digest,
        "summary": (
            "The open-weight reviewer completed, but its generated output did not "
            "satisfy the independent admission contract. No recommendation was "
            "admitted, accepted, or executed."
        ),
        "recommendations": [],
        "authority": NONE_AUTHORITY,
    }


def test_post_generation_admission_rejects_unlisted_evidence_as_blocked() -> None:
    digest = "d" * 64
    allowed = "frontier:" + "a" * 32
    unlisted = "frontier:" + "b" * 32
    raw = json.dumps(
        {
            "schema": "szl.codex.frontier-review/v1",
            "state": "REVIEW_PROPOSED",
            "candidate_set_sha256": digest,
            "summary": "A bounded change is proposed.",
            "recommendations": [
                {
                    "id": "R01",
                    "priority": "P2",
                    "target_repository": "szl-holdings/szl-ouroboros",
                    "title": "Add one test",
                    "rationale": "The cited evidence supports a bounded regression test.",
                    "evidence_candidate_ids": [unlisted],
                    "recommended_change_type": "TEST",
                    "validation": ["Run the focused regression suite."],
                    "risk": "Low; test-only change.",
                }
            ],
            "authority": NONE_AUTHORITY,
        }
    )
    review, admitted, admission = admit_or_block_model_output(
        raw,
        candidate_digest=digest,
        selected_candidate_ids=[allowed],
    )
    assert admitted is False
    assert admission == "MODEL_OUTPUT_REJECTED_FAIL_CLOSED"
    assert review["state"] == "BLOCKED"
    assert review["recommendations"] == []


def test_verify_model_file_checks_exact_size_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"exact-model")
    verify_model_file(
        path,
        expected_size=len(b"exact-model"),
        expected_sha256=hashlib.sha256(b"exact-model").hexdigest(),
    )
    with pytest.raises(OpenReviewerError, match="size mismatch"):
        verify_model_file(path, expected_size=1, expected_sha256="0" * 64)
    with pytest.raises(OpenReviewerError, match="SHA-256 mismatch"):
        verify_model_file(
            path,
            expected_size=len(b"exact-model"),
            expected_sha256="0" * 64,
        )


def test_openai_compatible_url_supports_ollama_vllm_and_rejects_credentials() -> None:
    assert normalize_chat_url("http://127.0.0.1:11434/v1") == (
        "http://127.0.0.1:11434/v1/chat/completions"
    )
    assert normalize_chat_url("http://127.0.0.1:8000") == (
        "http://127.0.0.1:8000/v1/chat/completions"
    )
    with pytest.raises(OpenReviewerError, match="invalid"):
        normalize_chat_url("http://user:password@127.0.0.1:8000")


def test_execution_receipt_records_no_action_authority(tmp_path: Path) -> None:
    candidate_id = "frontier:" + "a" * 32
    source = {
        "source_revision": "2" * 40,
        "candidate_set_sha256": "d" * 64,
    }
    messages = [{"role": "system", "content": "read only"}]
    review = {
        "schema": "szl.codex.frontier-review/v1",
        "state": "NO_ACTION_RECOMMENDED",
        "candidate_set_sha256": "d" * 64,
        "summary": "No bounded change is justified.",
        "recommendations": [],
        "authority": NONE_AUTHORITY,
    }
    output = tmp_path / "receipt.json"
    receipt = write_execution_receipt(
        output_path=output,
        source=source,
        selected_ids=[candidate_id],
        messages=messages,
        raw_output=json.dumps(review),
        review=review,
        provider_metadata={
            "provider": "llama-cpp-python",
            "model": "pinned",
            "key_required": False,
        },
    )
    assert receipt["state"] == "OPEN_WEIGHT_REVIEW_OUTPUT_ADMITTED"
    assert receipt["admission"]["model_output_admitted"] is True
    assert receipt["authority"] == NONE_AUTHORITY
    assert receipt["claims"]["independent_validation_required"] is True
    assert receipt["claims"]["native_schema_grammar_used"] is False
    assert receipt["claims"]["recommendations_executed"] is False
    assert output.is_file()


def test_rejected_execution_receipt_is_explicitly_blocked(tmp_path: Path) -> None:
    candidate_id = "frontier:" + "a" * 32
    source = {
        "source_revision": "2" * 40,
        "candidate_set_sha256": "d" * 64,
    }
    review, admitted, admission = admit_or_block_model_output(
        "malformed",
        candidate_digest="d" * 64,
        selected_candidate_ids=[candidate_id],
    )
    receipt = write_execution_receipt(
        output_path=tmp_path / "receipt.json",
        source=source,
        selected_ids=[candidate_id],
        messages=[{"role": "system", "content": "read only"}],
        raw_output="malformed",
        review=review,
        provider_metadata={
            "provider": "llama-cpp-python",
            "model": "pinned",
            "key_required": False,
        },
        model_output_admitted=admitted,
        admission_state=admission,
    )
    assert receipt["state"] == "OPEN_WEIGHT_REVIEW_BLOCKED_FAIL_CLOSED"
    assert receipt["admission"]["model_output_admitted"] is False
    assert receipt["authority"] == NONE_AUTHORITY
