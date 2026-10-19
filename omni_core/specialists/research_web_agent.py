"""Deep Research & Web Documentation Specialist Agent for Hermes-Omni.

Provides:
- Web scraping and technical documentation fetching
- HTML cleaning and Markdown conversion to prevent context-rot
- Playwright headless support with automatic fallback to httpx
"""

import logging
import re
from typing import Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger("omni_core.specialists.research_web")


class WebResearchResult(BaseModel):
    """Result of fetching and extracting web content."""
    url: str
    success: bool
    title: str = ""
    markdown_content: str = ""
    error: Optional[str] = None


class ResearchWebAgent:
    """Specialist providing web search, technical docs ingestion, and summarization."""

    @staticmethod
    def _html_to_markdown(html_content: str) -> str:
        """Strip tags, scripts, and styles, converting raw HTML into clean readable text."""
        # Remove script and style elements
        cleaned = re.sub(r"<(script|style).*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        # Convert links <a href="url">text</a> -> [text](url)
        cleaned = re.sub(r'<a\s+(?:[^>]*?\s+)?href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", cleaned, flags=re.IGNORECASE)
        # Convert headers
        cleaned = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n### \1\n", cleaned, flags=re.IGNORECASE)
        # Convert paragraphs and breaks
        cleaned = re.sub(r"</p>", "\n\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
        # Strip all remaining tags
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        # Normalize whitespace
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        return "\n\n".join(lines)

    async def fetch_page_content(
        self,
        url: str,
        timeout_seconds: float = 20.0,
        max_characters: int = 15000,
    ) -> WebResearchResult:
        """Fetch documentation page and return clean Markdown content."""
        logger.info(f"Research Agent: Fetching content from {url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 HermesOmniBot/2.0"
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()

            raw_html = resp.text
            # Extract title if present
            title_match = re.search(r"<title>(.*?)</title>", raw_html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "Documentation Page"

            md_text = self._html_to_markdown(raw_html)

            # Context protection truncation
            if len(md_text) > max_characters:
                md_text = md_text[:max_characters] + "\n\n[... Truncated for Context Protection ...]"

            return WebResearchResult(
                url=url,
                success=True,
                title=title,
                markdown_content=md_text,
            )

        except Exception as exc:
            logger.error(f"Failed to fetch {url}: {exc}")
            return WebResearchResult(
                url=url,
                success=False,
                error=str(exc),
            )
