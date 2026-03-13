"""Infra exec obfuscation detect — ported from bk/src/infra/exec-obfuscation-detect.ts.

Detects obfuscated or encoded commands that could bypass allowlist-based
security filters (e.g., base64-piped shell execution, hex decode piping,
curl-to-shell patterns).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ObfuscationDetection:
    detected: bool = False
    reasons: list[str] = field(default_factory=list)
    matched_patterns: list[str] = field(default_factory=list)


@dataclass
class _ObfuscationPattern:
    id: str
    description: str
    regex: re.Pattern[str]


OBFUSCATION_PATTERNS: list[_ObfuscationPattern] = [
    _ObfuscationPattern(
        id="base64-pipe-exec",
        description="Base64 decode piped to shell execution",
        regex=re.compile(r"base64\s+(?:-d|--decode)\b.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="hex-pipe-exec",
        description="Hex decode (xxd) piped to shell execution",
        regex=re.compile(r"xxd\s+-r\b.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="printf-pipe-exec",
        description="printf with escape sequences piped to shell execution",
        regex=re.compile(r"printf\s+.*\\x[0-9a-f]{2}.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="eval-decode",
        description="eval with encoded/decoded input",
        regex=re.compile(r"eval\s+.*(?:base64|xxd|printf|decode)", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="base64-decode-to-shell",
        description="Base64 decode piped to shell",
        regex=re.compile(r"\|\s*base64\s+(?:-d|--decode)\b.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="pipe-to-shell",
        description="Content piped directly to shell interpreter",
        regex=re.compile(r"\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b(?:\s+[^|;\n\r]+)?\s*$", re.IGNORECASE | re.MULTILINE),
    ),
    _ObfuscationPattern(
        id="command-substitution-decode-exec",
        description="Shell -c with command substitution decode/obfuscation",
        regex=re.compile(
            r'(?:sh|bash|zsh|dash|ksh|fish)\s+-c\s+["\'][^"\']*\$\([^)]*(?:base64\s+(?:-d|--decode)|xxd\s+-r|printf\s+.*\\x[0-9a-f]{2})[^)]*\)[^"\']*["\']',
            re.IGNORECASE,
        ),
    ),
    _ObfuscationPattern(
        id="process-substitution-remote-exec",
        description="Shell process substitution from remote content",
        regex=re.compile(r"(?:sh|bash|zsh|dash|ksh|fish)\s+<\(\s*(?:curl|wget)\b", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="source-process-substitution-remote",
        description="source/. with process substitution from remote content",
        regex=re.compile(r"(?:^|[;&\s])(?:source|\.)\s+<\(\s*(?:curl|wget)\b", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="shell-heredoc-exec",
        description="Shell heredoc execution",
        regex=re.compile(r"(?:sh|bash|zsh|dash|ksh|fish)\s+<<-?\s*['\"]?[a-zA-Z_][\w-]*['\"]?", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="octal-escape",
        description="Bash octal escape sequences (potential command obfuscation)",
        regex=re.compile(r"\$'(?:[^']*\\[0-7]{3}){2,}"),
    ),
    _ObfuscationPattern(
        id="hex-escape",
        description="Bash hex escape sequences (potential command obfuscation)",
        regex=re.compile(r"\$'(?:[^']*\\x[0-9a-fA-F]{2}){2,}"),
    ),
    _ObfuscationPattern(
        id="python-exec-encoded",
        description="Python/Perl/Ruby with base64 or encoded execution",
        regex=re.compile(r"(?:python[23]?|perl|ruby)\s+-[ec]\s+.*(?:base64|b64decode|decode|exec|system|eval)", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="curl-pipe-shell",
        description="Remote content (curl/wget) piped to shell execution",
        regex=re.compile(r"(?:curl|wget)\s+.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.IGNORECASE),
    ),
    _ObfuscationPattern(
        id="var-expansion-obfuscation",
        description="Variable assignment chain with expansion (potential obfuscation)",
        regex=re.compile(r"(?:[a-zA-Z_]\w{0,2}=\S+\s*;\s*){2,}.*\$(?:[a-zA-Z_]|\{[a-zA-Z_])"),
    ),
]

_FALSE_POSITIVE_SUPPRESSIONS: list[tuple[list[str], re.Pattern[str]]] = [
    (
        ["curl-pipe-shell"],
        re.compile(r"curl\s+.*https?://(?:raw\.githubusercontent\.com/Homebrew|brew\.sh)\b", re.IGNORECASE),
    ),
    (
        ["curl-pipe-shell"],
        re.compile(
            r"curl\s+.*https?://(?:raw\.githubusercontent\.com/nvm-sh/nvm|sh\.rustup\.rs|get\.docker\.com|install\.python-poetry\.org)\b",
            re.IGNORECASE,
        ),
    ),
    (
        ["curl-pipe-shell"],
        re.compile(r"curl\s+.*https?://(?:get\.pnpm\.io|bun\.sh/install)\b", re.IGNORECASE),
    ),
]


def detect_command_obfuscation(command: str) -> ObfuscationDetection:
    """Detect obfuscated or encoded commands that could bypass security filters."""
    if not command or not command.strip():
        return ObfuscationDetection()

    reasons: list[str] = []
    matched_patterns: list[str] = []

    for pattern in OBFUSCATION_PATTERNS:
        if not pattern.regex.search(command):
            continue

        # Check false-positive suppressions
        url_count = len(re.findall(r"https?://\S+", command))
        suppressed = False
        if url_count <= 1:
            for suppresses, suppression_regex in _FALSE_POSITIVE_SUPPRESSIONS:
                if pattern.id in suppresses and suppression_regex.search(command):
                    suppressed = True
                    break

        if suppressed:
            continue

        matched_patterns.append(pattern.id)
        reasons.append(pattern.description)

    return ObfuscationDetection(
        detected=len(matched_patterns) > 0,
        reasons=reasons,
        matched_patterns=matched_patterns,
    )
