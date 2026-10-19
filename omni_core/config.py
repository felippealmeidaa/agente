"""Hermes-Omni System Configuration.

Pydantic Settings module providing strict validation of environment variables,
remote Ollama cluster URLs, local gateway settings, concurrency semaphores,
VRAM context limits, and safety tier configurations.
"""

from functools import lru_cache
from pathlib import Path
import tempfile
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for Hermes-Omni."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --------------------------------------------------------------------------
    # Remote Inference Cluster (NVIDIA RTX 5090 32GB)
    # --------------------------------------------------------------------------
    ollama_remote_url: str = Field(
        default="http://localhost:11434",
        description="Public/Tunnneled HTTPS URL for the remote Ollama inference server.",
    )
    ollama_model_name: str = Field(
        default="qwen3.8-pro",
        description="Target model identifier running on the remote Ollama server.",
    )
    ollama_request_timeout_seconds: float = Field(
        default=600.0,
        description="Maximum HTTP timeout for long-context inferences to respect GPU queue.",
    )

    # --------------------------------------------------------------------------
    # Local LLM Gateway & Cross-Process Concurrency
    # --------------------------------------------------------------------------
    gateway_host: str = Field(
        default="127.0.0.1",
        description="Local interface IP where the LiteLLM/FastAPI proxy listens.",
    )
    gateway_port: int = Field(
        default=4000,
        description="Local port where the LiteLLM/FastAPI proxy listens.",
    )
    gateway_api_key: str = Field(
        default="omni-local",
        description="Shared secret key for local CLI authentication.",
    )
    max_concurrent_llm_calls: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Max concurrent requests dispatched from this host to Ollama.",
    )
    gpu_lock_file: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "omni_gpu.lock",
        description="Filesystem IPC lock path for cross-process synchronization.",
    )

    # --------------------------------------------------------------------------
    # VRAM Budget & Context Limits
    # --------------------------------------------------------------------------
    default_num_ctx: int = Field(
        default=32768,
        description="Default context window in tokens for fast domain sub-agents.",
    )
    council_num_ctx: int = Field(
        default=65536,
        description="Expanded context window for deep coding council tasks.",
    )
    max_reflexion_turns: int = Field(
        default=3,
        description="Hard circuit-breaker threshold for self-correction loops.",
    )

    # --------------------------------------------------------------------------
    # Databases, Cache & State
    # --------------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql://omni_user:omni_pass@localhost:5432/omni_db",
        description="PostgreSQL + pgvector connection string.",
    )
    sqlite_db_path: Path = Field(
        default=Path("./omni_memory.db"),
        description="Fallback SQLite database path for local checkpointing and RAG.",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for global distributed semaphores and event queues.",
    )

    # --------------------------------------------------------------------------
    # Mobile Gateway & Audio Transcription
    # --------------------------------------------------------------------------
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram Bot API token for mobile remote control.",
    )
    telegram_allowed_user_id: Optional[int] = Field(
        default=None,
        description="Strictly whitelisted Telegram User ID authorized to send commands.",
    )
    whatsapp_session_path: Path = Field(
        default=Path("./.whatsapp_session"),
        description="Directory for WhatsApp Web session persistence.",
    )
    whatsapp_allowed_phone: Optional[str] = Field(
        default=None,
        description="Strictly whitelisted WhatsApp phone number (+55...).",
    )
    whisper_model: str = Field(
        default="small",
        description="Faster-Whisper model variant (base, small) for notebook CPU.",
    )
    whisper_device: str = Field(
        default="cpu",
        description="Inference device for faster-whisper (cpu or cuda).",
    )
    whisper_compute_type: str = Field(
        default="int8",
        description="Quantized compute type to ensure zero CPU freezing on notebook.",
    )

    # --------------------------------------------------------------------------
    # Safety Gate & Sandboxing
    # --------------------------------------------------------------------------
    enable_safety_gate: bool = Field(
        default=True,
        description="Whether to enforce Tiered Safety (Tier 1/2/3) checks.",
    )
    require_hitl_on_tier3: bool = Field(
        default=True,
        description="Require interactive mobile confirmation before running destructive actions.",
    )
    sandbox_base_dir: Path = Field(
        default=Path("../.omni_sandboxes"),
        description="Base directory where isolated Git Worktrees are spawned.",
    )

    @field_validator("ollama_remote_url")
    @classmethod
    def clean_remote_url(cls, v: str) -> str:
        """Strip trailing slashes from the Ollama URL."""
        return v.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of the system settings."""
    return Settings()
