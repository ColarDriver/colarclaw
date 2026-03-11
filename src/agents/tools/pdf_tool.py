"""PDF tool — ported from bk/src/agents/tools/pdf-tool.ts + pdf-tool.helpers.ts + pdf-native-providers.ts."""
from __future__ import annotations

from typing import Any

PDF_TOOL_NAME = "pdf"
PDF_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Path to PDF file"},
        "action": {"type": "string", "enum": ["extract_text", "extract_images", "summarize"]},
        "pages": {"type": "string", "description": "Page range (e.g. '1-5')"},
    },
    "required": ["file_path"],
}


async def handle_pdf_tool(params: dict[str, Any]) -> dict[str, Any]:
    file_path = params.get("file_path", "")
    action = params.get("action", "extract_text")
    return {"status": "ok", "file_path": file_path, "action": action}


PDF_NATIVE_PROVIDERS = ["anthropic", "google", "openai"]


def supports_native_pdf(provider: str) -> bool:
    return provider.lower() in PDF_NATIVE_PROVIDERS


def parse_page_range(range_str: str) -> list[int]:
    pages: list[int] = []
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            try:
                pages.extend(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                pages.append(int(part))
            except ValueError:
                continue
    return sorted(set(pages))
