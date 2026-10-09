"""Abstract GitHub client interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GitHubRepo:
    """Metadata about a GitHub repository."""

    owner: str
    name: str
    default_branch: str = "main"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GitHubFile:
    """A file retrieved from a GitHub repository."""

    path: str
    content: str
    sha: str
    size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class GitHubClient(ABC):
    """Abstract base class for GitHub API access.

    Hides authentication, rate-limiting, and HTTP details behind a clean
    interface so the engine can work with any GitHub integration layer.
    """

    @abstractmethod
    async def get_repo(self, owner: str, name: str) -> GitHubRepo:
        """Fetch repository metadata.

        Args:
            owner: Repository owner (user or org).
            name: Repository name.

        Returns:
            A GitHubRepo with the repository metadata.
        """
        ...

    @abstractmethod
    async def get_file(self, owner: str, name: str, path: str, ref: str = "main") -> GitHubFile:
        """Fetch a single file from a repository.

        Args:
            owner: Repository owner.
            name: Repository name.
            path: File path within the repo.
            ref: Branch, tag, or commit SHA.

        Returns:
            A GitHubFile with the file content.
        """
        ...

    @abstractmethod
    async def list_files(
        self, owner: str, name: str, path: str = "", ref: str = "main"
    ) -> list[str]:
        """List file paths under a directory in a repository.

        Args:
            owner: Repository owner.
            name: Repository name.
            path: Directory path (empty string for root).
            ref: Branch, tag, or commit SHA.

        Returns:
            A list of file paths relative to the repository root.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the GitHub API is reachable and authenticated."""
        ...
