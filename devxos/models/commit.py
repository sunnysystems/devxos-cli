"""Commit data model used across ingestion and analysis modules."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class FileChange:
    """A single file changed in a commit."""

    path: str
    lines_added: int
    lines_removed: int


@dataclass(frozen=True)
class Commit:
    """A single Git commit with metadata and file-level changes."""

    hash: str
    author: str
    date: datetime
    message: str
    files: list[FileChange] = field(default_factory=list)
    is_merge: bool = False
    co_authors: list[str] = field(default_factory=list)
