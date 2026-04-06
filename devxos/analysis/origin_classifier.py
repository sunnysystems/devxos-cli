"""Commit origin classifier — determines whether a commit is human, AI-assisted, or bot.

Heuristics (first match wins):
1. Co-author patterns: copilot, claude/anthropic, cursor, codeium, tabnine, amazon-q, gemini → AI_ASSISTED
2. Author patterns: [bot], dependabot, renovate, github-actions, mergify → BOT
3. Default: HUMAN

Rules:
- Case-insensitive matching
- Deterministic: same input always produces same output
- No ML, NLP, or external APIs
"""

import re
from enum import Enum

from devxos.models.commit import Commit


class CommitOrigin(Enum):
    """Origin attribution for a commit."""

    HUMAN = "HUMAN"
    AI_ASSISTED = "AI_ASSISTED"
    BOT = "BOT"


# Co-author email patterns that indicate AI assistance
_AI_CO_AUTHOR_PATTERNS = re.compile(
    r"copilot|github-copilot|claude|anthropic|cursor|codeium|tabnine|amazon-q|gemini",
    re.IGNORECASE,
)

# Author name patterns that indicate bot commits
_BOT_AUTHOR_PATTERNS = re.compile(
    r"\[bot\]|dependabot|renovate|github-actions|mergify",
    re.IGNORECASE,
)


def classify_origin(commit: Commit) -> CommitOrigin:
    """Classify a commit by its origin (human, AI-assisted, or bot).

    Args:
        commit: A Commit object with author and co_authors.

    Returns:
        CommitOrigin enum value.
    """
    # Heuristic 1: co-author patterns → AI_ASSISTED
    for email in commit.co_authors:
        if _AI_CO_AUTHOR_PATTERNS.search(email):
            return CommitOrigin.AI_ASSISTED

    # Heuristic 2: author patterns → BOT
    if _BOT_AUTHOR_PATTERNS.search(commit.author):
        return CommitOrigin.BOT

    # Default: HUMAN
    return CommitOrigin.HUMAN


# Tool-specific patterns for granular AI tool identification.
# Order matters: first match wins.
_TOOL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"copilot|github-copilot", re.IGNORECASE), "Copilot"),
    (re.compile(r"claude|anthropic", re.IGNORECASE), "Claude"),
    (re.compile(r"cursor", re.IGNORECASE), "Cursor"),
    (re.compile(r"codeium", re.IGNORECASE), "Codeium"),
    (re.compile(r"tabnine", re.IGNORECASE), "Tabnine"),
    (re.compile(r"amazon-q", re.IGNORECASE), "Amazon Q"),
    (re.compile(r"gemini", re.IGNORECASE), "Gemini"),
]


def detect_tool(commit: Commit) -> str | None:
    """Detect the specific AI tool from a commit's co-author patterns.

    Returns the tool name (e.g. "Copilot", "Claude") or None if no AI tool
    is detected. Only meaningful when classify_origin returns AI_ASSISTED.
    """
    for email in commit.co_authors:
        for pattern, tool_name in _TOOL_PATTERNS:
            if pattern.search(email):
                return tool_name
    return None


def classify_origins(commits: list[Commit]) -> list[tuple[Commit, CommitOrigin]]:
    """Classify a batch of commits by origin.

    Args:
        commits: List of Commit objects.

    Returns:
        List of (commit, origin) tuples in the same order.
    """
    return [(c, classify_origin(c)) for c in commits]
