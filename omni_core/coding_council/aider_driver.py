"""Aider Surgical Driver for Hermes-Omni Coding Council.

Acts as the Surgical Code Repairer:
- Invoked when the Auditor/Codex stage rejects a diff due to test failures or contract bugs.
- Connects explicitly to the Local Gateway:
  `aider --model openai/qwen3.8-pro --openai-api-base http://127.0.0.1:4000/v1 --openai-api-key omni-local --yes-always --no-pretty --no-stream --message "..."`
- Sanitizes output to remove ANSI codes.
- Provides native LLM surgical patch fallback if `aider` is not installed on the system.
"""

import asyncio
import logging
import os
from pathlib import Path
import shutil
import time
from typing import Optional

from pydantic import BaseModel

from omni_core.config import get_settings
from omni_core.coding_council.worktree_manager import sanitize_terminal_output
from omni_core.llm_gateway import get_chat_model

logger = logging.getLogger("omni_core.coding_council.aider_driver")
settings = get_settings()


class AiderExecutionResult(BaseModel):
    """Result of an Aider surgical patch turn."""
    success: bool
    output: str
    error: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.0
    fallback_used: bool = False


class AiderDriver:
    """Manages invocations of Aider to apply surgical code fixes inside a worktree."""

    def __init__(self):
        self.aider_bin = shutil.which("aider")

    async def execute_surgical_fix(
        self,
        worktree_path: Path,
        traceback_or_critique: str,
        task_instruction: str,
        timeout_seconds: float = 300.0,
    ) -> AiderExecutionResult:
        """Execute a targeted code repair inside the worktree sandbox."""
        start_time = time.time()
        worktree_path = worktree_path.resolve()

        surgical_message = (
            f"SURGICAL BUG FIX REQUEST:\n"
            f"Original Goal: {task_instruction}\n\n"
            f"AUDIT / TEST FAILURE TRACEBACK:\n"
            f"{traceback_or_critique}\n\n"
            f"Fix the root cause precisely without breaking other functionality. Ensure all tests pass."
        )

        if not self.aider_bin:
            logger.warning("Aider CLI not found in PATH. Using LLM Surgical Fallback.")
            return await self._fallback_surgical_repair(
                worktree_path, surgical_message, start_time
            )

        cmd = [
            self.aider_bin,
            "--model",
            f"openai/{settings.ollama_model_name}",
            "--openai-api-base",
            f"http://{settings.gateway_host}:{settings.gateway_port}/v1",
            "--openai-api-key",
            settings.gateway_api_key,
            "--yes-always",
            "--no-pretty",
            "--no-stream",
            "--message",
            surgical_message,
        ]

        logger.info(f"Running Aider surgical fix in {worktree_path}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(worktree_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )

            duration = round(time.time() - start_time, 2)
            out_clean = sanitize_terminal_output(stdout.decode(errors="replace"))
            err_clean = sanitize_terminal_output(stderr.decode(errors="replace"))

            is_success = (process.returncode == 0)
            return AiderExecutionResult(
                success=is_success,
                output=out_clean,
                error=err_clean,
                exit_code=process.returncode or 0,
                duration_seconds=duration,
                fallback_used=False,
            )

        except asyncio.TimeoutError:
            logger.error(f"Aider execution timed out after {timeout_seconds}s")
            return AiderExecutionResult(
                success=False,
                output="",
                error=f"Aider timed out after {timeout_seconds}s",
                exit_code=-1,
                duration_seconds=round(time.time() - start_time, 2),
                fallback_used=False,
            )
        except Exception as exc:
            logger.exception(f"Error running Aider: {exc}")
            return AiderExecutionResult(
                success=False,
                output="",
                error=str(exc),
                exit_code=-1,
                duration_seconds=round(time.time() - start_time, 2),
                fallback_used=False,
            )

    async def _fallback_surgical_repair(
        self,
        worktree_path: Path,
        instruction: str,
        start_time: float,
    ) -> AiderExecutionResult:
        """Internal surgical repair fallback when Aider CLI is not present."""
        logger.info("Executing Native LLM Surgical Repair...")
        llm = get_chat_model(temperature=0.1, num_ctx=settings.council_num_ctx)

        prompt = (
            f"You are the Surgical Code Repairer of Hermes-Omni.\n"
            f"{instruction}\n"
            f"Provide the exact, targeted code fixes to resolve the traceback."
        )

        try:
            resp = await llm.ainvoke([{"role": "user", "content": prompt}])
            duration = round(time.time() - start_time, 2)
            return AiderExecutionResult(
                success=True,
                output=str(resp.content),
                error="",
                exit_code=0,
                duration_seconds=duration,
                fallback_used=True,
            )
        except Exception as exc:
            logger.error(f"Fallback surgical repair failed: {exc}")
            return AiderExecutionResult(
                success=False,
                output="",
                error=str(exc),
                exit_code=-1,
                duration_seconds=round(time.time() - start_time, 2),
                fallback_used=True,
            )
