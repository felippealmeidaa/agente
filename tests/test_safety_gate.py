"""Automated tests for SafetyGate Tiered Policy in Hermes-Omni."""

from omni_core.orchestrator.safety_gate import SafetyGate


def test_safety_gate_tier1_green():
    """Verify that read-only and inspection commands are auto-approved as Tier 1."""
    gate = SafetyGate()

    commands = [
        "git status",
        "git diff HEAD~1",
        "ls -la",
        "pytest -v",
        "SELECT id, name FROM users",
    ]

    for cmd in commands:
        result = gate.evaluate_command(cmd)
        assert result.tier == "tier1_green"
        assert result.is_safe_to_execute is True
        assert result.requires_human_confirmation is False


def test_safety_gate_tier2_yellow():
    """Verify that standard operational commands pass as Tier 2."""
    gate = SafetyGate()

    commands = [
        "pip install requests",
        "docker compose restart redis",
        "echo 'data' > output.txt",
    ]

    for cmd in commands:
        result = gate.evaluate_command(cmd)
        assert result.tier == "tier2_yellow"
        assert result.is_safe_to_execute is True
        assert result.requires_human_confirmation is False


def test_safety_gate_tier3_red_and_token_flow():
    """Verify that destructive actions are blocked into Tier 3 and require token confirmation."""
    gate = SafetyGate()

    destructive_commands = [
        "rm -rf /mnt/c/Users/Felippe/important_dir",
        "Remove-Item -Recurse -Force C:\\Windows",
        "DROP DATABASE production_db",
        "DELETE FROM customers",
        "taskkill /f /im explorer.exe",
    ]

    for cmd in destructive_commands:
        result = gate.evaluate_command(cmd)
        assert result.tier == "tier3_red"
        assert result.is_safe_to_execute is False
        assert result.requires_human_confirmation is True
        assert result.confirmation_token is not None

        # Verify confirmation token resolution
        token = result.confirmation_token
        approved_cmd = gate.confirm_token(token)
        assert approved_cmd == cmd

        # Second attempt with same token must fail (single-use)
        assert gate.confirm_token(token) is None
