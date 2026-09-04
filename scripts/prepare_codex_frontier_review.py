#!/usr/bin/env python3
"""Prepare an exact, bounded Second Brain packet for scheduled Codex review.

The source repository and admitted paths are fixed. This operator resolves the
current protected-main commit, fetches two immutable public files, validates every
candidate and digest, and writes a secret-free source receipt. It never fetches a
private graph, executes candidate content, or grants mutation authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SOURCE_REPOSITORY = "szl-holdings/szl-second-brain"
SOURCE_REF = "main"
STATE_PATH = "data/frontier-state.v1.json"
CANDIDATES_PATH = "data/frontier-candidates.public.jsonl"
STATE_SCHEMA = "szl.second-brain.frontier-state/v1"
CANDIDATE_SCHEMA = "szl.second-brain.frontier-candidate/v1"
USER_AGENT = "szl-ouroboros-codex-frontier-review/1.0"
MAX_STATE_BYTES = 512 * 1024
MAX_CANDIDATE_BYTES = 4 * 1024 * 1024
MAX_REVIEW_CANDIDATES = 64
MAX_REVIEW_EXCERPT_CHARS = 2_000
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
CANDIDATE_ID = re.compile(r"^frontier:[0-9a-f]{32}$")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class SnapshotError(RuntimeError):
    """The exact source snapshot violated the bounded review contract."""


class PacketError(SnapshotError):
    """The upstream public candidate packet violated its declared contract."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def request_bytes(url: str, *, token: str | None, limit: int) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json, application/json, text/plain;q=0.9, */*;q=0.8",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read(limit + 1)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise PacketError(f"public source fetch failed: {type(exc).__name__}") from exc
    if len(payload) > limit:
        raise PacketError(f"public source response exceeded {limit} bytes")
    return payload


def github_json(url: str, token: str | None) -> Any:
    try:
        raw = request_bytes(url, token=token, limit=MAX_STATE_BYTES)
    except PacketError:
        if not token:
            raise
        raw = request_bytes(url, token=None, limit=MAX_STATE_BYTES)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PacketError("GitHub returned invalid JSON") from exc


def resolve_source_revision(
    *,
    token: str | None,
    api_url: str = "https://api.github.com",
) -> str:
    payload = github_json(
        f"{api_url.rstrip('/')}/repos/{SOURCE_REPOSITORY}/commits/{SOURCE_REF}",
        token,
    )
    revision = str(payload.get("sha") or "").lower() if isinstance(payload, dict) else ""
    if not HEX_40.fullmatch(revision):
        raise PacketError("Second Brain main did not resolve to an exact revision")
    return revision


def fetch_immutable_files(
    revision: str,
    *,
    raw_url: str = "https://raw.githubusercontent.com",
) -> tuple[bytes, bytes]:
    root = f"{raw_url.rstrip('/')}/{SOURCE_REPOSITORY}/{revision}"
    state = request_bytes(
        f"{root}/{STATE_PATH}",
        token=None,
        limit=MAX_STATE_BYTES,
    )
    candidates = request_bytes(
        f"{root}/{CANDIDATES_PATH}",
        token=None,
        limit=MAX_CANDIDATE_BYTES,
    )
    return state, candidates


