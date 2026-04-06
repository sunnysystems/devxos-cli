"""Revert detection — identifies commits that revert previous work.

Detection strategy (v0):
  Pattern matching on commit messages. Git-generated reverts follow
  predictable patterns like 'Revert "..."' or 'This reverts commit <hash>'.

  This is an imperfect proxy — manual reverts or squashed reverts may be
  missed. The heuristic is intentionally conservative to avoid false positives.

Assumption:
  Only message-based detection is used in v0. Diff-based detection
  (checking if a commit exactly undoes another) may be added later.
"""

import re
from dataclasses import dataclass

from devxos.models.commit import Commit

# Patterns that indicate a revert commit
_REVERT_PATTERNS = [
    re.compile(r"^Revert\s+\"", re.IGNORECASE),
    re.compile(r"^Revert\s+\S", re.IGNORECASE),
    re.compile(r"This reverts commit\s+[0-9a-f]+", re.IGNORECASE),
]


@dataclass(frozen=True)
class RevertResult:
    """Result of revert analysis on a set of commits."""

    commits_total: int
    commits_revert: int
    revert_rate: float
    revert_hashes: list[str]


def is_revert(commit: Commit) -> bool:
    """Check if a commit message matches known revert patterns."""
    for pattern in _REVERT_PATTERNS:
        if pattern.search(commit.message):
            return True
    return False


def detect_reverts(commits: list[Commit]) -> RevertResult:
    """Analyze a list of commits and calculate revert metrics.

    Args:
        commits: List of Commit objects (from git_reader).

    Returns:
        RevertResult with counts and revert rate.
    """
    total = len(commits)
    revert_hashes = [c.hash for c in commits if is_revert(c)]
    revert_count = len(revert_hashes)

    rate = revert_count / total if total > 0 else 0.0

    return RevertResult(
        commits_total=total,
        commits_revert=revert_count,
        revert_rate=rate,
        revert_hashes=revert_hashes,
    )
