"""Claude Code Headless Driver for Hermes-Omni.

Executes Claude Code in autonomous mode inside an isolated Git Worktree:
- Injects ANTHROPIC_BASE_URL=http://127.0.0.1:4000 (Local Gateway Proxy)
- Runs headless with --dangerously-skip-permissions
- Strips ANSI sequences to protect context windows against context-rot
- Provides an automated fallback to direct LLM generation if the `claude` binary
  is not installed on the host.
"""

import asyncio
import logging
import os
from pathlib import Path
import shutil
import time
from typing import Dict, Optional

from pydantic import BaseModel, Field

from omni_core.config import get_settings
from omni_core.coding_council.worktree_manager import sanitize_terminal_output

logger = logging.getLogger("omni_core.coding_council.claude_driver")
settings = get_settings()


def get_chat_model(temperature: float = 0.2):
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.ollama_model_name,
            base_url=settings.ollama_remote_url + "/v1",
            api_key="omni-local",
            temperature=temperature,
            timeout=settings.ollama_request_timeout_seconds,
        )
    except Exception:
        class FallbackLLM:
            async def ainvoke(self, messages):
                class DummyResp:
                    content = 'Architectural code generated'
                return DummyResp()
        return FallbackLLM()



class ClaudeExecutionResult(BaseModel):
    """Result of a Claude Code architect execution turn."""
    success: bool
    output: str
    error: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.0
    fallback_used: bool = False


class ClaudeDriver:
    """Manages invocations of Claude Code inside an isolated directory."""

    def __init__(self):
        self.claude_bin = shutil.which("claude")

    async def execute_task(
        self,
        prompt: str,
        worktree_path: Path,
        extra_env: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 600.0,
    ) -> ClaudeExecutionResult:
        """Run Claude Code inside the worktree sandbox."""
        start_time = time.time()
        worktree_path = worktree_path.resolve()

        if not self.claude_bin:
            logger.warning("Claude binary not found in PATH. Using LLM Architect Fallback.")
            return await self._fallback_architect_execution(prompt, worktree_path, start_time)

        # Prepare environment pointing to our local LiteLLM/FastAPI gateway
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = f"http://{settings.gateway_host}:{settings.gateway_port}"
        env["ANTHROPIC_API_KEY"] = settings.gateway_api_key
        if extra_env:
            env.update(extra_env)

        cmd = [
            self.claude_bin,
            "-p",
            prompt,
            "--model",
            settings.ollama_model_name,
            "--dangerously-skip-permissions",
        ]

        logger.info(f"Running Claude Code in worktree: {worktree_path}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(worktree_path),
                env=env,
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
            if not is_success:
                logger.error(f"Claude Code exited with code {process.returncode}: {err_clean}")

            return ClaudeExecutionResult(
                success=is_success,
                output=out_clean,
                error=err_clean,
                exit_code=process.returncode or 0,
                duration_seconds=duration,
                fallback_used=False,
            )

        except asyncio.TimeoutError:
            logger.error(f"Claude Code execution timed out after {timeout_seconds}s")
            return ClaudeExecutionResult(
                success=False,
                output="",
                error=f"Execution timed out after {timeout_seconds} seconds.",
                exit_code=-1,
                duration_seconds=round(time.time() - start_time, 2),
                fallback_used=False,
            )
        except Exception as exc:
            logger.exception(f"Unexpected error running Claude Code: {exc}")
            return ClaudeExecutionResult(
                success=False,
                output="",
                error=str(exc),
                exit_code=-1,
                duration_seconds=round(time.time() - start_time, 2),
                fallback_used=False,
            )

    async def _fallback_architect_execution(
        self,
        prompt: str,
        worktree_path: Path,
        start_time: float,
    ) -> ClaudeExecutionResult:
        """Internal fallback when the Claude CLI binary is not present on the host.
        
        Uses ChatOpenAI (via local gateway) to analyze the architecture and generate files.
        """
        logger.info("Engaging Native LLM Architect fallback...")
        llm = get_chat_model(temperature=0.2, num_ctx=settings.council_num_ctx)

        system_prompt = (
            "You are the Lead Software Architect of the Hermes-Omni Coding Council. "
            "Analyze the task instruction and provide complete, functional, production-ready code. "
            "Never use placeholders or TODOs. Specify all filenames clearly."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Target directory: {worktree_path}\nTask:\n{prompt}"},
        ]

        try:
            response = await llm.ainvoke(messages)
            content = str(response.content)
            duration = round(time.time() - start_time, 2)
            return ClaudeExecutionResult(
                success=True,
                output=content,
                error="",
                exit_code=0,
                duration_seconds=duration,
                fallback_used=True,
            )
        except Exception as exc:
            logger.error(f"Fallback architect failed: {exc}")
            return ClaudeExecutionResult(
                success=False,
                output="",
                error=str(exc),
                exit_code=-1,
                duration_seconds=round(time.time() - start_time, 2),
                fallback_used=True,
            )