def reject_secret_like_material(text: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise PacketError("secret-like material rejected from frontier packet")


def reject_secret_like(text: str) -> None:
    """Reject secret-shaped text without echoing the rejected value."""

    reject_secret_like_material(text)


def validate_packet(
    state_raw: bytes,
    candidates_raw: bytes,
    *,
    required_source_count: int | None = 6,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        state = json.loads(state_raw)
    except json.JSONDecodeError as exc:
        raise PacketError("frontier state is invalid JSON") from exc
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        raise PacketError("frontier state schema mismatch")
    expected = {
        "state": "REVIEW_REQUIRED",
        "public_content_access": "HANDLES_ONLY",
        "controller_content_access": "AUTHORIZED_CONTROLLER_ONLY",
        "training_authority": "NONE",
        "promotion_authority": "NONE",
        "execution_authority": "NONE",
        "merge_authority": "NONE",
        "lambda": "CONJECTURE_1",
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise PacketError(f"frontier authority drift: {key}")
    if int(state.get("private_graph_nodes_loaded") or 0) != 0:
        raise PacketError("private graph material entered the frontier state")
    if int(state.get("raw_graph_nodes_admitted_to_gradients") or 0) != 0:
        raise PacketError("frontier state admitted raw graph nodes to gradients")
    try:
        source_count = int(state.get("source_count") or 0)
    except (TypeError, ValueError) as exc:
        raise PacketError("frontier source count is invalid") from exc
    if source_count <= 0:
        raise PacketError("frontier source count is invalid")
    if required_source_count is not None and source_count != required_source_count:
        raise PacketError("frontier source count drifted")

    reject_secret_like_material(candidates_raw.decode("utf-8"))
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    canonical_lines: list[bytes] = []
    for line_number, line in enumerate(candidates_raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PacketError(f"candidate line {line_number} is invalid JSON") from exc
        if not isinstance(row, dict) or row.get("schema") != CANDIDATE_SCHEMA:
            raise PacketError(f"candidate line {line_number} has the wrong schema")
        candidate_id = str(row.get("id") or "")
        if not CANDIDATE_ID.fullmatch(candidate_id) or candidate_id in seen_ids:
            raise PacketError(f"candidate identity failed at line {line_number}")
        seen_ids.add(candidate_id)
        revision = str(row.get("source_revision") or "")
        digest = str(row.get("content_sha256") or "")
        if not HEX_40.fullmatch(revision) or not HEX_64.fullmatch(digest):
            raise PacketError(f"candidate source binding failed at line {line_number}")
        content = str(row.get("content") or "")
        if sha256_bytes(content.encode("utf-8")) != digest:
            raise PacketError(f"candidate digest failed at line {line_number}")
        if row.get("candidate_state") != "DISCOVERED_REVIEW_REQUIRED":
            raise PacketError(f"candidate was promoted at line {line_number}")
        if row.get("content_access") != "CONTROLLER_ONLY":
            raise PacketError(f"candidate content boundary drifted at line {line_number}")
        rows.append(row)
        canonical_lines.append(canonical_bytes(row) + b"\n")

    declared_count = int(state.get("candidate_count") or -1)
    if declared_count != len(rows) or len(rows) == 0:
        raise PacketError("candidate count mismatch")
    measured_set = sha256_bytes(b"".join(canonical_lines))
    if state.get("candidate_set_sha256") != measured_set:
        raise PacketError("candidate-set digest mismatch")
    if not HEX_64.fullmatch(str(state.get("state_sha256") or "")):
        raise PacketError("frontier state digest is malformed")
    return state, rows


def build_input(
    revision: str,
    state_raw: bytes,
    candidates_raw: bytes,
    *,
    required_source_count: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build one bounded, digest-linked input and its source receipt."""

    revision = revision.lower()
    if not HEX_40.fullmatch(revision):
        raise SnapshotError("source revision is not an exact Git commit")
    state, rows = validate_packet(
        state_raw,
        candidates_raw,
        required_source_count=required_source_count,
    )
    selected_rows = rows[:MAX_REVIEW_CANDIDATES]
    candidates: list[dict[str, Any]] = []
    for row in selected_rows:
        content = str(row.get("content") or "")
        reject_secret_like(content)
        candidate: dict[str, Any] = {
            "handle": row["id"],
            "title": str(row.get("title") or ""),
            "source_repository": str(row.get("source_repository") or ""),
            "source_revision": row["source_revision"],
            "source_path": str(row.get("source_path") or ""),
            "source_kind": str(row.get("source_kind") or ""),
            "content_sha256": row["content_sha256"],
            "candidate_state": row["candidate_state"],
            "admission": str(row.get("admission") or ""),
            "untrusted_evidence_excerpt": content[:MAX_REVIEW_EXCERPT_CHARS],
        }
        quant_domain = row.get("quant_domain")
        if quant_domain is not None:
            candidate["quant_domain"] = str(quant_domain)
        candidates.append(candidate)

    authority = {
        "mode": "REVIEW_ONLY",
        "content_access": "PUBLIC_CANDIDATES_READ_ONLY",
        "private_graph_used": False,
        "training": "NONE",
        "promotion": "NONE",
        "execution": "NONE",
        "merge": "NONE",
        "provider_mutation": "NONE",
    }
    payload: dict[str, Any] = {
        "schema": "szl.ouroboros.codex-frontier-input/v1",
        "source": {
            "repository": SOURCE_REPOSITORY,
            "ref": SOURCE_REF,
            "revision": revision,
            "state_path": STATE_PATH,
            "state_sha256": sha256_bytes(state_raw),
            "candidates_path": CANDIDATES_PATH,
            "candidates_sha256": sha256_bytes(candidates_raw),
            "candidate_set_sha256": state["candidate_set_sha256"],
            "source_count": int(state["source_count"]),
            "lambda": state["lambda"],
        },
        "selection": {
            "total_candidate_count": len(rows),
            "selected_candidate_count": len(candidates),
            "maximum_candidate_count": MAX_REVIEW_CANDIDATES,
            "selection_order": "SOURCE_ORDER",
        },
        "candidates": candidates,
        "authority": authority,
    }
    payload["input_sha256"] = sha256_bytes(canonical_bytes(payload))

    receipt: dict[str, Any] = {
        "schema": "szl.ouroboros.codex-frontier-source/v1",
        "state": "VERIFIED_EXACT_SOURCE_SNAPSHOT",
        "source_repository": SOURCE_REPOSITORY,
        "source_ref": SOURCE_REF,
        "source_revision": revision,
        "state_path": STATE_PATH,
        "state_sha256": sha256_bytes(state_raw),
        "candidates_path": CANDIDATES_PATH,
        "candidates_sha256": sha256_bytes(candidates_raw),
        "candidate_set_sha256": state["candidate_set_sha256"],
        "total_candidate_count": len(rows),
        "selected_candidate_count": len(candidates),
        "input_sha256": payload["input_sha256"],
        "authority": authority,
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))
    return payload, receipt


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def prepare(
    output: Path,
    *,
    token: str | None,
    api_url: str = "https://api.github.com",
    raw_url: str = "https://raw.githubusercontent.com",
) -> dict[str, Any]:
    revision = resolve_source_revision(token=token, api_url=api_url)
    state_raw, candidates_raw = fetch_immutable_files(revision, raw_url=raw_url)
    state, rows = validate_packet(state_raw, candidates_raw)
    receipt_core: dict[str, Any] = {
        "schema": "szl.ouroboros.codex-frontier-source/v1",
        "source_repository": SOURCE_REPOSITORY,
        "source_ref": SOURCE_REF,
        "source_revision": revision,
        "state_path": STATE_PATH,
        "state_sha256": sha256_bytes(state_raw),
        "candidates_path": CANDIDATES_PATH,
        "candidates_sha256": sha256_bytes(candidates_raw),
        "candidate_count": len(rows),
        "candidate_set_sha256": state["candidate_set_sha256"],
        "source_count": state["source_count"],
        "candidate_state": "DISCOVERED_REVIEW_REQUIRED",
        "content_scope": "PUBLIC_SOURCE_REVIEW_MATERIAL",
        "authority": {
            "training": "NONE",
            "promotion": "NONE",
            "execution": "NONE",
            "merge": "NONE",
            "provider_mutation": "NONE",
        },
    }
    receipt_core["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt_core))
    atomic_write(output / "frontier-state.v1.json", state_raw)
    atomic_write(output / "frontier-candidates.public.jsonl", candidates_raw)
    atomic_write(
        output / "source-receipt.json",
        (json.dumps(receipt_core, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    return receipt_core


def prepare_review(
    input_path: Path,
    receipt_path: Path,
    *,
    token: str | None,
    api_url: str = "https://api.github.com",
    raw_url: str = "https://raw.githubusercontent.com",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch, verify, and atomically materialize a review-only source snapshot."""

    revision = resolve_source_revision(token=token, api_url=api_url)
    state_raw, candidates_raw = fetch_immutable_files(revision, raw_url=raw_url)
    payload, receipt = build_input(
        revision,
        state_raw,
        candidates_raw,
        required_source_count=6,
    )
    atomic_write(
        input_path,
        (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )
    atomic_write(
        receipt_path,
        (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    return payload, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument(
        "--api-url",
        default=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
    )
    parser.add_argument("--raw-url", default="https://raw.githubusercontent.com")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    if (args.input is None) != (args.receipt is None):
        parser.error("--input and --receipt must be provided together")
    if args.input is not None and args.output is not None:
        parser.error("--output cannot be combined with --input and --receipt")
    if args.input is not None:
        payload, receipt = prepare_review(
            args.input,
            args.receipt,
            token=token,
            api_url=args.api_url,
            raw_url=args.raw_url,
        )
        print(
            json.dumps(
                {
                    "source_revision": payload["source"]["revision"],
                    "candidate_count": payload["selection"]["selected_candidate_count"],
                    "candidate_set_sha256": payload["source"]["candidate_set_sha256"],
                    "input": str(args.input),
                    "receipt": str(args.receipt),
                    "receipt_sha256": receipt["receipt_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    receipt = prepare(
        args.output or Path("inputs"),
        token=token,
        api_url=args.api_url,
        raw_url=args.raw_url,
    )
    print(
        json.dumps(
            {
                "source_revision": receipt["source_revision"],
                "candidate_count": receipt["candidate_count"],
                "candidate_set_sha256": receipt["candidate_set_sha256"],
                "output": str(args.output or Path("inputs")),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
