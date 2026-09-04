#!/usr/bin/env python3
"""Build and validate a bounded Codex-assisted Ouroboros frontier loop.

The loop is proposal-only. It observes exact public source artifacts, gives a
read-only Codex process a bounded context, validates the resulting JSON against
source handles and authority constraints, and emits a content-addressed receipt.
It cannot merge, deploy, train weights, expose private memory, or execute tools.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

USER_AGENT = "szl-ouroboros-continuous-frontier-loop/1.0"
MAX_API_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_LIVE_BYTES = 256 * 1024
MAX_CANDIDATES = 256
MAX_CYCLES = 5
MAX_STRING = 8_000
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)

SECOND_BRAIN_REPOSITORY = "szl-holdings/szl-second-brain"
SECOND_BRAIN_STATE_PATH = "data/frontier-state.v1.json"
SECOND_BRAIN_CANDIDATES_PATH = "data/frontier-candidates.public.jsonl"
FORMULA_REPOSITORY = "szl-holdings/szl-formulas"
FORMULA_PATH = "atlas/formula-atlas.v1.json"
ANATOMY_ORIGIN = "https://betterwithage-anatomy.hf.space"
ANATOMY_PATHS = (
    "/api/anatomy/v1/living-health",
    "/api/anatomy/v1/brain/health",
    "/version",
)

LOOP_STAGES = (
    "OBSERVE",
    "RETRIEVE",
    "HYPOTHESIZE",
    "FALSIFY",
    "REVISE",
    "PACKAGE",
    "REVIEW",
)

AUTHORITY = {
    "content_access": "PUBLIC_CANDIDATES_READ_ONLY",
    "private_memory_access": "NONE",
    "training": "NONE",
    "weight_update": "NONE",
    "promotion": "NONE",
    "merge": "NONE",
    "execution": "NONE",
    "provider_mutation": "NONE",
    "consequential_action": "HUMAN_REVIEW_REQUIRED",
}


class LoopBoundaryError(RuntimeError):
    """Raised when source or proposal bytes cross the bounded loop contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def reject_secret_like(value: str, *, label: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            raise LoopBoundaryError("secret-like material rejected from " + label)


def request_bytes(
    url: str,
    *,
    token: Optional[str] = None,
    limit: int,
    accept: str = "application/json, text/plain;q=0.9, */*;q=0.8",
) -> bytes:
    headers = {
        "Accept": accept,
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read(limit + 1)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise LoopBoundaryError("bounded GET failed: " + type(exc).__name__) from exc
    if len(payload) > limit:
        raise LoopBoundaryError("bounded GET exceeded response limit")
    return payload


def github_json(url: str, token: Optional[str]) -> Any:
    try:
        payload = request_bytes(url, token=token, limit=MAX_API_BYTES)
    except LoopBoundaryError:
        if not token:
            raise
        payload = request_bytes(url, token=None, limit=MAX_API_BYTES)
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise LoopBoundaryError("GitHub returned malformed JSON") from exc


def resolve_path_revision(
    repository: str,
    path: str,
    *,
    token: Optional[str],
    api_url: str = "https://api.github.com",
) -> str:
    encoded_path = urllib.parse.quote(path, safe="")
    url = (
        api_url.rstrip("/")
        + "/repos/"
        + repository
        + "/commits?path="
        + encoded_path
        + "&sha=main&per_page=1"
    )
    value = github_json(url, token)
    if not isinstance(value, list) or len(value) != 1:
        raise LoopBoundaryError("exact source revision was not returned")
    revision = str(value[0].get("sha") or "").lower()
    if not HEX_40.fullmatch(revision):
        raise LoopBoundaryError("source revision is not an exact Git commit")
    return revision


def fetch_immutable_source(
    repository: str,
    path: str,
    *,
    token: Optional[str],
    api_url: str = "https://api.github.com",
    raw_url: str = "https://raw.githubusercontent.com",
) -> Tuple[str, bytes]:
    revision = resolve_path_revision(repository, path, token=token, api_url=api_url)
    encoded_path = "/".join(
        urllib.parse.quote(part, safe="") for part in path.split("/")
    )
    payload = request_bytes(
        raw_url.rstrip("/")
        + "/"
        + repository
        + "/"
        + revision
        + "/"
        + encoded_path,
        limit=MAX_SOURCE_BYTES,
    )
    reject_secret_like(payload.decode("utf-8"), label=repository + "/" + path)
    return revision, payload


def parse_candidate_lines(payload: bytes) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LoopBoundaryError(
                "candidate JSONL is malformed at line " + str(line_number)
            ) from exc
        if not isinstance(row, dict):
            raise LoopBoundaryError("candidate row is not an object")
        candidate_id = str(row.get("id") or "")
        if not candidate_id or candidate_id in seen:
            raise LoopBoundaryError("candidate IDs are missing or duplicated")
        seen.add(candidate_id)
        if row.get("candidate_state") != "DISCOVERED_REVIEW_REQUIRED":
            raise LoopBoundaryError("candidate state crossed the review boundary")
        if row.get("content_access") != "CONTROLLER_ONLY":
            raise LoopBoundaryError("candidate content access crossed the boundary")
        revision = str(row.get("source_revision") or "")
        digest = str(row.get("content_sha256") or "")
        content = str(row.get("content") or "")
        if not HEX_40.fullmatch(revision):
            raise LoopBoundaryError("candidate source revision is not exact")
        if not HEX_64.fullmatch(digest):
            raise LoopBoundaryError("candidate content digest is malformed")
        if sha256_bytes(content.encode("utf-8")) != digest:
            raise LoopBoundaryError("candidate content digest does not replay")
        reject_secret_like(content, label="frontier candidate")
        rows.append(row)
        if len(rows) > MAX_CANDIDATES:
            raise LoopBoundaryError("candidate corpus exceeded the bounded maximum")
    if not rows:
        raise LoopBoundaryError("candidate corpus is empty")
    return rows


def candidate_set_digest(rows: Sequence[Dict[str, Any]]) -> str:
    canonical = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    return sha256_bytes(canonical)


def inspect_local_kernel() -> Dict[str, Any]:
    """Inspect and self-check the local Python kernel without network or mutation."""

    try:
        import szl_ouroboros as kernel
    except Exception as exc:
        return {
            "state": "UNAVAILABLE",
            "reason": type(exc).__name__,
            "network_used": False,
            "mutation_performed": False,
        }

    result: Dict[str, Any] = {
        "state": "LOADED",
        "module": "szl_ouroboros",
        "version": str(getattr(kernel, "__version__", "UNKNOWN")),
        "exports": sorted(
            name
            for name in dir(kernel)
            if not name.startswith("_") and callable(getattr(kernel, name, None))
        )[:80],
        "network_used": False,
        "mutation_performed": False,
    }
    selfcheck = getattr(kernel, "selfcheck", None)
    if callable(selfcheck):
        try:
            value = selfcheck()
            canonical_bytes(value)
            result["selfcheck_state"] = "COMPLETED"
            result["selfcheck"] = value
        except Exception as exc:
            result["selfcheck_state"] = "FAILED"
            result["selfcheck_reason"] = type(exc).__name__
    else:
        result["selfcheck_state"] = "NOT_EXPORTED"
    return result


def observe_anatomy() -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []
    for path in ANATOMY_PATHS:
        url = ANATOMY_ORIGIN + path + "?frontier_loop=1"
        try:
            payload = request_bytes(url, limit=MAX_LIVE_BYTES)
            content_type = "application/json"
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None
                content_type = "non-json"
            observations.append(
                {
                    "path": path,
                    "state": "REACHABLE",
                    "content_type": content_type,
                    "response_sha256": sha256_bytes(payload),
                    "json": parsed,
                }
            )
        except LoopBoundaryError as exc:
            observations.append(
                {
                    "path": path,
                    "state": "UNAVAILABLE",
                    "reason": type(exc).__name__,
                }
            )
    return observations


def build_context(
    *,
    token: Optional[str],
    api_url: str = "https://api.github.com",
    raw_url: str = "https://raw.githubusercontent.com",
    anatomy_observer: Optional[Any] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    state_revision, state_raw = fetch_immutable_source(
        SECOND_BRAIN_REPOSITORY,
        SECOND_BRAIN_STATE_PATH,
        token=token,
        api_url=api_url,
        raw_url=raw_url,
    )
    candidates_revision, candidate_raw = fetch_immutable_source(
        SECOND_BRAIN_REPOSITORY,
        SECOND_BRAIN_CANDIDATES_PATH,
        token=token,
        api_url=api_url,
        raw_url=raw_url,
    )
    if state_revision != candidates_revision:
        raise LoopBoundaryError("Second Brain state and candidates are not revision-aligned")
    state = json.loads(state_raw)
    candidates = parse_candidate_lines(candidate_raw)
    measured_candidate_digest = candidate_set_digest(candidates)
    if state.get("schema") != "szl.second-brain.frontier-state/v1":
        raise LoopBoundaryError("Second Brain frontier state schema is unsupported")
    if state.get("state") != "REVIEW_REQUIRED":
        raise LoopBoundaryError("Second Brain frontier state is not review-required")
    if state.get("candidate_set_sha256") != measured_candidate_digest:
        raise LoopBoundaryError("Second Brain candidate set digest drifted")
    if state.get("training_authority") != "NONE":
        raise LoopBoundaryError("Second Brain unexpectedly grants training authority")
    if state.get("promotion_authority") != "NONE":
        raise LoopBoundaryError("Second Brain unexpectedly grants promotion authority")
    if state.get("execution_authority") != "NONE":
        raise LoopBoundaryError("Second Brain unexpectedly grants execution authority")

    formula_revision, formula_raw = fetch_immutable_source(
        FORMULA_REPOSITORY,
        FORMULA_PATH,
        token=token,
        api_url=api_url,
        raw_url=raw_url,
    )
    formula = json.loads(formula_raw)
    authority = formula.get("authority") if isinstance(formula, dict) else None
    summary = formula.get("summary") if isinstance(formula, dict) else None
    if formula.get("schema") != "szl.formula-quant-atlas/v1":
        raise LoopBoundaryError("formula atlas schema is unsupported")
    if not isinstance(authority, dict) or not isinstance(summary, dict):
        raise LoopBoundaryError("formula atlas authority or summary is missing")
    if authority.get("locked_proven_count") != 8:
        raise LoopBoundaryError("locked-proven formula count drifted")
    if authority.get("lambda_status") != "CONJECTURE_1_OPEN_ADVISORY_ONLY":
        raise LoopBoundaryError("Lambda honesty state drifted")
    if summary.get("attributed_formula_count") != 30:
        raise LoopBoundaryError("attributed formula count drifted")
    if summary.get("executable_formula_count") != 21:
        raise LoopBoundaryError("executable formula count drifted")

    observer = anatomy_observer or observe_anatomy
    anatomy = observer()
    core: Dict[str, Any] = {
        "schema": "szl.ouroboros.continuous-frontier-context/v1",
        "state": "READY_FOR_READ_ONLY_CODEX_REVIEW",
        "loop_stages": list(LOOP_STAGES),
        "max_cycles": MAX_CYCLES,
        "second_brain": {
            "repository": SECOND_BRAIN_REPOSITORY,
            "revision": state_revision,
            "state_path": SECOND_BRAIN_STATE_PATH,
            "candidates_path": SECOND_BRAIN_CANDIDATES_PATH,
            "state_sha256": sha256_bytes(state_raw),
            "candidate_bytes_sha256": sha256_bytes(candidate_raw),
            "candidate_set_sha256": measured_candidate_digest,
            "candidate_count": len(candidates),
            "state": "REVIEW_REQUIRED",
            "content_access": "PUBLIC_SOURCE_CONTEXT_FOR_SANDBOXED_REVIEW",
            "private_graph_nodes_loaded": 0,
        },
        "formula_quant_atlas": {
            "repository": FORMULA_REPOSITORY,
            "revision": formula_revision,
            "path": FORMULA_PATH,
            "sha256": sha256_bytes(formula_raw),
            "summary": summary,
            "authority": authority,
        },
        "anatomy_observations": anatomy,
        "local_ouroboros_kernel": inspect_local_kernel(),
        "authority": dict(AUTHORITY),
        "required_output_state": ["PROPOSAL", "NO_CHANGE", "BLOCKED"],
        "doctrine": [
            "Evidence before claim.",
            "A source handle is not correctness.",
            "Lambda remains Conjecture 1 and advisory only.",
            "Exactly eight formulas are locked-proven; status strings do not promote formulas.",
            "Codex may reason and propose but may not execute, merge, deploy, train, or mutate providers.",
            "Human review is required before any candidate is promoted into durable memory or code.",
        ],
    }
    core["context_sha256"] = sha256_bytes(canonical_bytes(core))
    return core, candidates


def write_context(
    context: Dict[str, Any],
    candidates: Sequence[Dict[str, Any]],
    *,
    context_path: Path,
    candidates_path: Path,
) -> None:
    context_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(
        json.dumps(context, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    candidates_path.write_bytes(
        b"".join(canonical_bytes(row) + b"\n" for row in candidates)
    )


def walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def require_string(value: Any, field: str, *, maximum: int = MAX_STRING) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LoopBoundaryError(field + " must be a non-empty string")
    text = value.strip()
    if len(text) > maximum:
        raise LoopBoundaryError(field + " exceeded the maximum length")
    return text


def validate_output(
    proposal: Any,
    context: Dict[str, Any],
    candidates: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(proposal, dict):
        raise LoopBoundaryError("Codex output must be a JSON object")
    if proposal.get("schema") != "szl.ouroboros.codex-frontier-proposal/v1":
        raise LoopBoundaryError("Codex proposal schema is unsupported")
    state = proposal.get("state")
    if state not in {"PROPOSAL", "NO_CHANGE", "BLOCKED"}:
        raise LoopBoundaryError("Codex proposal state is invalid")
    expected_digest = context["second_brain"]["candidate_set_sha256"]
    if proposal.get("candidate_set_sha256") != expected_digest:
        raise LoopBoundaryError("Codex proposal is not bound to the candidate set")
    if proposal.get("context_sha256") != context.get("context_sha256"):
        raise LoopBoundaryError("Codex proposal is not bound to the loop context")
    if proposal.get("authority") != AUTHORITY:
        raise LoopBoundaryError("Codex proposal authority boundary drifted")

    candidate_ids = {str(row["id"]) for row in candidates}
    cycles = proposal.get("cycles")
    if not isinstance(cycles, list) or len(cycles) > MAX_CYCLES:
        raise LoopBoundaryError("Codex cycles are missing or exceed the maximum")
    if state == "PROPOSAL" and not cycles:
        raise LoopBoundaryError("a proposal requires at least one bounded cycle")
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, dict):
            raise LoopBoundaryError("each Codex cycle must be an object")
        if cycle.get("cycle") != index + 1:
            raise LoopBoundaryError("Codex cycle numbering is not contiguous")
        for field in ("observation", "hypothesis", "challenge", "revision"):
            require_string(cycle.get(field), "cycles." + field, maximum=2_000)
        handles = cycle.get("evidence_handles")
        if not isinstance(handles, list) or not handles:
            raise LoopBoundaryError("each Codex cycle requires evidence handles")
        if len(handles) > 12:
            raise LoopBoundaryError("a Codex cycle references too many handles")
        if any(str(handle) not in candidate_ids for handle in handles):
            raise LoopBoundaryError("Codex referenced an unknown evidence handle")

    convergence = proposal.get("convergence")
    if not isinstance(convergence, dict):
        raise LoopBoundaryError("Codex convergence record is missing")
    if convergence.get("state") not in {
        "CONVERGED_TO_REVIEW_PROPOSAL",
        "NO_CHANGE",
        "BLOCKED",
    }:
        raise LoopBoundaryError("Codex convergence state is invalid")
    require_string(convergence.get("stopping_reason"), "convergence.stopping_reason")

    recommendation = proposal.get("recommendation")
    if not isinstance(recommendation, dict):
        raise LoopBoundaryError("Codex recommendation is missing")
    for field in ("title", "problem", "smallest_safe_change", "target_repository"):
        require_string(recommendation.get(field), "recommendation." + field, maximum=3_000)
    target_repository = recommendation["target_repository"]
    if not re.fullmatch(r"szl-holdings/[A-Za-z0-9_.-]+", target_repository):
        raise LoopBoundaryError("Codex target repository is outside SZL Holdings")
    paths = recommendation.get("target_paths")
    tests = recommendation.get("acceptance_tests")
    risks = recommendation.get("risks")
    for field, value, maximum in (
        ("target_paths", paths, 12),
        ("acceptance_tests", tests, 16),
        ("risks", risks, 12),
    ):
        if not isinstance(value, list) or len(value) > maximum:
            raise LoopBoundaryError("recommendation." + field + " is invalid")
        for item in value:
            require_string(item, "recommendation." + field, maximum=1_000)
    if state == "PROPOSAL" and (not paths or not tests):
        raise LoopBoundaryError("a proposal requires target paths and acceptance tests")

    for text in walk_strings(proposal):
        reject_secret_like(text, label="Codex proposal")
        lowered = text.lower()
        if len(text) > MAX_STRING:
            raise LoopBoundaryError("Codex output contains an oversized string")
        if any(
            prohibited in lowered
            for prohibited in (
                "bypass branch protection",
                "disable branch protection",
                "exfiltrate",
                "steal credential",
                "private key value",
                "auto-merge without review",
                "automerge without review",
                "execute production command",
            )
        ):
            raise LoopBoundaryError("Codex proposal contains prohibited authority language")

    canonical = json.loads(canonical_bytes(proposal))
    canonical["proposal_sha256"] = sha256_bytes(canonical_bytes(canonical))
    return canonical


def write_validated(
    proposal: Dict[str, Any],
    *,
    proposal_path: Path,
    receipt_path: Path,
    run_id: str,
    run_attempt: int,
) -> None:
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_payload = (
        json.dumps(proposal, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    proposal_path.write_bytes(proposal_payload)
    receipt = {
        "schema": "szl.ouroboros.codex-frontier-receipt/v1",
        "observed_at": utc_now(),
        "run_id": run_id,
        "run_attempt": run_attempt,
        "state": proposal["state"],
        "proposal_sha256": sha256_bytes(proposal_payload),
        "candidate_set_sha256": proposal["candidate_set_sha256"],
        "context_sha256": proposal["context_sha256"],
        "cycle_count": len(proposal["cycles"]),
        "authority": dict(AUTHORITY),
        "codex_output_validated": True,
        "automatic_merge_performed": False,
        "production_execution_performed": False,
    }
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_blocked(
    context: Dict[str, Any],
    *,
    proposal_path: Path,
    receipt_path: Path,
    reason: str,
    run_id: str,
    run_attempt: int,
) -> None:
    proposal = {
        "schema": "szl.ouroboros.codex-frontier-proposal/v1",
        "state": "BLOCKED",
        "candidate_set_sha256": context["second_brain"]["candidate_set_sha256"],
        "context_sha256": context["context_sha256"],
        "cycles": [],
        "convergence": {
            "state": "BLOCKED",
            "stopping_reason": reason,
        },
        "recommendation": {
            "title": "Codex frontier review unavailable",
            "problem": reason,
            "smallest_safe_change": "Restore the repository-scoped OpenAI API secret and rerun the bounded workflow.",
            "target_repository": "szl-holdings/szl-ouroboros",
            "target_paths": [],
            "acceptance_tests": [],
            "risks": ["No model-assisted frontier proposal was produced in this run."],
        },
        "authority": dict(AUTHORITY),
    }
    proposal["proposal_sha256"] = sha256_bytes(canonical_bytes(proposal))
    write_validated(
        proposal,
        proposal_path=proposal_path,
        receipt_path=receipt_path,
        run_id=run_id,
        run_attempt=run_attempt,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-context")
    build.add_argument("--context", type=Path, required=True)
    build.add_argument("--candidates", type=Path, required=True)
    build.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    build.add_argument("--raw-url", default="https://raw.githubusercontent.com")

    validate = subparsers.add_parser("validate-output")
    validate.add_argument("--context", type=Path, required=True)
    validate.add_argument("--candidates", type=Path, required=True)
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--proposal", type=Path, required=True)
    validate.add_argument("--receipt", type=Path, required=True)

    blocked = subparsers.add_parser("write-blocked")
    blocked.add_argument("--context", type=Path, required=True)
    blocked.add_argument("--proposal", type=Path, required=True)
    blocked.add_argument("--receipt", type=Path, required=True)
    blocked.add_argument("--reason", required=True)

    args = parser.parse_args()
    run_id = os.environ.get("GITHUB_RUN_ID", "LOCAL")
    try:
        run_attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    except ValueError:
        run_attempt = 1

    if args.command == "build-context":
        token = os.environ.get("GITHUB_TOKEN", "").strip() or None
        context, candidates = build_context(
            token=token,
            api_url=args.api_url,
            raw_url=args.raw_url,
        )
        write_context(
            context,
            candidates,
            context_path=args.context,
            candidates_path=args.candidates,
        )
        print(
            json.dumps(
                {
                    "context_sha256": context["context_sha256"],
                    "candidate_set_sha256": context["second_brain"]["candidate_set_sha256"],
                    "candidate_count": len(candidates),
                },
                sort_keys=True,
            )
        )
        return 0

    context = json.loads(args.context.read_text(encoding="utf-8"))
    if args.command == "write-blocked":
        write_blocked(
            context,
            proposal_path=args.proposal,
            receipt_path=args.receipt,
            reason=args.reason,
            run_id=run_id,
            run_attempt=run_attempt,
        )
        return 0

    candidates = parse_candidate_lines(args.candidates.read_bytes())
    raw_output = args.input.read_text(encoding="utf-8").strip()
    reject_secret_like(raw_output, label="Codex raw output")
    try:
        output = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise LoopBoundaryError("Codex did not emit valid JSON") from exc
    validated = validate_output(output, context, candidates)
    write_validated(
        validated,
        proposal_path=args.proposal,
        receipt_path=args.receipt,
        run_id=run_id,
        run_attempt=run_attempt,
    )
    print(
        json.dumps(
            {
                "state": validated["state"],
                "proposal_sha256": validated["proposal_sha256"],
                "cycle_count": len(validated["cycles"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
