"""Markdown processing utilities.

Ported from bk/src/markdown/ (~7 TS files).

Covers markdown parsing, code block extraction, heading detection,
reference link resolution, HTML stripping, and channel-specific
markdown format conversion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "extract_code_blocks", "strip_code_blocks",
    "strip_html_tags", "extract_headings",
    "markdown_to_plain", "convert_markdown_for_channel",
    "CodeBlock",
]


@dataclass
class CodeBlock:
    """An extracted code block."""
    language: str = ""
    code: str = ""
    start_line: int = 0
    end_line: int = 0


def extract_code_blocks(text: str) -> list[CodeBlock]:
    """Extract fenced code blocks from markdown."""
    blocks = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        match = re.match(r"^```(\w*)$", lines[i].strip())
        if match:
            lang = match.group(1)
            start = i
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append(CodeBlock(
                language=lang,
                code="\n".join(code_lines),
                start_line=start,
                end_line=i,
            ))
        i += 1
    return blocks


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks from markdown."""
    return re.sub(r"```[\s\S]*?```", "", text).strip()


def extract_headings(text: str) -> list[tuple[int, str]]:
    """Extract headings as (level, text) tuples."""
    headings = []
    for line in text.split("\n"):
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if match:
            headings.append((len(match.group(1)), match.group(2).strip()))
    return headings


def strip_html_tags(text: str) -> str:
    """Strip HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text)


def markdown_to_plain(text: str) -> str:
    """Convert markdown to plain text."""
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "[code]", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove bold/italic
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    # Remove links
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove images
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Remove headings
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
    # Clean up
    text = strip_html_tags(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def convert_markdown_for_channel(text: str, channel: str) -> str:
    """Convert markdown for a specific channel's format."""
    if channel == "telegram":
        # Telegram MarkdownV2: escape special chars
        special = r"_*[]()~`>#+-=|{}.!"
        text = re.sub(f"([{re.escape(special)}])", r"\\\1", text)
        return text
    if channel == "slack":
        # Slack mrkdwn
        text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
        text = re.sub(r"__(.+?)__", r"_\1_", text)
        text = re.sub(r"~~(.+?)~~", r"~\1~", text)
        return text
    if channel == "discord":
        # Discord supports standard markdown
        return text
    if channel in ("signal", "imessage", "whatsapp"):
        # Plain text for these channels
        return markdown_to_plain(text)
    return text
