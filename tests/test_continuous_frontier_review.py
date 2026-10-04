from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse

import pytest

from scripts.finalize_codex_frontier_review import ReviewError, finalize
from scripts.prepare_codex_frontier_review import PacketError, build_input, validate_packet


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


def source_identities() -> list[dict[str, str]]:
    return [
        {"source_id": "a11oy_public_estate", "repository": "szl-holdings/a11oy", "path": "governance/public-estate.v1.json", "parser": "public_estate"},
        {"source_id": "forge_production_controller", "repository": "szl-holdings/szl-forge", "path": "inference/production.py", "parser": "python_contract"},
        {"source_id": "formula_quant_atlas", "repository": "szl-holdings/szl-formulas", "path": "atlas/formula-atlas.v1.json", "parser": "formula_atlas"},
        {"source_id": "governed_kernel_suite", "repository": "szl-holdings/szl-kernels", "path": "README.md", "parser": "markdown"},
        {"source_id": "living_anatomy", "repository": "szl-holdings/anatomy", "path": "README.md", "parser": "markdown"},
        {"source_id": "nemo_witness", "repository": "szl-holdings/szl-nemo", "path": "README.md", "parser": "markdown"},
        {"source_id": "ouroboros_runtime", "repository": "szl-holdings/szl-ouroboros", "path": "README.md", "parser": "markdown"},
        {"source_id": "science_forum_pilot", "repository": "szl-holdings/szl-science-forum-corpus", "path": "dataset/sources.public.jsonl", "parser": "forum_pilot"},
        {"source_id": "public_research_arxiv", "repository": "public-metadata/arxiv", "path": "data/public-research-metadata.v1.json", "parser": "public_research_metadata"},
        {"source_id": "public_research_crossref", "repository": "public-metadata/crossref", "path": "data/public-research-metadata.v1.json", "parser": "public_research_metadata"},
    ]


def packet_bytes() -> tuple[bytes, bytes, str]:
    row = candidate()
    candidates = canonical_bytes(row) + b"\n"
    digest = hashlib.sha256(candidates).hexdigest()
    state = {
        "schema": "szl.second-brain.frontier-state/v1",
        "state": "REVIEW_REQUIRED",
        "candidate_count": 1,
        "candidate_set_sha256": digest,
        "source_count": 10,
        "sources": source_identities(),
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
                "source_count": 8,
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


def metadata_candidate(provider: str = "arxiv", *, long_fields: bool = False) -> dict[str, object]:
    row = candidate()
    metadata = {
        "provider": provider,
        "identifier": "2601.00001v1" if provider == "arxiv" else "10.1000/example",
        "title": "Synthetic metadata fixture",
        "full_text_licence": "NOT_INFERRED",
        "authors": ["Fixture Author"], "categories": [], "licence_urls": [],
        "published": "2026-01-01T00:00:00Z" if provider == "arxiv" else "2026-01-01",
        "updated": "2026-01-01T00:00:00Z" if provider == "arxiv" else None,
        "metadata_licence": "CC0-1.0" if provider == "arxiv" else "NOT_DECLARED_BY_RESPONSE",
    }
    metadata["canonical_url"] = ("https://arxiv.org/abs/" if provider == "arxiv" else "https://doi.org/") + metadata["identifier"]
    if long_fields:
        metadata["title"] = "T" * 240
        metadata["authors"] = ["A" * 240] * 32
    content = "\n".join((metadata["title"], "Authors: " + ", ".join(metadata["authors"]),
                         "Identifier: " + metadata["identifier"], "Publication date: " + str(metadata["published"]),
                         "Categories: " + ", ".join(metadata["categories"]),
                         "Metadata licence: " + metadata["metadata_licence"],
                         "Full text licence: NOT_INFERRED", "Source: " + metadata["canonical_url"]))
    content = "\n".join(line.rstrip() for line in content.splitlines()).strip()[:1600]
    capture = hashlib.sha256(canonical_bytes(metadata)).hexdigest()
    row.update({
        "title": metadata["title"][:180], "content": content,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "source_repository": f"public-metadata/{provider}",
        "source_path": metadata["identifier"],
        "source_kind": "research-metadata",
        "source_revision_kind": "metadata-capture-sha256",
        "source_revision": capture,
        "admission": "DISCOVERED_REVIEW_REQUIRED",
        "provenance": {
            "provider": provider,
            "identifier": metadata["identifier"],
            "metadata": metadata,
            "capture_sha256": capture,
            "response_sha256": "b" * 64, "response_bytes": 1024,
            "observed_at": "2026-01-01T01:00:00Z",
            "request_url": ("https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": metadata["identifier"], "max_results": 1})
                            if provider == "arxiv" else "https://api.crossref.org/works/" + urllib.parse.quote(metadata["identifier"], safe="")),
            "source_authentication": "PUBLIC_HTTPS_METADATA_NOT_INDEPENDENT_ATTESTATION",
        },
    })
    return row


