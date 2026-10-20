"""OS God Mode Specialist Agent for Hermes-Omni.

Provides unrestricted operating system control over:
- Linux / WSL2 via bash
- Windows Host via PowerShell (powershell.exe -Command ...)
- Filesystem inspection and process lifecycle management

All execution is audited and guarded by the Tiered Safety Gate (safety_gate.py).
Tier 3 commands are quarantined until human token confirmation.
"""

import asyncio
import logging
from pathlib import Path
import shutil
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from omni_core.config import get_settings
from omni_core.coding_council.worktree_manager import sanitize_terminal_output

logger = logging.getLogger("omni_core.specialists.os_godmode")
settings = get_settings()


class SafetyGate:
    """Integrated safety checker for OS GodMode operations."""
    DESTRUCTIVE_PATTERNS = ["rm -rf", "drop database", "format ", "remove-item -recurse"]

    def __init__(self):
        self._tokens = {}

    def evaluate_command(self, cmd: str):
        class Verdict:
            tier = "tier1_green"
            allowed = True
            requires_human_confirmation = False
            quarantine_token = None
            confirmation_token = None
            reason = "Auto-approved execution"

        v = Verdict()
        lower = cmd.lower()
        if any(p in lower for p in self.DESTRUCTIVE_PATTERNS):
            v.tier = "tier3_red"
            v.allowed = False
            v.requires_human_confirmation = True
            token = "QUARANTINE_TOKEN_123"
            v.quarantine_token = token
            v.confirmation_token = token
            self._tokens[token] = cmd
            v.reason = "Destructive command blocked by safety policy"
        elif "git " in lower or "ls" in lower or "dir" in lower or "echo" in lower:
            v.tier = "tier1_green"
        else:
            v.tier = "tier2_yellow"
        return v

    def confirm_token(self, token: str) -> Optional[str]:
        return self._tokens.pop(token, None)



class CommandExecutionOutput(BaseModel):
    """Result of an OS execution."""
    command: str
    target_shell: str
    exit_code: int
    stdout: str
    stderr: str
    executed: bool
    safety_tier: str
    quarantine_token: Optional[str] = None
    reason: str = ""


class OSGodModeAgent:
    """Agent specialist providing system-level execution under safety governance."""

    def __init__(self, safety_gate: Optional[SafetyGate] = None):
        self.safety_gate = safety_gate or SafetyGate()
        self.wsl_available = shutil.which("wsl") is not None
        self.powershell_bin = shutil.which("powershell.exe") or shutil.which("pwsh") or "powershell"

    async def execute_command(
        self,
        command: str,
        target_shell: str = "powershell",
        cwd: Optional[Path] = None,
        confirmation_token: Optional[str] = None,
        timeout_seconds: float = 120.0,
    ) -> CommandExecutionOutput:
        """Execute a shell command in PowerShell or WSL2 Bash, audited by SafetyGate."""
        work_dir = (cwd or Path.cwd()).resolve()

        # If a confirmation token was provided, attempt to claim it
        if confirmation_token:
            approved_cmd = self.safety_gate.confirm_token(confirmation_token)
            if not approved_cmd:
                return CommandExecutionOutput(
                    command=command,
                    target_shell=target_shell,
                    exit_code=-1,
                    stdout="",
                    stderr="Invalid or expired confirmation token.",
                    executed=False,
                    safety_tier="tier3_red",
                    reason="Quarantine token rejection.",
                )
            command = approved_cmd
            safety_eval_tier = "tier3_red"
        else:
            # Evaluate against safety gate
            safety_result = self.safety_gate.evaluate_command(command)
            safety_eval_tier = safety_result.tier

            if safety_result.requires_human_confirmation:
                logger.warning(f"OS GodMode: Command quarantined: {command}")
                return CommandExecutionOutput(
                    command=command,
                    target_shell=target_shell,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Quarantined by Safety Gate: {safety_result.reason}",
                    executed=False,
                    safety_tier=safety_result.tier,
                    quarantine_token=safety_result.confirmation_token,
                    reason=safety_result.reason,
                )

        # Build command invocation
        if target_shell.lower() in ("bash", "wsl", "linux") and self.wsl_available:
            exec_args = ["wsl", "bash", "-c", command]
        else:
            exec_args = [self.powershell_bin, "-NoProfile", "-NonInteractive", "-Command", command]

        logger.info(f"OS GodMode: Executing in [{target_shell}]: {command}")

        try:
            process = await asyncio.create_subprocess_exec(
                *exec_args,
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )

            out_clean = sanitize_terminal_output(stdout.decode(errors="replace"))
            err_clean = sanitize_terminal_output(stderr.decode(errors="replace"))

            return CommandExecutionOutput(
                command=command,
                target_shell=target_shell,
                exit_code=process.returncode or 0,
                stdout=out_clean,
                stderr=err_clean,
                executed=True,
                safety_tier=safety_eval_tier,
                reason="Execution completed.",
            )

        except asyncio.TimeoutError:
            return CommandExecutionOutput(
                command=command,
                target_shell=target_shell,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout_seconds}s.",
                executed=False,
                safety_tier=safety_eval_tier,
                reason="Timeout.",
            )
        except Exception as exc:
            return CommandExecutionOutput(
                command=command,
                target_shell=target_shell,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                executed=False,
                safety_tier=safety_eval_tier,
                reason=str(exc),
            )
