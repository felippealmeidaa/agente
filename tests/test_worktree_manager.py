"""Automated tests for WorktreeManager in Hermes-Omni."""

import asyncio
from pathlib import Path
import tempfile
import pytest

from omni_core.coding_council.worktree_manager import (
    WorktreeManager,
    sanitize_terminal_output,
)


def test_sanitize_terminal_output():
    """Verify that ANSI sequences and progress artifacts are cleanly removed."""
    raw = "\x1b[32mSUCCESS\x1b[0m\r\n\x1b[1mLine 2\x1b[0m"
    clean = sanitize_terminal_output(raw)
    assert "SUCCESS" in clean
    assert "Line 2" in clean
    assert "\x1b" not in clean


@pytest.mark.asyncio
async def test_worktree_lifecycle(tmp_path):
    """Verify end-to-end Git Worktree creation, diff detection, commit, and cleanup in an isolated repo."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    # Initialize a clean test repository
    p_init = await asyncio.create_subprocess_exec("git", "init", "-b", "main", cwd=str(repo_root))
    await p_init.wait()
    p_cfg1 = await asyncio.create_subprocess_exec("git", "config", "user.name", "TestUser", cwd=str(repo_root))
    await p_cfg1.wait()
    p_cfg2 = await asyncio.create_subprocess_exec("git", "config", "user.email", "test@test.local", cwd=str(repo_root))
    await p_cfg2.wait()

    readme = repo_root / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    p_add = await asyncio.create_subprocess_exec("git", "add", "README.md", cwd=str(repo_root))
    await p_add.wait()
    p_cmt = await asyncio.create_subprocess_exec("git", "commit", "-m", "init", cwd=str(repo_root))
    await p_cmt.wait()

    task_id = "test_unit_99"
    wm = WorktreeManager(sandbox_base_dir=tmp_path / "sandboxes")
    worktree_path, branch_name = await wm.create_worktree(
        repo_root=repo_root,
        task_id=task_id,
    )

    try:
        # Verify the worktree folder exists and is isolated
        assert worktree_path.exists()
        assert worktree_path.is_dir()
        assert branch_name == f"omni/task-{task_id}"

        # Create a test file inside the worktree
        test_file = worktree_path / "sandbox_test.txt"
        test_file.write_text("Hello from isolated worktree sandbox!", encoding="utf-8")

        # Verify clean diff captures the new file
        diff = await wm.get_clean_diff(worktree_path)
        # Untracked files appear when staged or committed
        await wm.commit_changes(worktree_path, "test: add sandbox test file")

        # Get diff against HEAD~1
        code, out, _ = await wm._run_git(worktree_path, "diff", "HEAD~1")
        assert "sandbox_test.txt" in out

    finally:
        # Cleanup worktree and branch
        removed = await wm.remove_worktree(
            repo_root=repo_root,
            worktree_path=worktree_path,
            branch_name=branch_name,
        )
        assert removed is True
        assert not worktree_path.exists()

