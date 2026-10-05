from __future__ import annotations

import hashlib
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

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
    build_compact_generation_grammar,
    build_messages,
    build_runtime_schema,
    candidate_projection,
    normalize_chat_url,
    parse_single_json_object,
    run_local_gguf,
    run_openai_compatible,
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
    path = Path(__file__).resolve().parents[1] / "schemas/codex-frontier-review.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


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
    assert len(first) == 3
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
    assert recommendations["maxItems"] == 1
    evidence = recommendations["items"]["properties"]["evidence_candidate_ids"]
    assert evidence["items"]["enum"] == candidate_ids


def test_selection_never_exceeds_a_budget_smaller_than_the_source_count() -> None:
    candidates = [row(f"frontier:{index:032x}", f"szl-holdings/repo-{index}") for index in range(10)]
    for limit in (1, 6, 10):
        assert len(select_candidates(candidates, limit=limit)) == limit
    with pytest.raises(OpenReviewerError):
        select_candidates(candidates, limit=True)


def proposed_review() -> dict:
    return {
        "schema": "szl.codex.frontier-review/v1",
        "state": "REVIEW_PROPOSED",
        "candidate_set_sha256": "d" * 64,
        "summary": "Review one source-bound integration test.",
        "recommendations": [{
            "id": "R01", "priority": "P2", "target_repository": "szl-holdings/a11oy",
            "title": "Test the public evidence binding",
            "rationale": "The selected receipt identifies a checkable interface contract.",
            "evidence_candidate_ids": ["frontier:" + "a" * 32],
            "recommended_change_type": "TEST",
            "validation": ["Verify the exact source digest and expected rejection."],
            "risk": "A local test does not prove a live deployment.",
        }],
        "authority": dict(NONE_AUTHORITY),
    }


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(summary="x" * 121),
    lambda value: value["recommendations"].append({**value["recommendations"][0], "id": "R02"}),
    lambda value: value["recommendations"][0].update(title="x" * 81),
    lambda value: value["recommendations"][0].update(rationale="x" * 241),
    lambda value: value["recommendations"][0].update(risk="x" * 121),
    lambda value: value["recommendations"][0].update(validation=["one", "two", "three"]),
    lambda value: value["recommendations"][0].update(validation=["x" * 121]),
    lambda value: value["recommendations"][0].update(evidence_candidate_ids=["frontier:" + char * 32 for char in "abc"]),
])
def test_global_schema_compliance_cannot_bypass_the_compact_output_budget(mutation) -> None:
    value = copy.deepcopy(proposed_review())
    mutation(value)
    review, admitted, _, failure = admit_or_block_model_output(
        json.dumps(value), candidate_digest="d" * 64,
        selected_candidate_ids=["frontier:" + char * 32 for char in "abc"],
    )
    assert admitted is False
    assert failure == "OUTPUT_BUDGET_CONTRACT"
    assert review["recommendations"] == []


def test_compact_review_counts_utf8_bytes_and_preserves_a_valid_small_review() -> None:
    value = proposed_review()
    assert admit_or_block_model_output(
        json.dumps(value), candidate_digest="d" * 64,
        selected_candidate_ids=["frontier:" + "a" * 32],
    )[1] is True
    value["summary"] = "\U0001f9ea" * 120
    value["recommendations"][0].update(title="\U0001f9ea" * 80, rationale="\U0001f9ea" * 240,
                                           risk="\U0001f9ea" * 120, validation=["\U0001f9ea" * 120] * 2)
    review, admitted, _, failure = admit_or_block_model_output(
        json.dumps(value), candidate_digest="d" * 64,
        selected_candidate_ids=["frontier:" + "a" * 32],
    )
    assert admitted is False
    assert failure == "OUTPUT_BUDGET_CONTRACT"
    assert review["recommendations"] == []


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
    review, admitted, admission, failure_code = admit_or_block_model_output(
        raw,
        candidate_digest=digest,
        selected_candidate_ids=[candidate_id],
    )
    assert admitted is True
    assert admission == "MODEL_OUTPUT_ADMITTED"
    assert failure_code is None
    assert review["state"] == "NO_ACTION_RECOMMENDED"


