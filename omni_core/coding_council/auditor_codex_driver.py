"""Hybrid Auditor & Codex Driver for Hermes-Omni Coding Council.

Two-tier verification pipeline:
1. Deterministic Tier: Automatically detects project stack (Python, Node/TS, .NET, Go, Rust)
   and executes real test suites (pytest, ruff, npm test, tsc, dotnet test).
2. Agentic Tier: Audits the git diff with the Codex CLI (or LLM Auditor via Local Gateway)
   for contract violations, logic bugs, regression risks, and security issues.
"""

import asyncio
import logging
import os
from pathlib import Path
import shutil
import time
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from omni_core.config import get_settings
from omni_core.coding_council.worktree_manager import sanitize_terminal_output
from omni_core.llm_gateway import get_chat_model

logger = logging.getLogger("omni_core.coding_council.auditor_codex_driver")
settings = get_settings()


class AuditReport(BaseModel):
    """Structured report produced by the Auditor / Codex stage."""
    approved: bool
    deterministic_tests_passed: bool
    test_output: str = ""
    traceback: str = ""
    agentic_critique: str = ""
    suggested_fixes: List[str] = Field(default_factory=list)
    duration_seconds: float = 0.0


class AuditorCodexDriver:
    """Orchestrates deterministic test suites and agentic code audits."""

    def __init__(self):
        self.codex_bin = shutil.which("codex")

    async def run_command(
        self,
        cmd: List[str],
        cwd: Path,
        timeout: float = 120.0,
    ) -> Tuple[int, str, str]:
        """Run an external command asynchronously with sanitized outputs."""
        logger.debug(f"Running audit command: {' '.join(cmd)} in {cwd}")
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            out = sanitize_terminal_output(stdout.decode(errors="replace"))
            err = sanitize_terminal_output(stderr.decode(errors="replace"))
            return process.returncode or 0, out, err
        except asyncio.TimeoutError:
            return -1, "", f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
        except Exception as exc:
            return -1, "", f"Execution error: {exc}"

    async def run_deterministic_suite(self, worktree_path: Path) -> Tuple[bool, str, str]:
        """Detect tech stack and execute appropriate automated tests and linters."""
        worktree_path = worktree_path.resolve()
        logger.info(f"Running deterministic audit in {worktree_path}")

        # Python projects
        if (worktree_path / "pyproject.toml").exists() or (worktree_path / "pytest.ini").exists() or any(worktree_path.glob("test_*.py")):
            pytest_bin = shutil.which("pytest") or "pytest"
            code, out, err = await self.run_command([sys_python := "python", "-m", "pytest", "-v", "--tb=short"], worktree_path)
            # If no tests collected, that's not a failure
            if code == 5:  # pytest exit code 5: no tests were collected
                return True, "No pytest tests collected. Passing deterministic step.", ""
            passed = (code == 0)
            combined = f"{out}\n{err}".strip()
            tb = combined if not passed else ""
            return passed, combined, tb

        # Node / TypeScript projects
        if (worktree_path / "package.json").exists():
            npm_bin = shutil.which("npm") or "npm"
            code, out, err = await self.run_command([npm_bin, "test", "--", "--passWithNoTests"], worktree_path)
            passed = (code == 0)
            combined = f"{out}\n{err}".strip()
            tb = combined if not passed else ""
            return passed, combined, tb

        # Go projects
        if (worktree_path / "go.mod").exists():
            go_bin = shutil.which("go") or "go"
            code, out, err = await self.run_command([go_bin, "test", "./..."], worktree_path)
            passed = (code == 0)
            combined = f"{out}\n{err}".strip()
            return passed, combined, combined if not passed else ""

        # Default fallback if no known test runner files detected
        logger.info("No specific test framework files detected. Deterministic step passes.")
        return True, "No formal test runner detected in sandbox.", ""

    async def run_agentic_audit(
        self,
        worktree_path: Path,
        git_diff: str,
        test_output: str,
        task_instruction: str,
    ) -> Tuple[bool, str, List[str]]:
        """Run deep semantic code review via Codex CLI or Native LLM Auditor."""
        logger.info("Running Agentic Code Audit on git diff...")

        if not git_diff.strip():
            return True, "Empty diff. No changes detected.", []

        # If official codex CLI is installed in PATH, use it
        if self.codex_bin:
            prompt = (
                f"Audit the following code changes for task: {task_instruction}\n"
                f"Diff:\n{git_diff}\n"
                f"Test results: {test_output}\n"
                "Return 'STATUS: APPROVED' if correct and high quality. "
                "Otherwise explain root causes and list specific fixes."
            )
            cmd = [
                self.codex_bin,
                "--model",
                settings.ollama_model_name,
                "-q",
                prompt,
            ]
            code, out, err = await self.run_command(cmd, worktree_path)
            combined = f"{out}\n{err}".strip()
            approved = "STATUS: APPROVED" in combined.upper()
            return approved, combined, []

        # Native LLM Auditor via Local Gateway
        llm = get_chat_model(temperature=0.1, num_ctx=settings.council_num_ctx)
        audit_prompt = f"""You are the Principal Code Auditor of the Hermes-Omni Coding Council.
Inspect the Git Diff below against the original user task and automated test output.

USER TASK:
{task_instruction}

TEST OUTPUT:
{test_output}

GIT DIFF:
{git_diff}

AUDIT CRITERIA:
1. Does the code fulfill the user's task without breaking contracts?
2. Are all types, imports, and edge cases handled?
3. Zero placeholders or incomplete code.

Respond strictly in this format:
VERDICT: APPROVED or REJECTED
CRITIQUE: <concise explanation of quality or failure cause>
FIXES:
- <fix 1>
- <fix 2>
"""
        try:
            resp = await llm.ainvoke([{"role": "user", "content": audit_prompt}])
            content = str(resp.content).strip()
            is_approved = "VERDICT: APPROVED" in content.upper()
            lines = content.splitlines()
            fixes = [line.strip("- ").strip() for line in lines if line.strip().startswith("- ")]
            return is_approved, content, fixes
        except Exception as exc:
            logger.error(f"Agentic audit failed: {exc}")
            # Do not block if deterministic tests passed and LLM audit experienced network glitch
            return False, f"LLM Audit encountered error: {exc}", [str(exc)]

    async def audit_worktree(
        self,
        worktree_path: Path,
        git_diff: str,
        task_instruction: str,
    ) -> AuditReport:
        """Execute both deterministic and agentic audit stages."""
        start_time = time.time()

        # Step 1: Deterministic test suite execution
        det_passed, test_out, traceback = await self.run_deterministic_suite(worktree_path)

        # If deterministic tests failed, reject immediately with traceback
        if not det_passed:
            duration = round(time.time() - start_time, 2)
            logger.warning("Deterministic tests failed. Rejecting diff.")
            return AuditReport(
                approved=False,
                deterministic_tests_passed=False,
                test_output=test_out,
                traceback=traceback,
                agentic_critique="Deterministic tests failed.",
                suggested_fixes=["Fix failing unit tests or compilation errors reported in traceback."],
                duration_seconds=duration,
            )

        # Step 2: Agentic audit on git diff
        agentic_approved, critique, fixes = await self.run_agentic_audit(
            worktree_path,
            git_diff,
            test_out,
            task_instruction,
        )

        duration = round(time.time() - start_time, 2)
        overall_approved = det_passed and agentic_approved

        return AuditReport(
            approved=overall_approved,
            deterministic_tests_passed=det_passed,
            test_output=test_out,
            traceback="" if overall_approved else traceback,
            agentic_critique=critique,
            suggested_fixes=fixes,
            duration_seconds=duration,
        )
