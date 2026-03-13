"""Link understanding — URL preview and content extraction.

Ported from bk/src/link-understanding/ (~5 TS files).

Covers URL metadata extraction (title, description, image),
Open Graph / Twitter Card parsing, and content summarization.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = ["LinkPreview", "extract_link_preview", "extract_urls"]


@dataclass
class LinkPreview:
    url: str = ""
    title: str = ""
    description: str = ""
    image_url: str = ""
    site_name: str = ""
    favicon_url: str = ""
    content_type: str = ""


URL_PATTERN = re.compile(
    r"https?://[^\s<>\"')\]]+",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    return URL_PATTERN.findall(text)


async def extract_link_preview(url: str) -> LinkPreview | None:
    """Extract Open Graph / meta tag preview data from a URL."""
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "OpenClaw/1.0 LinkPreview"},
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return None
                ct = resp.headers.get("Content-Type", "")
                if "text/html" not in ct:
                    return LinkPreview(url=url, content_type=ct)

                html = await resp.text()
                return _parse_html_meta(url, html)
    except Exception as e:
        logger.debug(f"Link preview failed for {url}: {e}")
        return None


def _parse_html_meta(url: str, html: str) -> LinkPreview:
    """Parse OG and meta tags from HTML."""
    preview = LinkPreview(url=url)

    # OG tags
    og_map = {
        "og:title": "title",
        "og:description": "description",
        "og:image": "image_url",
        "og:site_name": "site_name",
    }
    for og_prop, field_name in og_map.items():
        match = re.search(
            rf'<meta\s+(?:property|name)="{re.escape(og_prop)}"\s+content="([^"]*)"',
            html, re.IGNORECASE,
        )
        if not match:
            match = re.search(
                rf'<meta\s+content="([^"]*)"\s+(?:property|name)="{re.escape(og_prop)}"',
                html, re.IGNORECASE,
            )
        if match:
            setattr(preview, field_name, match.group(1))

    # Twitter card fallback
    if not preview.title:
        m = re.search(r'<meta\s+name="twitter:title"\s+content="([^"]*)"', html, re.I)
        if m:
            preview.title = m.group(1)
    if not preview.description:
        m = re.search(r'<meta\s+name="(?:twitter:description|description)"\s+content="([^"]*)"', html, re.I)
        if m:
            preview.description = m.group(1)

    # Fallback to <title>
    if not preview.title:
        m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        if m:
            preview.title = m.group(1).strip()

    # Favicon
    m = re.search(r'<link\s+[^>]*rel="(?:shortcut )?icon"[^>]*href="([^"]*)"', html, re.I)
    if m:
        preview.favicon_url = m.group(1)

    return preview