@pytest.mark.parametrize(
    ("finish_reason", "expected_code"),
    [("length", "OUTPUT_TRUNCATED"), (None, "COMPLETION_NOT_STOPPED")],
)
def test_post_generation_admission_rejects_incomplete_completion(
    finish_reason: str | None,
    expected_code: str,
) -> None:
    digest = "d" * 64
    candidate_id = "frontier:" + "a" * 32
    valid_json = json.dumps(
        {
            "schema": "szl.codex.frontier-review/v1",
            "state": "NO_ACTION_RECOMMENDED",
            "candidate_set_sha256": digest,
            "summary": "No bounded change is justified.",
            "recommendations": [],
            "authority": NONE_AUTHORITY,
        }
    )
    review, admitted, admission, failure_code = admit_or_block_model_output(
        valid_json,
        candidate_digest=digest,
        selected_candidate_ids=[candidate_id],
        finish_reason=finish_reason,
    )
    assert admitted is False
    assert admission == "MODEL_OUTPUT_REJECTED_FAIL_CLOSED"
    assert failure_code == expected_code
    assert review["state"] == "BLOCKED"
    assert review["recommendations"] == []


def test_post_generation_admission_rejects_invalid_model_json_as_blocked() -> None:
    digest = "d" * 64
    candidate_id = "frontier:" + "a" * 32
    review, admitted, admission, failure_code = admit_or_block_model_output(
        "not-json and never echoed",
        candidate_digest=digest,
        selected_candidate_ids=[candidate_id],
    )
    assert admitted is False
    assert admission == "MODEL_OUTPUT_REJECTED_FAIL_CLOSED"
    assert failure_code == "OUTPUT_NOT_SINGLE_JSON_OBJECT"
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
    review, admitted, admission, failure_code = admit_or_block_model_output(
        raw,
        candidate_digest=digest,
        selected_candidate_ids=[allowed],
    )
    assert admitted is False
    assert admission == "MODEL_OUTPUT_REJECTED_FAIL_CLOSED"
    assert failure_code == "EVIDENCE_BINDING"
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


def test_local_gguf_uses_bounded_grammar_without_response_format_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeGrammar:
        @classmethod
        def from_string(cls, value: str, *, verbose: bool):
            calls["grammar_text"] = value
            assert verbose is False
            return cls()

    class FakeLlama:
        def __init__(self, **kwargs: object) -> None:
            calls["init"] = kwargs

        def create_chat_completion(self, **kwargs: object) -> dict[str, object]:
            calls["completion"] = kwargs
            return {
                "choices": [
                    {
                        "message": {"content": '{"state":"NO_ACTION_RECOMMENDED"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            }

    fake_module = ModuleType("llama_cpp")
    fake_module.Llama = FakeLlama
    fake_module.LlamaGrammar = FakeGrammar
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_module)
    content, metadata = run_local_gguf(
        messages=[{"role": "user", "content": "Return JSON."}],
        runtime_schema=build_runtime_schema(
            review_schema(), candidate_digest="d" * 64,
            allowed_candidate_ids=["frontier:" + "a" * 32],
        ),
        model_path=Path("pinned.gguf"),
        max_tokens=1800,
        context_tokens=16384,
        seed=749,
    )
    assert content == '{"state":"NO_ACTION_RECOMMENDED"}'
    assert "response_format" not in calls["completion"]
    assert isinstance(calls["completion"]["grammar"], FakeGrammar)
    assert calls["completion"]["max_tokens"] == 1800
    assert calls["completion"]["temperature"] == 0.0
    assert calls["completion"]["seed"] == 749
    assert metadata["json_object_grammar"] is True
    assert metadata["native_schema_grammar"] is False
    assert metadata["bounded_generation_grammar"] == "szl.ouroboros.compact-ascii-json/v1"
    assert metadata["generation_grammar_sha256"] == hashlib.sha256(
        calls["grammar_text"].encode("ascii")
    ).hexdigest()
    assert metadata["finish_reason"] == "stop"


@pytest.mark.parametrize("mutation", [
    lambda value: value["properties"].pop("candidate_set_sha256"),
    lambda value: value["properties"]["candidate_set_sha256"].update(const="d" * 63),
    lambda value: value["properties"]["candidate_set_sha256"].update(const=True),
    lambda value: value["properties"]["recommendations"]["items"]["properties"][
        "evidence_candidate_ids"
    ]["items"].update(enum=[]),
    lambda value: value["properties"]["recommendations"]["items"]["properties"][
        "evidence_candidate_ids"
    ]["items"].update(enum=["not-a-candidate"]),
    lambda value: value["properties"]["recommendations"]["items"]["properties"][
        "evidence_candidate_ids"
    ]["items"].update(enum=["frontier:" + "a" * 32] * 2),
    lambda value: value["properties"]["recommendations"]["items"]["properties"][
        "evidence_candidate_ids"
    ]["items"].update(enum=[f"frontier:{index:032x}" for index in range(25)]),
])
def test_generation_grammar_requires_exact_bounded_evidence_before_model_load(mutation):
    schema = build_runtime_schema(
        review_schema(), candidate_digest="d" * 64,
        allowed_candidate_ids=["frontier:" + "a" * 32],
    )
    mutation(schema)
    with pytest.raises(OpenReviewerError, match="generation grammar"):
        build_compact_generation_grammar(schema)


def test_bounded_generation_does_not_admit_a_complete_but_truncated_review():
    value = proposed_review()
    review, admitted, admission, code = admit_or_block_model_output(
        json.dumps(value, separators=(",", ":")),
        candidate_digest="d" * 64,
        selected_candidate_ids=["frontier:" + "a" * 32],
        finish_reason="length",
    )
    assert admitted is False
    assert admission == "MODEL_OUTPUT_REJECTED_FAIL_CLOSED"
    assert code == "OUTPUT_TRUNCATED"
    assert review["state"] == "BLOCKED"


def test_endpoint_records_finish_reason_for_independent_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {"content": '{"state":"NO_ACTION_RECOMMENDED"}'},
                            "finish_reason": "stop",
                        }
                    ]
                }
            ).encode()

    def fake_urlopen(_request: object, timeout: int) -> FakeResponse:
        assert timeout == 180
        return FakeResponse()

    monkeypatch.setattr(
        "scripts.run_open_frontier_review.urllib.request.urlopen", fake_urlopen
    )
    content, metadata = run_openai_compatible(
        base_url="http://127.0.0.1:8000",
        model_name="local-model",
        messages=[{"role": "user", "content": "Return JSON."}],
        runtime_schema=review_schema(),
        max_tokens=1800,
        seed=749,
        api_key=None,
    )
    assert content == '{"state":"NO_ACTION_RECOMMENDED"}'
    assert metadata["finish_reason"] == "stop"
    assert metadata["json_object_grammar"] is False


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
    assert receipt["admission"]["failure_code"] is None
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
    review, admitted, admission, failure_code = admit_or_block_model_output(
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
        failure_code=failure_code,
    )
    assert receipt["state"] == "OPEN_WEIGHT_REVIEW_BLOCKED_FAIL_CLOSED"
    assert receipt["admission"]["model_output_admitted"] is False
    assert receipt["admission"]["failure_code"] == "OUTPUT_NOT_SINGLE_JSON_OBJECT"
    assert receipt["authority"] == NONE_AUTHORITY


