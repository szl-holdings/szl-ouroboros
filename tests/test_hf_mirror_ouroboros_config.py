"""Repo-specific contract for the ported release mirror (stdlib + pytest only).

The shared publisher contract lives in test_hf_mirror_oidc_contract.py. This
file pins what is specific to SZLHOLDINGS/szl-ouroboros: the target map derived
from the live Hub card, the Hub paths the mirror must never overwrite, the
staging excludes, and the workflow hardening that replaced the legacy lane.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "hf-mirror.yml"
CONFIG = ROOT / ".github" / "hf-mirror.json"
PUBLISHER = ROOT / "scripts" / "hf_mirror_release.py"
RENDERER = ROOT / "scripts" / "render_model_card.py"

_spec = importlib.util.spec_from_file_location("hf_mirror_release_ouroboros", PUBLISHER)
assert _spec and _spec.loader
mirror = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mirror)

# Pins proven by szl-holdings/szl-lambda-gate@29a0bd9 (run 36154245684).
PROVEN_PINS = {
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "huggingface/hub-sync@fdffea8e04104d0bd4e3181c5feb3025f0433ff5",
}


def _target() -> dict:
    targets = json.loads(CONFIG.read_text(encoding="utf-8"))["targets"]
    assert len(targets) == 1
    return targets[0]


def _run_blocks(text: str) -> list[str]:
    """Return the body of every `run:` key (inline or block scalar)."""
    lines = text.splitlines()
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", lines[i])
        if not match:
            i += 1
            continue
        indent = len(match.group(1))
        inline = match.group(2).strip()
        if inline and inline[0] not in "|>":
            blocks.append(inline)
            i += 1
            continue
        body = []
        i += 1
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
            body.append(lines[i])
            i += 1
        blocks.append("\n".join(body))
    return blocks


def test_target_is_derived_from_live_hub_card() -> None:
    item = _target()
    assert item["slug"] == "ouroboros"
    assert item["hf_repo_id"] == "SZLHOLDINGS/szl-ouroboros"
    assert item["oidc_resource"] == item["hf_repo_id"]
    assert item["repo_type"] == "model"
    assert item["subdirectory"] == "."
    assert item["mirror_on_push"] is False
    assert item["preserve_hub_card"] is True
    assert item["required_card_metadata"] == {"library_name": "kernels", "license": "apache-2.0"}
    assert item["required_card_tags"] == ["doi:10.5281/zenodo.19944926"]


def test_preserve_paths_are_exact_unique_safe_files() -> None:
    paths = _target()["preserve_hub_paths"]
    assert len(paths) == len(set(paths))
    assert "README.md" not in paths
    for name in paths:
        assert not name.endswith("/"), name
        assert mirror.safe_relative(name).as_posix() == name


def test_stage_drops_preserved_hub_paths_and_keeps_package(tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "hf-mirror.json").write_bytes(CONFIG.read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HF_REPO_ID", "SZLHOLDINGS/szl-ouroboros")
    monkeypatch.setenv("HF_REPO_TYPE", "model")
    kept = [
        "README.md",
        "NOTICE",
        "pyproject.toml",
        "build/torch-universal/szl_ouroboros/__init__.py",
        "torch-ext/szl_ouroboros/__init__.py",
        "torch-ext/szl_ouroboros/metadata.json",
    ]
    dropped = ["LICENSE", "SECURITY.md", "build.toml", "build/torch-universal/szl_ouroboros/metadata.json"]
    for name in kept + dropped:
        path = mirror.STAGE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")

    mirror.stage()

    assert sorted(mirror.stage_files()) == sorted(kept)


def test_stage_fails_closed_without_readme(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "hf-mirror.json").write_bytes(CONFIG.read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HF_REPO_ID", "SZLHOLDINGS/szl-ouroboros")
    monkeypatch.setenv("HF_REPO_TYPE", "model")
    (mirror.STAGE / "torch-ext").mkdir(parents=True)
    (mirror.STAGE / "torch-ext" / "x.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="README.md missing"):
        mirror.stage()


def test_staging_excludes_github_only_automation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    excludes = set(re.findall(r"--exclude '([^']+)'", text))
    assert {".git", ".github", ".hfstage", "tests", "__pycache__"} <= excludes
    assert {"/codex/", "/prompts/", "/schemas/", "/scripts/"} <= excludes


def test_run_scripts_never_interpolate_secrets_inputs_or_event_text() -> None:
    blocks = _run_blocks(WORKFLOW.read_text(encoding="utf-8"))
    assert len(blocks) >= 8
    for body in blocks:
        assert "${{" not in body, body


def test_every_action_uses_a_proven_full_sha_pin() -> None:
    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW.read_text(encoding="utf-8"))
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref
        assert ref in PROVEN_PINS, ref


def test_legacy_lane_defects_are_absent() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    publisher = PUBLISHER.read_text(encoding="utf-8")
    renderer = RENDERER.read_text(encoding="utf-8")
    top_permissions = workflow.split("\npermissions:\n", 1)[1].split("\n\n", 1)[0]
    assert top_permissions.strip() == "contents: read"
    assert "HF_OIDC_RESOURCE: ${{ matrix.target.oidc_resource }}" in workflow
    assert "only='${{" not in workflow
    assert "ONLY: ${{ inputs.only }}" in workflow
    assert "hf auth whoami" not in workflow
    assert "--clobber" not in workflow
    assert "delete_tag" not in workflow + publisher
    assert re.search(r"create_tag\([^)]*exist_ok=True", workflow + publisher, re.S) is None
    assert re.search(r"create_tag\([^)]*exist_ok=False", publisher, re.S) is not None
    assert "from_template" not in renderer
    assert "cp -f LICENSE" not in workflow
