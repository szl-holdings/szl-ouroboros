#!/usr/bin/env python3
"""Open a Hub PR that deletes model.joblib at an exact parent_commit.

Requires HF_TOKEN in the environment (GitHub Actions secret). Never prints the token.
Exit 2 if the token is missing — UNAVAILABLE, not success.
"""
from __future__ import annotations

import os
import sys

REPO_ID = os.environ.get("HUB_REPO_ID", "SZLHOLDINGS/szl-ouroboros")


def main() -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HF_ORG_TOKEN")
    if not token:
        print("UNAVAILABLE: HF_TOKEN/HF_ORG_TOKEN not present in this runner")
        return 2
    try:
        from huggingface_hub import HfApi, CommitOperationDelete
    except ImportError:
        print("UNAVAILABLE: huggingface_hub not installed")
        return 2

    api = HfApi(token=token)
    info = api.repo_info(repo_id=REPO_ID, repo_type="model")
    parent = info.sha
    siblings = {s.rfilename for s in (info.siblings or [])}
    if "model.joblib" not in siblings:
        print(f"VERIFIED_CURRENT: {REPO_ID}@{parent} has no model.joblib")
        return 0
    ops = [
        CommitOperationDelete(path_in_repo="model.joblib"),
    ]
    commit = api.create_commit(
        repo_id=REPO_ID,
        repo_type="model",
        operations=ops,
        commit_message="quarantine: remove model.joblib from approved path",
        create_pr=True,
        parent_commit=parent,
    )
    print(f"Hub PR opened for {REPO_ID} parent={parent} result={commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