def workflow_step(name: str) -> tuple[str, str]:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/codex-continuous-frontier.yml").read_text()
    block = workflow.split(f"      - name: {name}\n", 1)[1].split("\n      - name:", 1)[0]
    body = block.split("        run: |\n", 1)[1]
    return block, "\n".join(line[10:] for line in body.splitlines())


def workflow_reviewer_selection(
    tmp_path: Path, *, event: str, choice: str | None, key_present: bool
) -> tuple[dict[str, str], dict[str, object]]:
    # Execute both checked-in selection steps with only a synthetic key. This
    # invokes no action, provider, model, remote source, or credential lookup.
    output = tmp_path / "selection-output"
    env = {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "GITHUB_OUTPUT": str(output),
        "REVIEW_EVENT_NAME": event,
        "GITHUB_EVENT_NAME": event,
        "GITHUB_SHA": "5" * 40,
    }
    if choice is not None:
        env["REVIEWER_REQUEST"] = choice
    _, selection_shell = workflow_step("Validate the manual reviewer selection")
    selected = subprocess.run(
        ["bash", "-c", selection_shell], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert selected.returncode == 0, selected.stderr
    mode = dict(line.split("=", 1) for line in output.read_text().splitlines())["mode"]
    env["REVIEWER_MODE"] = mode
    fake_key = "synthetic-selection-key-do-not-print"
    env["CODEX_API_KEY"] = fake_key if key_present else ""
    (tmp_path / "outputs").mkdir()
    _, authority_shell = workflow_step("Detect optional Codex authority without revealing it")
    authority = subprocess.run(
        ["bash", "-c", authority_shell], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert authority.returncode == 0, authority.stderr
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    receipt_text = (tmp_path / "outputs/reviewer-selection.json").read_text()
    assert fake_key not in selected.stdout + selected.stderr + authority.stdout + authority.stderr
    assert fake_key not in receipt_text + output.read_text()
    receipt = json.loads(receipt_text)
    assert receipt["workflow_event"] == event
    assert receipt["controller_revision"] == "5" * 40
    assert receipt["schema"] == "szl.ouroboros.reviewer-selection/v1"
    return values, receipt


@pytest.mark.parametrize("event,choice,key_present,mode,provider", [
    ("workflow_dispatch", "local-gguf", True, "local-gguf", "local-gguf"),
    ("workflow_dispatch", "local-gguf", False, "local-gguf", "local-gguf"),
    ("workflow_dispatch", "auto", True, "auto", "codex"),
    ("workflow_dispatch", "auto", False, "auto", "local-gguf"),
    ("workflow_dispatch", None, True, "auto", "codex"),
    ("workflow_dispatch", None, False, "auto", "local-gguf"),
    ("schedule", "local-gguf", True, "auto", "codex"),
    ("schedule", "local-gguf", False, "auto", "local-gguf"),
    ("push", "invalid-input-is-ignored", True, "auto", "codex"),
    ("push", "local-gguf", False, "auto", "local-gguf"),
])
def test_workflow_manual_reviewer_selection_preserves_automatic_behavior(
    tmp_path: Path, event: str, choice: str | None, key_present: bool,
    mode: str, provider: str,
) -> None:
    values, receipt = workflow_reviewer_selection(
        tmp_path, event=event, choice=choice, key_present=key_present
    )
    assert values == {
        "mode": mode, "present": str(provider == "codex").lower(), "reviewer": provider,
    }
    assert receipt["requested_reviewer"] == mode
    assert receipt["selected_reviewer"] == provider
    assert receipt["codex_authority_enabled"] is (provider == "codex")


@pytest.mark.parametrize("choice", [
    "codex", "LOCAL-GGUF", "local-gguf\nmode=auto", "$(touch selection-must-not-execute)",
])
def test_workflow_rejects_invalid_manual_reviewer_before_source_or_model(
    tmp_path: Path, choice: str
) -> None:
    _, shell = workflow_step("Validate the manual reviewer selection")
    output = tmp_path / "selection-output"
    env = {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "REVIEW_EVENT_NAME": "workflow_dispatch", "REVIEWER_REQUEST": choice,
        "GITHUB_OUTPUT": str(output),
    }
    result = subprocess.run(
        ["bash", "-c", shell], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "Invalid manual reviewer selection" in result.stderr
    assert choice not in result.stdout + result.stderr
    assert not output.exists()
    assert not (tmp_path / "outputs/reviewer-selection.json").exists()
    assert not (tmp_path / "selection-must-not-execute").exists()


def test_workflow_manual_choice_masks_authority_and_retains_review_gates() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/codex-continuous-frontier.yml").read_text()
    dispatch = workflow.split("  workflow_dispatch:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "      reviewer:\n" in dispatch
    assert "        type: choice\n" in dispatch
    assert "        default: auto\n" in dispatch
    assert "          - auto\n          - local-gguf\n" in dispatch
    selection, _ = workflow_step("Validate the manual reviewer selection")
    assert "REVIEW_EVENT_NAME: ${{ github.event_name }}" in selection
    assert "REVIEWER_REQUEST: ${{ github.event.inputs.reviewer || 'auto' }}" in selection
    assert workflow.index("name: Start the measured bounded loop") < workflow.index(
        "name: Validate the manual reviewer selection"
    ) < workflow.index("name: Prepare exact Second Brain frontier input")
    authority, _ = workflow_step("Detect optional Codex authority without revealing it")
    assert (
        "CODEX_API_KEY: ${{ steps.selection.outputs.mode == 'auto' && "
        "(secrets.OPENAI_API_KEY || secrets.CODEX_API_KEY) || '' }}"
    ) in authority
    codex = workflow.split("      - name: Run Codex as a read-only advisory reviewer\n", 1)[1].split(
        "\n      - name:", 1
    )[0]
    assert "if: steps.key.outputs.reviewer == 'codex' && steps.key.outputs.present == 'true'" in codex
    assert 'permission-profile: ":read-only"' in codex
    assert "safety-strategy: drop-sudo" in codex
    for name in [
        "Cache exact public Khipu model and verified wheel",
        "Install verified keyless open-model runtime",
        "Run exact Khipu GGUF as the keyless advisory reviewer",
    ]:
        block = workflow.split(f"      - name: {name}\n", 1)[1].split("\n      - name:", 1)[0]
        assert "if: steps.key.outputs.reviewer == 'local-gguf'" in block
    _, local_shell = workflow_step("Run exact Khipu GGUF as the keyless advisory reviewer")
    for setting in [
        "--provider local-gguf", "--candidate-limit 6", "--context-tokens 16384",
        "--max-tokens 1800", "--seed 749",
    ]:
        assert setting in local_shell
    assert "            outputs/reviewer-selection.json\n" in workflow
    assert "\npermissions:\n  contents: read\n" in workflow
    assert "if: github.event_name != 'pull_request'" in workflow


@pytest.mark.parametrize("review_state,open_outcome,accepted", [
    ("NO_ACTION_RECOMMENDED", "success", True),
    ("BLOCKED", "success", False),
    ("NO_ACTION_RECOMMENDED", "failure", False),
])
def test_workflow_manual_local_receipt_and_final_gate_remain_honest(
    tmp_path: Path, review_state: str, open_outcome: str, accepted: bool
) -> None:
    values, selection = workflow_reviewer_selection(
        tmp_path, event="workflow_dispatch", choice="local-gguf", key_present=True
    )
    assert selection["codex_authority_enabled"] is False
    candidate = row("frontier:" + "a" * 32, "szl-holdings/szl-ouroboros")
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(json.dumps(candidate) + "\n")
    digest = hashlib.sha256(candidates.read_bytes()).hexdigest()
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "schema": "szl.ouroboros.codex-frontier-source/v1",
        "candidate_count": 1, "candidate_set_sha256": digest, "authority": NONE_AUTHORITY,
    }))
    review = tmp_path / "review.json"
    review.write_text(json.dumps({
        "schema": "szl.codex.frontier-review/v1",
        "state": review_state, "candidate_set_sha256": digest,
        "summary": "No bounded change is justified by this evidence.",
        "recommendations": [], "authority": NONE_AUTHORITY,
    }))
    wall_timer, reviewer_timer = tmp_path / "wall-start", tmp_path / "reviewer-start"
    now = int(time.time() * 1000)
    wall_timer.write_text(str(now - 2000))
    reviewer_timer.write_text(str(now - 1000))
    root = Path(__file__).resolve().parents[1]
    receipt_path = tmp_path / "loop.json"
    open_receipt = tmp_path / "open-execution.json"
    open_receipt.write_text(json.dumps({"provider": {"provider": "llama-cpp-python"}}))
    env = {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "PYTHONPATH": str(root / "torch-ext"),
        "SOURCE_RECEIPT": str(source), "CANDIDATES": str(candidates),
        "REVIEW_OUTPUT": str(review), "LOOP_RECEIPT": str(receipt_path),
        "OPEN_EXECUTION_RECEIPT": str(open_receipt),
        "PREPARATION_OUTCOME": "success", "CODEX_CONFIGURED": values["present"],
        "CODEX_OUTCOME": "skipped", "OPEN_REVIEWER_OUTCOME": open_outcome,
        "OPEN_MODEL_LABEL": "pinned-gguf",
    }
    _, shell = workflow_step("Close the loop with an exact receipt")
    shell = shell.replace("/tmp/ouroboros-wall-start-ms", str(wall_timer))
    shell = shell.replace("/tmp/reviewer-start-ms", str(reviewer_timer))
    result = subprocess.run(
        ["bash", "-c", shell], cwd=root, env=env, capture_output=True, text=True, timeout=10
    )
    assert (result.returncode == 0) is accepted, result.stderr
    receipt = json.loads(receipt_path.read_text())
    assert receipt["codex"]["configured"] is False
    assert receipt["codex"]["attempted"] is False
    assert receipt["codex"]["outcome"] == "not_attempted"
    assert receipt["codex"]["review"] is None
    assert receipt["open_reviewer"]["attempted"] is True
    assert receipt["open_reviewer"]["outcome"] == open_outcome
    assert receipt["authority"] == NONE_AUTHORITY
    assert receipt["ouroboros"]["receiptsInEqOut"] is True
    assert receipt["ouroboros"]["withinBudget"] is True
    assert receipt["state"] == (review_state if open_outcome == "success" else "OPEN_REVIEWER_FAILED")
    env["GITHUB_STEP_SUMMARY"] = str(tmp_path / "summary.md")
    _, summary_shell = workflow_step("Publish the loop summary")
    summary_result = subprocess.run(
        ["bash", "-c", summary_shell], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert summary_result.returncode == 0, summary_result.stderr
    summary = Path(env["GITHUB_STEP_SUMMARY"]).read_text()
    assert "Requested reviewer: local-gguf" in summary
    assert "Selected reviewer: local-gguf" in summary
    assert "Codex authority enabled for this run:" in summary
    assert "Codex configured:" not in summary
    env["FINALIZE_OUTCOME"] = "success" if accepted else "failure"
    _, enforce_shell = workflow_step("Enforce honest terminal state")
    enforced = subprocess.run(
        ["bash", "-c", enforce_shell], cwd=root, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert (enforced.returncode == 0) is accepted
