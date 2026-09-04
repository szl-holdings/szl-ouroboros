from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "codex-frontier-review.yml"


def test_missing_optional_codex_authority_is_an_explicit_terminal_state() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "Detect optional Codex API authority" in workflow
    assert 'echo "available=false" >> "$GITHUB_OUTPUT"' in workflow
    assert "CODEX_UNAVAILABLE_MISSING_AUTHORITY" in workflow
    assert '"recommendations_fabricated": False' in workflow
    assert '"terminal_without_red_schedule": state == "CODEX_UNAVAILABLE_MISSING_AUTHORITY"' in workflow

    # Missing optional credentials must not make the scheduled review red. A real
    # action/pipeline failure still fails closed after its receipt is retained.
    assert "Fail closed when configured Codex execution failed" in workflow
    assert "needs.codex.outputs.state == 'CODEX_ACTION_FAILED'" in workflow
    assert "Fail closed when a requested Codex pass was unavailable" not in workflow


def test_codex_action_remains_read_only_and_real_failures_are_observable() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "openai/codex-action@86365089eb2b84e0a8fb0717b304f8bdcb13b20e" in workflow
    assert 'permission-profile: ":read-only"' in workflow
    assert "safety-strategy: drop-sudo" in workflow
    assert "continue-on-error: true" in workflow
    assert "CODEX_ACTION_FAILED" in workflow
    assert "gh pr merge" not in workflow
    assert "git push" not in workflow
