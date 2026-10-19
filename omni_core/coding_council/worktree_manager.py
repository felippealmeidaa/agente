"""Git Worktree Manager for Isolated Agent Coding Sessions.

Enforces zero-contamination of the user's primary IDE working directory:
- Spawns isolated Git Worktrees in .omni_sandboxes/task_<id>
- Captures sanitized git diffs (free of ANSI escape codes)
- Performs atomic commits and conditional merges back to the target branch
- Safely removes and prunes worktrees on failure or completion
"""

import asyncio
import logging
from pathlib import Path
import re
import shutil
from typing import Optional, Tuple

logger = logging.getLogger("omni_core.coding_council.worktree_manager")

# Regex to strip ANSI escape codes from git and terminal outputs
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def sanitize_terminal_output(text: str) -> str:
    """Remove ANSI escape sequences and non-printable control characters."""
    clean = ANSI_ESCAPE_PATTERN.sub("", text)
    # Replace repeated carriage returns or progress-bar artifacts
    lines = [line.strip("\r") for line in clean.splitlines()]
    return "\n".join(lines)


class WorktreeManager:
    """Manages creation, execution, and cleanup of Git Worktrees."""

    def __init__(self, sandbox_base_dir: Optional[Path] = None):
        self.sandbox_base_dir = (
            sandbox_base_dir
            if sandbox_base_dir
            else Path(".omni_sandboxes").resolve()
        )
        self.sandbox_base_dir.mkdir(parents=True, exist_ok=True)

    async def _run_git(
        self, cwd: Path, *args: str
    ) -> Tuple[int, str, str]:
        """Execute a git command asynchronously in the specified directory."""
        cmd = ["git", *args]
        logger.debug(f"Executing: {' '.join(cmd)} in {cwd}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        out_str = sanitize_terminal_output(stdout.decode(errors="replace"))
        err_str = sanitize_terminal_output(stderr.decode(errors="replace"))
        return process.returncode or 0, out_str, err_str

    async def create_worktree(
        self,
        repo_root: Path,
        task_id: str,
        base_ref: str = "HEAD",
    ) -> Tuple[Path, str]:
        """Create a dedicated, isolated Git worktree for an agent task.

        Returns:
            Tuple[Path, str]: (absolute path to worktree sandbox, branch name)
        """
        repo_root = repo_root.resolve()
        branch_name = f"omni/task-{task_id}"
        worktree_path = (self.sandbox_base_dir / f"task_{task_id}").resolve()

        # If worktree directory already exists, clean it first
        if worktree_path.exists():
            await self.remove_worktree(repo_root, worktree_path, branch_name)

        logger.info(f"Creating Git Worktree at {worktree_path} on branch {branch_name}")

        code, out, err = await self._run_git(
            repo_root,
            "worktree",
            "add",
            "-b",
            branch_name,
            str(worktree_path),
            base_ref,
        )

        if code != 0:
            logger.error(f"Failed to create worktree: {err}")
            raise RuntimeError(f"Git worktree creation failed: {err or out}")

        return worktree_path, branch_name

    async def get_clean_diff(
        self,
        worktree_path: Path,
        max_lines: int = 400,
    ) -> str:
        """Extract a clean, sanitized git diff of all modifications in the worktree."""
        code, out, err = await self._run_git(worktree_path, "diff", "HEAD")
        if code != 0:
            logger.warning(f"Failed to get git diff: {err}")
            return ""

        diff_lines = out.splitlines()
        if len(diff_lines) > max_lines:
            truncated = (
                f"# DIFF TRUNCATED: {len(diff_lines)} lines detected (showing top {max_lines})\n"
                + "\n".join(diff_lines[:max_lines])
                + f"\n# ... [TRUNCATED {len(diff_lines) - max_lines} LINES FOR CONTEXT PROTECTION]"
            )
            return truncated

        return out

    async def commit_changes(
        self,
        worktree_path: Path,
        message: str = "chore(omni): automated council updates",
    ) -> bool:
        """Stage all changes and commit in the worktree sandbox."""
        # Stage all changes
        code, _, err = await self._run_git(worktree_path, "add", "-A")
        if code != 0:
            logger.error(f"Git add failed: {err}")
            return False

        # Check if there is anything to commit
        code, status_out, _ = await self._run_git(worktree_path, "status", "--porcelain")
        if not status_out.strip():
            logger.info("No modifications to commit in worktree.")
            return True

        code, _, err = await self._run_git(
            worktree_path, "commit", "-m", message
        )
        if code != 0:
            logger.error(f"Git commit failed: {err}")
            return False

        logger.info(f"Committed changes in worktree: {message}")
        return True

    async def merge_to_branch(
        self,
        repo_root: Path,
        branch_name: str,
        target_branch: str = "main",
    ) -> bool:
        """Merge the worktree's task branch into the target branch."""
        repo_root = repo_root.resolve()
        logger.info(f"Merging branch {branch_name} into {target_branch}")

        # Checkout target branch
        code, _, err = await self._run_git(repo_root, "checkout", target_branch)
        if code != 0:
            logger.error(f"Failed to checkout {target_branch}: {err}")
            return False

        # Merge branch
        code, out, err = await self._run_git(
            repo_root, "merge", "--no-ff", branch_name, "-m", f"merge: {branch_name}"
        )
        if code != 0:
            logger.error(f"Merge conflict or failure: {err or out}")
            return False

        logger.info(f"Successfully merged {branch_name} into {target_branch}")
        return True

    async def remove_worktree(
        self,
        repo_root: Path,
        worktree_path: Path,
        branch_name: Optional[str] = None,
        delete_branch: bool = True,
    ) -> bool:
        """Remove the worktree sandbox and prune metadata."""
        repo_root = repo_root.resolve()
        worktree_path = worktree_path.resolve()
        logger.info(f"Removing Git Worktree: {worktree_path}")

        # Git worktree remove
        code, _, err = await self._run_git(
            repo_root, "worktree", "remove", "--force", str(worktree_path)
        )
        if code != 0:
            logger.warning(f"git worktree remove --force failed: {err}. Attempting filesystem cleanup.")
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)

        # Prune dead worktrees
        await self._run_git(repo_root, "worktree", "prune")

        # Delete branch if requested
        if branch_name and delete_branch:
            await self._run_git(repo_root, "branch", "-D", branch_name)

        return True
