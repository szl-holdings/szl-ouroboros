from __future__ import annotations

from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "codex-continuous-frontier.yml"
)


def test_frontier_workflow_binds_exact_source_and_reduced_budget() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert (
        "SOURCE_REVISION: ${{ github.event.pull_request.head.sha || github.sha }}"
        in workflow
    )
    assert workflow.count("ref: ${{ env.SOURCE_REVISION }}") == 2
    assert workflow.count(
        'test "$(git rev-parse HEAD)" = "${SOURCE_REVISION}"'
    ) == 2

    # The measured 24-candidate / 1,800-token live attempts terminated with
    # OUTPUT_TRUNCATED. Twelve candidates preserve the ten-source diversity
    # contract while halving the selected evidence packet. Keep the output
    # ceiling unchanged so this change tests prompt reduction independently.
    assert "--candidate-limit 12" in workflow
    assert "--candidate-limit 24" not in workflow
    assert "--context-tokens 16384" in workflow
    assert "--max-tokens 1800" in workflow