def repack(row: dict[str, object]) -> tuple[bytes, bytes]:
    state_raw, _, _ = packet_bytes()
    state = json.loads(state_raw)
    candidates_raw = canonical_bytes(row) + b"\n"
    state["candidate_set_sha256"] = hashlib.sha256(candidates_raw).hexdigest()
    return canonical_bytes(state), candidates_raw


@pytest.mark.parametrize("provider", ["arxiv", "crossref"])
def test_prepare_admits_bound_metadata_without_relabelling_as_git(provider: str) -> None:
    row = metadata_candidate(provider)
    state_raw, candidates_raw = repack(row)
    _, rows = validate_packet(state_raw, candidates_raw)
    assert rows == [row]
    payload, _ = build_input("a" * 40, state_raw, candidates_raw)
    projected = payload["candidates"][0]
    assert projected["source_revision_kind"] == "metadata-capture-sha256"
    assert projected["source_authentication"] == "PUBLIC_HTTPS_METADATA_NOT_INDEPENDENT_ATTESTATION"
    assert payload["authority"]["training"] == "NONE"


@pytest.mark.parametrize("tamper", [
    "digest", "untyped", "kind", "repository", "provider", "identifier",
    "capture", "metadata", "authentication", "full_text_licence", "admission",
    "content", "title", "response", "request", "timestamp", "unhashable_provider", "unhashable_request",
])
def test_prepare_rejects_metadata_type_or_provenance_drift(tamper: str) -> None:
    row = metadata_candidate()
    if tamper == "digest":
        row["source_revision"] = "1" * 40
    elif tamper == "untyped":
        row.pop("source_revision_kind")
    elif tamper == "kind":
        row["source_kind"] = "public-source"
    elif tamper == "repository":
        row["source_repository"] = "public-metadata/other"
    elif tamper in {"provider", "identifier"}:
        row["provenance"][tamper] = "other"
    elif tamper == "capture":
        row["provenance"]["capture_sha256"] = "0" * 64
    elif tamper == "metadata":
        row["provenance"]["metadata"]["title"] = "changed"
    elif tamper == "authentication":
        row["provenance"]["source_authentication"] = "VERIFIED_TRUTH"
    elif tamper == "full_text_licence":
        row["provenance"]["metadata"]["full_text_licence"] = "INFERRED"
    elif tamper == "content":
        row["content"] = "This is a full paper, not the retained metadata."
        row["content_sha256"] = hashlib.sha256(row["content"].encode()).hexdigest()
    elif tamper == "title":
        row["title"] = "Unbound title"
    elif tamper == "response":
        row["provenance"]["response_bytes"] = 256 * 1024 + 1
    elif tamper == "request":
        row["provenance"]["request_url"] = "https://example.invalid/"
    elif tamper == "timestamp":
        row["provenance"]["observed_at"] = "unknown"
    elif tamper == "unhashable_provider":
        row["provenance"]["metadata"]["provider"] = []
    elif tamper == "unhashable_request":
        row["provenance"]["request_url"] = []
    else:
        row["admission"] = "ACCEPTED"
    with pytest.raises(PacketError, match="source binding"):
        validate_packet(*repack(row))


@pytest.mark.parametrize("revision_kind", ["git-sha1", "metadata-capture-sha256", "unknown"])
def test_prepare_does_not_admit_sha256_as_git_revision(revision_kind: str) -> None:
    row = candidate()
    row["source_revision"] = "1" * 64
    row["source_revision_kind"] = revision_kind
    with pytest.raises(PacketError, match="source binding"):
        validate_packet(*repack(row))


def test_prepare_retains_producer_title_and_content_bounds() -> None:
    row = metadata_candidate(long_fields=True)
    assert len(row["title"]) == 180
    assert len(row["content"]) == 1600
    assert validate_packet(*repack(row))[1] == [row]


