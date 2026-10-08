"""Official GitHub API client for 1A-2Z Phase 2 (read-only, targeted).

Unauthenticated by default; optional GITHUB_TOKEN from the environment is
used for higher rate limits and is NEVER stored, logged, printed, or placed
in provenance/registry/prompts. All failures raise GitHubError (structured,
fail closed) so discovery failure cannot corrupt local state.

No repository cloning, no HTML scraping, no code execution.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

GITHUB_API_BASE = "https://api.github.com"
MAX_RETRIES = 2
MAX_BACKOFF_S = 8.0

# transport(method, url, headers, timeout) -> (status, response_headers, body)
Transport = Callable[[str, str, dict[str, str], float], tuple[int, dict[str, str], str]]


class GitHubError(RuntimeError):
    """Structured GitHub failure. Message never contains credentials."""

    def __init__(self, kind: str, message: str, status: int = 0) -> None:
        super().__init__(f"github_{kind}: {message}")
        self.kind = kind  # rate_limited | http | network | malformed | disabled
        self.status = status


@dataclass(slots=True)
class _Response:
    status: int
    headers: dict[str, str]
    body: str


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _urllib_transport(
    method: str, url: str, headers: dict[str, str], timeout: float
) -> tuple[int, dict[str, str], str]:
    req = urllib.request.Request(url, method=method, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return (
                resp.status,
                {k.lower(): v for k, v in resp.headers.items()},
                resp.read().decode("utf-8", errors="replace"),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return exc.code, hdrs, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        detail = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        raise GitHubError("network", str(detail)) from exc


class GitHubClient:
    """Minimal read-only client for api.github.com.

    ``transport`` is injectable so tests never touch the network.
    """

    def __init__(
        self,
        token: str | None = None,
        base_url: str = GITHUB_API_BASE,
        timeout: float | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # token=None -> read env; token="" -> explicitly unauthenticated.
        self._token = (
            os.environ.get("GITHUB_TOKEN", "").strip()
            if token is None
            else token.strip()
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = (
            timeout
            if timeout is not None
            else _env_float("SCHOOL_SKILLGEN_GITHUB_TIMEOUT", 15.0)
        )
        self._transport = transport or _urllib_transport
        self._sleep = sleep

    def __repr__(self) -> str:  # never leak the token
        return f"GitHubClient(authenticated={bool(self._token)})"

    @property
    def authenticated(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "school-skillgen/1a-2z-phase2",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        last: GitHubError | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                status, headers, body = self._transport("GET", url, self._headers(), self.timeout)
            except GitHubError:
                raise  # network failures are not retried aggressively
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                # Custom transports may raise raw network errors; wrap them so
                # every failure stays a structured, fail-closed GitHubError.
                detail = exc.reason if isinstance(exc, urllib.error.URLError) else exc
                raise GitHubError("network", str(detail)) from exc
            if status in (403, 429) and self._is_rate_limited(status, headers, body):
                last = GitHubError("rate_limited", self._rate_message(headers), status)
                backoff = self._backoff(headers, attempt)
                if backoff is not None and attempt < MAX_RETRIES:
                    self._sleep(backoff)
                    continue
                raise last
            if status >= 500:
                # Transient server errors get the same bounded backoff budget
                # as rate limits; never more than MAX_RETRIES extra attempts.
                last = GitHubError("http", f"status {status}", status)
                if attempt < MAX_RETRIES:
                    self._sleep(self._backoff(headers, attempt))
                    continue
                raise last
            if status >= 400:
                raise GitHubError("http", f"status {status}", status)
            if not body.strip():
                return {}
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise GitHubError("malformed", "invalid JSON response", status) from exc

    @staticmethod
    def _is_rate_limited(status: int, headers: dict[str, str], body: str) -> bool:
        if status == 429:
            return True
        if headers.get("x-ratelimit-remaining") == "0":
            return True
        return status == 403 and (
            "rate limit" in body.lower() or "secondary rate" in body.lower()
        )

    @staticmethod
    def _rate_message(headers: dict[str, str]) -> str:
        reset = headers.get("x-ratelimit-reset", "")
        retry = headers.get("retry-after", "")
        return f"rate limited (retry-after={retry or '-'} reset={reset or '-'})"

    def _backoff(self, headers: dict[str, str], attempt: int) -> float | None:
        retry = headers.get("retry-after")
        if retry is not None:
            try:
                return min(float(retry), MAX_BACKOFF_S)
            except ValueError:
                pass
        return min(2.0 * (attempt + 1), MAX_BACKOFF_S)

    # ---- API surface -------------------------------------------------

    def search_repositories(self, query: str, per_page: int = 10) -> list[dict[str, Any]]:
        """Repository search (capped). Returns raw items, bounded."""
        data = self._get(
            "/search/repositories",
            {"q": query, "per_page": max(1, min(int(per_page), 30)), "sort": "stars"},
        )
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise GitHubError("malformed", "search response missing items")
        return data["items"][:per_page]

    def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        data = self._get(f"/repos/{owner}/{repo}")
        if not isinstance(data, dict) or "full_name" not in data:
            raise GitHubError("malformed", "repository response invalid")
        return data

    def get_commit_sha(self, owner: str, repo: str, ref: str = "") -> str:
        """Best-effort head commit SHA for provenance (single cached call)."""
        branch = ref or "HEAD"
        data = self._get(f"/repos/{owner}/{repo}/commits/{urllib.parse.quote(branch)}")
        if not isinstance(data, dict) or not isinstance(data.get("sha"), str):
            raise GitHubError("malformed", "commit response invalid")
        return data["sha"]

    def get_tree(self, owner: str, repo: str, ref: str = "") -> list[str]:
        """Bounded repository tree (file paths only - never contents)."""
        branch = ref or "HEAD"
        data = self._get(
            f"/repos/{owner}/{repo}/git/trees/{urllib.parse.quote(branch)}",
            {"recursive": "1"},
        )
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
            raise GitHubError("malformed", "tree response invalid")
        entries = [e for e in data["tree"] if isinstance(e, dict) and e.get("type") == "blob"]
        max_entries = int(os.environ.get("SCHOOL_SKILLGEN_GITHUB_MAX_TREE_ENTRIES", "400") or 400)
        return [str(e.get("path", "")) for e in entries if e.get("path")][:max_entries]

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = "") -> str:
        """Targeted single-file retrieval (contents API). Never clones."""
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref
        data = self._get(
            f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}",
            params or None,
        )
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubError("malformed", "file content response invalid")
        size = int(data.get("size") or 0)
        max_size = int(os.environ.get("SCHOOL_SKILLGEN_GITHUB_MAX_FILE_BYTES", "65536") or 65536)
        if size > max_size:
            raise GitHubError("http", f"file too large ({size} > {max_size} bytes)", 413)
        encoding = str(data.get("encoding") or "")
        content = data.get("content")
        if encoding == "base64" and isinstance(content, str):
            try:
                text = base64.b64decode(content).decode("utf-8", errors="replace")
            except (ValueError, TypeError) as exc:
                raise GitHubError("malformed", "undecodable file content") from exc
            return text[:max_size]
        if isinstance(data.get("download_url"), str):
            raise GitHubError("malformed", "inline content unavailable (git LFS or empty)")
        raise GitHubError("malformed", "file content unavailable")


def default_client() -> GitHubClient:
    """Client honoring GITHUB_TOKEN if present (never required)."""
    if os.environ.get("SCHOOL_SKILLGEN_GITHUB_DISABLED", ""):
        raise GitHubError("disabled", "GitHub discovery disabled by configuration")
    return GitHubClient()


__all__ = ["GITHUB_API_BASE", "GitHubClient", "GitHubError", "default_client"]
