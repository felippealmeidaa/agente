"""Local LLM Gateway and Cross-Process Concurrency Controller.

Acts as a local proxy on http://127.0.0.1:4000:
1. Translates Anthropic Messages API (POST /v1/messages) required by Claude Code
   into Ollama/OpenAI Chat Completions format.
2. Forwards OpenAI Chat Completions (POST /v1/chat/completions) directly to the remote Ollama tunnel.
3. Enforces strict global concurrency (asyncio Semaphore + FileLock IPC) so distinct
   CLI processes (Claude, Aider, Python supervisor) never overwhelm the remote RTX 5090.
"""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import uuid

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from filelock import FileLock
import httpx
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from omni_core.config import get_settings

logger = logging.getLogger("omni_core.llm_gateway")
settings = get_settings()

# In-memory semaphore for local event loop
_async_semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)


@asynccontextmanager
async def acquire_gpu_slot():
    """Acquire both the in-process semaphore and the filesystem IPC lock.
    
    Ensures that multiple OS processes (e.g. Claude Code subprocess, Aider,
    and LangGraph Python threads) do not violate OLLAMA_NUM_PARALLEL on the RTX 5090.
    """
    async with _async_semaphore:
        # Run filelock acquisition in a thread to keep async loop unblocked
        lock = FileLock(str(settings.gpu_lock_file), timeout=float(settings.ollama_request_timeout_seconds))
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lock.acquire)
        try:
            yield
        finally:
            await loop.run_in_executor(None, lock.release)


# ==============================================================================
# Pydantic Schemas for Anthropic <-> OpenAI Translation
# ==============================================================================

class AnthropicMessage(BaseModel):
    role: str
    content: Any  # string or list of content blocks


class AnthropicMessagesRequest(BaseModel):
    model: str
    messages: List[AnthropicMessage]
    system: Optional[str] = None
    max_tokens: Optional[int] = 4096
    temperature: Optional[float] = 0.2
    stream: Optional[bool] = False


# ==============================================================================
# FastAPI Proxy Application
# ==============================================================================

app = FastAPI(
    title="Hermes-Omni LLM Gateway",
    description="Cross-process LLM Proxy with Anthropic/OpenAI protocol bridging and GPU slot queueing.",
    version="0.2.0",
)


@app.get("/health")
async def health_check():
    """Health and connectivity check for local agents."""
    return {
        "status": "online",
        "remote_ollama_url": settings.ollama_remote_url,
        "model": settings.ollama_model_name,
        "max_concurrent": settings.max_concurrent_llm_calls,
    }


@app.post("/v1/messages")
async def anthropic_messages_proxy(request: Request):
    """Bridge Anthropic /v1/messages endpoint (used by Claude Code) to Ollama /v1/chat/completions."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}")

    # Extract messages and system prompt
    raw_messages = body.get("messages", [])
    system_prompt = body.get("system", "")
    stream = body.get("stream", False)
    temperature = body.get("temperature", 0.2)

    openai_messages: List[Dict[str, str]] = []
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})

    for msg in raw_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # If content is a list of blocks, extract text
        if isinstance(content, list):
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            content = "\n".join(text_parts)
        openai_messages.append({"role": role, "content": str(content)})

    payload = {
        "model": settings.ollama_model_name,
        "messages": openai_messages,
        "temperature": temperature,
        "stream": stream,
        "options": {
            "num_ctx": settings.council_num_ctx,
        },
    }

    target_url = f"{settings.ollama_remote_url}/v1/chat/completions"

    async with acquire_gpu_slot():
        timeout = httpx.Timeout(settings.ollama_request_timeout_seconds, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(target_url, json=payload)
                response.raise_for_status()
                openai_resp = response.json()
            except httpx.HTTPError as exc:
                logger.error(f"Upstream Ollama request failed: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Ollama inference error: {exc}",
                )

    # Translate OpenAI completion response to Anthropic message format
    completion_text = (
        openai_resp.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    usage = openai_resp.get("usage", {})

    anthropic_resp = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "model": settings.ollama_model_name,
        "content": [
            {
                "type": "text",
                "text": completion_text,
            }
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }

    return JSONResponse(content=anthropic_resp)


@app.post("/v1/chat/completions")
async def openai_chat_completions_proxy(request: Request):
    """Forward OpenAI Chat Completions requests to Ollama, guarded by the GPU Semaphore."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    stream = body.get("stream", False)
    body["model"] = settings.ollama_model_name

    # Ensure num_ctx is configured
    if "options" not in body:
        body["options"] = {"num_ctx": settings.default_num_ctx}

    target_url = f"{settings.ollama_remote_url}/v1/chat/completions"

    if stream:
        async def stream_generator() -> AsyncGenerator[bytes, None]:
            async with acquire_gpu_slot():
                timeout = httpx.Timeout(settings.ollama_request_timeout_seconds, connect=15.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream("POST", target_url, json=body) as upstream:
                        async for chunk in upstream.aiter_bytes():
                            yield chunk

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    async with acquire_gpu_slot():
        timeout = httpx.Timeout(settings.ollama_request_timeout_seconds, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(target_url, json=body)
                response.raise_for_status()
                return JSONResponse(content=response.json())
            except httpx.HTTPError as exc:
                logger.error(f"Error calling remote Ollama: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream error: {exc}",
                )


# ==============================================================================
# Helper factory for LangChain / LangGraph inside Python
# ==============================================================================

def get_chat_model(
    temperature: float = 0.2,
    num_ctx: Optional[int] = None,
    streaming: bool = False,
) -> ChatOpenAI:
    """Return an initialized ChatOpenAI instance configured to communicate with the local gateway.
    
    This unifies LangGraph LLM nodes, ensuring every call obeys the local semaphore
    and timeouts without hardcoding URLs across the codebase.
    """
    ctx = num_ctx or settings.default_num_ctx
    return ChatOpenAI(
        model=settings.ollama_model_name,
        base_url=f"http://{settings.gateway_host}:{settings.gateway_port}/v1",
        api_key=settings.gateway_api_key,
        temperature=temperature,
        streaming=streaming,
        timeout=settings.ollama_request_timeout_seconds,
        max_retries=3,
        model_kwargs={
            "extra_body": {
                "options": {
                    "num_ctx": ctx,
                }
            }
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.gateway_host,
        port=settings.gateway_port,
        log_level="info",
    )