@pytest.mark.parametrize("preparation_outcome", ["failure", "cancelled", "skipped"])
def test_prepare_failure_closes_without_source_or_reviewer(tmp_path: Path, preparation_outcome: str) -> None:
    output = tmp_path / "loop-receipt.json"
    receipt = finalize(
        source_receipt_path=tmp_path / "missing-source.json",
        candidate_path=tmp_path / "missing-candidates.jsonl",
        review_path=tmp_path / "missing-review.json",
        output_path=output,
        codex_attempted=False, codex_outcome="skipped", model="",
        latency_ms=0, wall_ms=1500,
        preparation_outcome=preparation_outcome,
    )
    assert receipt["state"] == "SOURCE_PREPARATION_FAILED"
    assert receipt["source"] is None
    assert receipt["preparation"] == {"outcome": preparation_outcome, "validated": False}
    assert receipt["codex"]["attempted"] is False
    assert receipt["open_reviewer"]["attempted"] is False
    assert receipt["ouroboros"]["exit"] == "aborted"
    assert receipt["ouroboros"]["modelMs"] == 0
    assert receipt["ouroboros"]["receiptsInEqOut"] is True
    assert receipt["authority"]["execution"] == "NONE"
    saved = json.loads(output.read_text())
    digest = saved.pop("receipt_sha256")
    assert digest == hashlib.sha256(canonical_bytes(saved)).hexdigest()


def test_failed_prepare_cannot_hide_model_attempt(tmp_path: Path) -> None:
    with pytest.raises(ReviewError, match="preparation"):
        finalize(
            source_receipt_path=tmp_path / "missing-source.json",
            candidate_path=tmp_path / "missing-candidates.jsonl",
            review_path=tmp_path / "missing-review.json",
            output_path=tmp_path / "receipt.json",
            codex_attempted=True, codex_outcome="success", model="",
            latency_ms=50, wall_ms=100, preparation_outcome="failure",
        )


