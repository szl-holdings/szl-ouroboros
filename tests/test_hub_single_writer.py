# SPDX-License-Identifier: Apache-2.0
"""Single-writer contract for this repository's Hugging Face assets.

SZL HF upgrade plan, decision D1: one asset, one source repository, one
committed writer. In this repository only the files in WRITERS may call a Hub
write API, push to a Hub git remote, or bind a Hugging Face secret. Every other
executable file is at most a reader. A writer that is removed cannot come back
unnoticed, and an allowlisted file that stops writing fails the check, so the
list cannot go stale.

Standard library only (runs under plain `pytest` and `python -I`).
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The committed release mirror (.github/hf-mirror.json): the workflow binds the
# credential, the publisher uploads and tags. The one-shot joblib quarantine
# writer was removed once the Hub held no model.joblib; the source-side guard
# (tests/test_no_unsafe_serialization.py) still refuses it.
WRITERS = frozenset({
    ".github/workflows/hf-mirror.yml",
    "scripts/hf_mirror_release.py",
})

# Executable sources only. Tests, docs and data corpora are not writers.
EXECUTABLE_SUFFIXES = {".py", ".sh", ".bash", ".ps1", ".js", ".mjs", ".cjs", ".ts", ".yml", ".yaml"}
EXCLUDED_DIRS = {".git", "tests", "__pycache__", "node_modules", ".hfstage"}

HUB_WRITE = re.compile(
    r"\b(?:create_commit|create_commits_on_pr|upload_file|upload_folder|upload_large_folder"
    r"|delete_file|delete_files|delete_folder|create_repo|delete_repo|move_repo"
    r"|create_tag|delete_tag|create_branch|delete_branch|create_pull_request"
    r"|merge_pull_request|update_repo_settings|update_repo_visibility"
    r"|add_space_secret|delete_space_secret|add_space_variable|super_squash_history)\s*\("
    r"|\bCommitOperation(?:Add|Delete|Copy)\b"
    r"|\b(?:huggingface-cli|hf)\s+(?:upload|upload-large-folder|repo\s+(?:create|delete)"
    r"|repo-files\s+delete|tag\s+create)\b"
    r"|huggingface/hub-sync@"
    r"|git\s+(?:push|remote\s+add)[^\n]*huggingface\.co"
)
HF_SECRET = re.compile(r"secrets\.(?:HF_[A-Z0-9_]*|HUGGING[A-Z0-9_]*)\b")


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        ).stdout.decode("utf-8")
        names = [name for name in out.split("\0") if name]
    except (OSError, subprocess.CalledProcessError):
        names = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()]
    return sorted(
        name for name in names
        if Path(name).suffix in EXECUTABLE_SUFFIXES
        and not set(Path(name).parts[:-1]) & EXCLUDED_DIRS
        and not Path(name).name.startswith("test_")
        and (ROOT / name).is_file()
    )


def hub_writers() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name in tracked_files():
        text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
        hits = [m.group(0) for m in HUB_WRITE.finditer(text)]
        hits += [m.group(0) for m in HF_SECRET.finditer(text)]
        if hits:
            found[name] = sorted(set(hits))
    return found


class HubSingleWriter(unittest.TestCase):
    def test_only_the_committed_writer_touches_the_hub(self) -> None:
        unexpected = {name: hits for name, hits in hub_writers().items() if name not in WRITERS}
        self.assertEqual(unexpected, {}, "Hub write path outside the committed writer")

    def test_every_listed_writer_still_writes(self) -> None:
        found = hub_writers()
        stale = sorted(name for name in WRITERS if name not in found)
        self.assertEqual(stale, [], "WRITERS lists a file that no longer writes to the Hub")

    def test_detector_sees_known_write_forms(self) -> None:
        for sample in (
            "api.create_commit(repo_id=r, operations=ops)",
            "upload_folder(folder_path='.', repo_id=r)",
            "ops = [CommitOperationDelete(path_in_repo='model.joblib')]",
            "huggingface-cli upload SZLHOLDINGS/x . .",
            "hf upload SZLHOLDINGS/x .",
            "uses: huggingface/hub-sync@fdffea8e04104d0bd4e3181c5feb3025f0433ff5",
            "git push https://user:tok@huggingface.co/SZLHOLDINGS/x main",
        ):
            self.assertRegex(sample, HUB_WRITE)
        self.assertRegex("HF_TOKEN: ${{ secrets.HF_TOKEN || secrets.HF_ORG_TOKEN }}", HF_SECRET)
        for sample in ("hf_hub_download(repo_id=r, filename=f)", "HfApi().repo_info(r)",
                       "snapshot_download(repo_id=r)", "ModelCard.load(path)"):
            self.assertNotRegex(sample, HUB_WRITE)


if __name__ == "__main__":
    unittest.main()
