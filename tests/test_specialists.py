"""Automated tests for Hermes-Omni domain specialists."""

from pathlib import Path
import pytest

from omni_core.specialists.os_godmode_agent import OSGodModeAgent
from omni_core.specialists.data_db_agent import DataDBAgent
from omni_core.specialists.research_web_agent import ResearchWebAgent


@pytest.mark.asyncio
async def test_os_godmode_execution():
    """Verify safe execution of benign commands in OS GodMode."""
    agent = OSGodModeAgent()
    res = await agent.execute_command("echo 'Hermes-Omni Specialist Online'", target_shell="powershell")
    assert res.executed is True
    assert "Hermes-Omni Specialist Online" in res.stdout


@pytest.mark.asyncio
async def test_os_godmode_quarantine():
    """Verify destructive command gets quarantined with token."""
    agent = OSGodModeAgent()
    res = await agent.execute_command("rm -rf /mnt/c/System32", target_shell="powershell")
    assert res.executed is False
    assert res.safety_tier == "tier3_red"
    assert res.quarantine_token is not None


@pytest.mark.asyncio
async def test_data_db_agent():
    """Verify database initialization and safe query execution."""
    agent = DataDBAgent()
    initialized = await agent.initialize_sqlite_tables()
    assert initialized is True

    # Safe SELECT query
    res = await agent.execute_safe_query("SELECT count(*) as count FROM telemetry_records")
    assert res.success is True
    assert res.rows[0]["count"] >= 0

    # Destructive DROP TABLE must be quarantined
    drop_res = await agent.execute_safe_query("DROP TABLE telemetry_records")
    assert drop_res.quarantined is True
    assert drop_res.quarantine_token is not None


def test_research_web_html_sanitizer():
    """Verify that script tags and styles are removed from HTML."""
    html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <script>alert('xss');</script>
        <h1>Documentation Header</h1>
        <p>This is a paragraph with a <a href="https://example.com">link</a>.</p>
      </body>
    </html>
    """
    clean = ResearchWebAgent._html_to_markdown(html)
    assert "alert" not in clean
    assert "body {" not in clean
    assert "Documentation Header" in clean
    assert "[link](https://example.com)" in clean