def test_workflow_finalizer_retains_prepare_failure_without_reviewer_timer(tmp_path: Path) -> None:
    # Execute the checked-in shell itself. Redirect only its two timer paths;
    # no model, remote source, credential, or workflow dispatch is involved.
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/codex-continuous-frontier.yml").read_text()
    finalizer = workflow.split("      - name: Close the loop with an exact receipt\n", 1)[1]
    run = finalizer.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
    shell = "\n".join(line[10:] for line in run.splitlines())
    wall_timer = tmp_path / "wall-start-ms"
    wall_timer.write_text(str(int(time.time() * 1000) - 50))
    shell = shell.replace("/tmp/ouroboros-wall-start-ms", str(wall_timer))
    shell = shell.replace("/tmp/reviewer-start-ms", str(tmp_path / "missing-reviewer-start-ms"))
    output = tmp_path / "receipt.json"
    env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
    env.update({
        "SOURCE_RECEIPT": str(tmp_path / "missing-source.json"),
        "CANDIDATES": str(tmp_path / "missing-candidates.jsonl"),
        "REVIEW_OUTPUT": str(tmp_path / "missing-review.json"),
        "LOOP_RECEIPT": str(output), "PREPARATION_OUTCOME": "failure",
        "CODEX_CONFIGURED": "false", "CODEX_OUTCOME": "skipped",
        "OPEN_REVIEWER_OUTCOME": "skipped", "OPEN_MODEL_LABEL": "not-run",
    })
    result = subprocess.run(["bash", "-c", shell], cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode == 2, result.stderr
    assert json.loads(output.read_text())["state"] == "SOURCE_PREPARATION_FAILED"
    summary = workflow.split("      - name: Publish the loop summary\n", 1)[1]
    summary_run = summary.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
    summary_shell = "\n".join(line[10:] for line in summary_run.splitlines())
    env["GITHUB_STEP_SUMMARY"] = str(tmp_path / "summary.md")
    env["OPEN_EXECUTION_RECEIPT"] = str(tmp_path / "missing-execution.json")
    summary_result = subprocess.run(["bash", "-c", summary_shell], cwd=root, env=env, capture_output=True, text=True)
    assert summary_result.returncode == 0, summary_result.stderr
    summary_text = Path(env["GITHUB_STEP_SUMMARY"]).read_text()
    assert "Source revision: `UNAVAILABLE`" in summary_text
    assert "Reviewer: `NOT_ATTEMPTED`" in summary_text
    enforce = workflow.split("      - name: Enforce honest terminal state\n", 1)[1]
    enforce_run = enforce.split("        run: |\n", 1)[1]
    enforce_shell = "\n".join(line[10:] for line in enforce_run.splitlines())
    env["FINALIZE_OUTCOME"] = "failure"
    enforced = subprocess.run(["bash", "-c", enforce_shell], cwd=root, env=env, capture_output=True, text=True)
    assert enforced.returncode != 0


@pytest.mark.parametrize("stale_count", [7, 8, 9, 11])
def test_prepare_rejects_stale_source_contract(stale_count: int) -> None:
    state_raw, candidates_raw, _digest = packet_bytes()
    state = json.loads(state_raw)
    state["source_count"] = stale_count
    with pytest.raises(PacketError, match="source count drifted"):
        validate_packet(json.dumps(state).encode(), candidates_raw)


def test_prepare_requires_the_exact_ten_source_identities() -> None:
    state_raw, candidates_raw, _digest = packet_bytes()
    state = json.loads(state_raw)
    state["sources"][0]["repository"] = "szl-holdings/other"
    with pytest.raises(PacketError, match="source identity drifted"):
        validate_packet(json.dumps(state).encode(), candidates_raw)
    state = json.loads(state_raw)
    state.pop("sources")
    with pytest.raises(PacketError, match="source list count mismatch"):
        validate_packet(json.dumps(state).encode(), candidates_raw)
    state = json.loads(state_raw)
    state["sources"][7]["source_id"] = "ouroboros_runtime"
    with pytest.raises(PacketError, match="source identity drifted"):
        validate_packet(json.dumps(state).encode(), candidates_raw)
    state = json.loads(state_raw)
    state["sources"][7]["parser"] = "markdown"
    with pytest.raises(PacketError, match="source identity drifted"):
        validate_packet(json.dumps(state).encode(), candidates_raw)


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


def test_finalize_keeps_codex_unavailable_separate_from_keyless_review(tmp_path: Path) -> None:
    source, candidates, review_path, digest = write_finalize_fixture(tmp_path)
    review_path.write_text(
        json.dumps({
            "schema": "szl.codex.frontier-review/v1",
            "state": "NO_ACTION_RECOMMENDED",
            "candidate_set_sha256": digest,
            "summary": "The current evidence does not justify a bounded change.",
            "recommendations": [],
            "authority": {"training": "NONE", "promotion": "NONE", "execution": "NONE", "merge": "NONE", "provider_mutation": "NONE"},
        }),
        encoding="utf-8",
    )
    receipt = finalize(
        source_receipt_path=source,
        candidate_path=candidates,
        review_path=review_path,
        output_path=tmp_path / "loop-receipt.json",
        codex_attempted=False,
        codex_configured=False,
        codex_outcome="skipped",
        model="codex-default",
        open_reviewer_attempted=True,
        open_reviewer_outcome="success",
        open_reviewer_model="pinned-gguf",
        latency_ms=100.0,
        wall_ms=120.0,
    )
    assert receipt["state"] == "NO_ACTION_RECOMMENDED"
    assert receipt["codex"]["configured"] is False
    assert receipt["codex"]["attempted"] is False
    assert receipt["codex"]["review"] is None
    assert receipt["open_reviewer"]["attempted"] is True
    assert receipt["open_reviewer"]["review"]["state"] == "NO_ACTION_RECOMMENDED"
    assert receipt["ouroboros"]["exit"] == "converged"


def test_finalize_blocked_keyless_output_is_not_a_converged_review(tmp_path: Path) -> None:
    source, candidates, review_path, digest = write_finalize_fixture(tmp_path)
    review_path.write_text(
        json.dumps({
            "schema": "szl.codex.frontier-review/v1",
            "state": "BLOCKED",
            "candidate_set_sha256": digest,
            "summary": "The model output was rejected by independent admission.",
            "recommendations": [],
            "authority": {"training": "NONE", "promotion": "NONE", "execution": "NONE", "merge": "NONE", "provider_mutation": "NONE"},
        }),
        encoding="utf-8",
    )
    receipt = finalize(
        source_receipt_path=source,
        candidate_path=candidates,
        review_path=review_path,
        output_path=tmp_path / "loop-receipt.json",
        codex_attempted=False,
        codex_configured=False,
        codex_outcome="skipped",
        model="codex-default",
        open_reviewer_attempted=True,
        open_reviewer_outcome="success",
        open_reviewer_model="pinned-gguf",
        latency_ms=100.0,
        wall_ms=120.0,
    )
    assert receipt["state"] == "BLOCKED"
    assert receipt["codex"]["attempted"] is False
    assert receipt["open_reviewer"]["review"]["state"] == "BLOCKED"
    assert receipt["ouroboros"]["exit"] == "error"


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
