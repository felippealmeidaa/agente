"""DevOps & Infrastructure Specialist Agent for Hermes-Omni.

Manages:
- Docker and Docker Compose services (Postgres, Redis, Phoenix)
- Tunnel health checks (Cloudflare Tunnel / Ngrok / Ollama Remote)
- Container log inspection and deployment automation
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

from omni_core.config import get_settings
from omni_core.coding_council.worktree_manager import sanitize_terminal_output

logger = logging.getLogger("omni_core.specialists.devops_infra")
settings = get_settings()


class ClusterHealthReport(BaseModel):
    """Health check diagnosis for local and remote infrastructure."""
    remote_ollama_reachable: bool
    remote_latency_ms: float = 0.0
    remote_model_loaded: bool = False
    local_gateway_reachable: bool = False
    docker_containers: List[Dict[str, str]] = []
    error_summary: Optional[str] = None


class DevOpsInfraAgent:
    """Specialist managing containers, tunnels, and cluster connectivity."""

    async def check_infrastructure_health(self) -> ClusterHealthReport:
        """Ping remote Ollama and local Gateway, checking status and latency."""
        start_t = asyncio.get_event_loop().time()
        ollama_ok = False
        model_loaded = False
        latency = 0.0

        # Check Remote Ollama
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{settings.ollama_remote_url}/api/tags")
                latency = round((asyncio.get_event_loop().time() - start_t) * 1000, 2)
                if resp.status_code == 200:
                    ollama_ok = True
                    data = resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    model_loaded = any(settings.ollama_model_name in m for m in models)
        except Exception as exc:
            logger.warning(f"Remote Ollama unreachable: {exc}")

        # Check Local Gateway
        gateway_ok = False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                g_resp = await client.get(f"http://{settings.gateway_host}:{settings.gateway_port}/health")
                gateway_ok = (g_resp.status_code == 200)
        except Exception:
            gateway_ok = False

        # Check Docker Compose status
        containers = await self.get_compose_status()

        return ClusterHealthReport(
            remote_ollama_reachable=ollama_ok,
            remote_latency_ms=latency,
            remote_model_loaded=model_loaded,
            local_gateway_reachable=gateway_ok,
            docker_containers=containers,
        )

    async def get_compose_status(self) -> List[Dict[str, str]]:
        """List active containers from docker compose."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "ps", "--format", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            output = sanitize_terminal_output(stdout.decode(errors="replace"))
            return [{"status": line} for line in output.splitlines() if line.strip()]
        except Exception as exc:
            logger.warning(f"Could not retrieve docker compose status: {exc}")
            return []

    async def manage_docker_compose(self, action: str = "up") -> Tuple[bool, str]:
        """Execute docker compose actions: up, down, restart."""
        valid_actions = {"up": ["docker", "compose", "up", "-d"], "down": ["docker", "compose", "down"], "restart": ["docker", "compose", "restart"]}
        cmd = valid_actions.get(action.lower(), ["docker", "compose", "ps"])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            out = sanitize_terminal_output(stdout.decode(errors="replace"))
            err = sanitize_terminal_output(stderr.decode(errors="replace"))
            success = (proc.returncode == 0)
            return success, out or err
        except Exception as exc:
            return False, str(exc)
