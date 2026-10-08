"""1A-2Z Phase 2: GitHub client transport, auth, rate limits, and error kinds.

Every test injects a scripted transport or patches urllib, so no test ever
reaches the real network. Tokens must never surface in reprs or messages.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

import pytest

from core.skillgen.github.client import (
    MAX_BACKOFF_S,
    MAX_RETRIES,
    GitHubClient,
    GitHubError,
    default_client,
)

TOKEN = "ghp_value_that_must_never_leak"

Response = tuple[int, dict[str, str], str]


@dataclass
class RecordedCall:
    method: str
    url: str
    headers: dict[str, str]
    timeout: float


class ScriptedTransport:
    """Fake transport: replays scripted responses in order (last one repeats)."""

    def __init__(self, *responses: Response | Exception) -> None:
        if not responses:
            raise ValueError("need at least one scripted response")
        self._responses = list(responses)
        self.calls: list[RecordedCall] = []

    def __call__(self, method: str, url: str, headers: dict[str, str], timeout: float) -> Response:
        self.calls.append(
            RecordedCall(method=method, url=url, headers=dict(headers), timeout=timeout)
        )
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def build(
    *responses: Response | Exception, token: str | None = ""
) -> tuple[GitHubClient, ScriptedTransport, list[float]]:
    """Client wired to a scripted transport plus a recording sleep() double."""
    transport = ScriptedTransport(*responses)
    delays: list[float] = []
    client = GitHubClient(token=token, transport=transport, sleep=delays.append)
    return client, transport, delays


def ok_json(data: object) -> Response:
    return 200, {}, json.dumps(data)


class TestAuthHeaders:
    def test_unauthenticated_client_omits_authorization_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        client, transport, _ = build(ok_json({"full_name": "octo/repo"}), token=None)
        client.get_repository("octo", "repo")
        headers = transport.calls[0].headers
        assert "Authorization" not in headers
        assert headers["User-Agent"].startswith("school-skillgen/")
        assert headers["Accept"] == "application/vnd.github+json"
        assert client.authenticated is False

    def test_token_adds_bearer_authorization_header(self) -> None:
        client, transport, _ = build(ok_json({"full_name": "octo/repo"}), token=TOKEN)
        client.get_repository("octo", "repo")
        assert transport.calls[0].headers["Authorization"] == f"Bearer {TOKEN}"
        assert client.authenticated is True

    def test_token_is_read_from_environment_when_not_supplied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
        client, transport, _ = build(ok_json({"full_name": "octo/repo"}), token=None)
        client.get_repository("octo", "repo")
        assert transport.calls[0].headers["Authorization"] == f"Bearer {TOKEN}"


class TestTokenSafety:
    def test_repr_and_str_never_contain_token(self) -> None:
        client, _, _ = build(ok_json({}), token=TOKEN)
        assert TOKEN not in repr(client)
        assert TOKEN not in str(client)
        assert repr(client) == "GitHubClient(authenticated=True)"

    def test_rate_limit_error_message_never_contains_token(self) -> None:
        client, _, _ = build((429, {"retry-after": "1"}, "slow down"), token=TOKEN)
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        message = str(excinfo.value)
        assert TOKEN not in message
        assert message.startswith("github_rate_limited:")


class TestRateLimitHandling:
    def test_429_raises_rate_limited_after_bounded_retries(self) -> None:
        client, transport, delays = build((429, {}, ""))
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        error = excinfo.value
        assert error.kind == "rate_limited"
        assert error.status == 429
        assert "rate limited" in str(error)
        assert len(transport.calls) == MAX_RETRIES + 1
        assert delays == pytest.approx([2.0 * (i + 1) for i in range(MAX_RETRIES)])
        assert all(delay <= MAX_BACKOFF_S for delay in delays)

    def test_retry_after_header_is_honored_and_capped(self) -> None:
        client, transport, delays = build((429, {"retry-after": "9999"}, "wait"))
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "rate_limited"
        assert len(transport.calls) == MAX_RETRIES + 1
        assert delays == pytest.approx([MAX_BACKOFF_S] * MAX_RETRIES)

    @pytest.mark.parametrize(
        ("headers", "body"),
        [
            ({"x-ratelimit-remaining": "0"}, "quota spent"),
            ({}, "You have exceeded a secondary rate limit."),
        ],
    )
    def test_403_rate_limit_signals_raise_rate_limited(
        self, headers: dict[str, str], body: str
    ) -> None:
        client, transport, delays = build((403, headers, body))
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "rate_limited"
        assert excinfo.value.status == 403
        assert len(transport.calls) == MAX_RETRIES + 1
        assert len(delays) == MAX_RETRIES

    def test_403_without_rate_limit_signals_is_http_error(self) -> None:
        client, transport, delays = build((403, {}, "resource forbidden"))
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "http"
        assert excinfo.value.status == 403
        assert len(transport.calls) == 1
        assert delays == []

    def test_success_after_rate_limit_retries_is_returned(self) -> None:
        client, transport, delays = build(
            (429, {"retry-after": "0"}, ""),
            (429, {"retry-after": "0"}, ""),
            ok_json({"full_name": "octo/repo"}),
        )
        data = client.get_repository("octo", "repo")
        assert data["full_name"] == "octo/repo"
        assert len(transport.calls) == 3
        assert delays == pytest.approx([0.0, 0.0])


class TestErrorKinds:
    def test_malformed_json_body_raises_malformed_error(self) -> None:
        client, _, _ = build((200, {}, "<html>oops</html>"))
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "malformed"
        assert excinfo.value.status == 200
        assert "github_malformed:" in str(excinfo.value)

    def test_5xx_raises_http_error_with_bounded_transport_calls(self) -> None:
        client, transport, delays = build((500, {}, "server exploded"), token=TOKEN)
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        error = excinfo.value
        assert error.kind == "http"
        assert error.status == 500
        assert len(transport.calls) <= MAX_RETRIES + 1
        assert all(delay <= MAX_BACKOFF_S for delay in delays)
        assert TOKEN not in str(error)

    def test_network_error_is_not_retried(self) -> None:
        client, transport, delays = build(GitHubError("network", "connection refused"))
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "network"
        assert "connection refused" in str(excinfo.value)
        assert len(transport.calls) == 1
        assert delays == []


class TestUrllibTransport:
    @pytest.mark.parametrize(
        ("failure", "needle"),
        [
            (urllib.error.URLError("dns failure"), "dns failure"),
            (OSError("connection reset"), "connection reset"),
        ],
    )
    def test_socket_level_failures_become_network_errors(
        self, monkeypatch: pytest.MonkeyPatch, failure: Exception, needle: str
    ) -> None:
        def raise_failure(request: object, timeout: object) -> object:
            raise failure

        monkeypatch.setattr(urllib.request, "urlopen", raise_failure)
        client = GitHubClient(token="")
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "network"
        assert needle in str(excinfo.value)

    def test_http_error_response_surfaces_as_http_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_http_error(request: object, timeout: object) -> object:
            raise urllib.error.HTTPError(
                "https://api.github.com/octo/repo", 404, "Not Found",
                {"Server": "GitHub"}, io.BytesIO(b"denied"),
            )

        monkeypatch.setattr(urllib.request, "urlopen", raise_http_error)
        client = GitHubClient(token="")
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "http"
        assert excinfo.value.status == 404


class TestDefaultClient:
    @pytest.mark.parametrize("value", ["1", "true"])
    def test_disabled_flag_raises_disabled_error(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("SCHOOL_SKILLGEN_GITHUB_DISABLED", value)
        with pytest.raises(GitHubError) as excinfo:
            default_client()
        assert excinfo.value.kind == "disabled"
        assert excinfo.value.status == 0


class TestGetFileContent:
    def test_base64_payload_is_decoded_to_text(self) -> None:
        payload = base64.b64encode(b"# My Skill\n").decode()
        client, transport, _ = build(
            ok_json({"type": "file", "size": 11, "encoding": "base64", "content": payload})
        )
        text = client.get_file_content("octo", "repo", "SKILL.md")
        assert text == "# My Skill\n"
        assert "/contents/SKILL.md" in transport.calls[0].url

    def test_file_over_env_cap_raises_413(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_SKILLGEN_GITHUB_MAX_FILE_BYTES", "10")
        client, _, _ = build(
            ok_json({"type": "file", "size": 999, "encoding": "base64", "content": "AA=="})
        )
        with pytest.raises(GitHubError) as excinfo:
            client.get_file_content("octo", "repo", "huge.md")
        assert excinfo.value.kind == "http"
        assert excinfo.value.status == 413
        assert "too large" in str(excinfo.value)

    def test_decoded_text_is_truncated_to_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_SKILLGEN_GITHUB_MAX_FILE_BYTES", "5")
        payload = base64.b64encode(b"hello world").decode()
        client, _, _ = build(
            ok_json({"type": "file", "size": 5, "encoding": "base64", "content": payload})
        )
        assert client.get_file_content("octo", "repo", "f.md") == "hello"

    def test_undecodable_base64_raises_malformed(self) -> None:
        client, _, _ = build(
            ok_json({"type": "file", "size": 3, "encoding": "base64", "content": "abc"})
        )
        with pytest.raises(GitHubError) as excinfo:
            client.get_file_content("octo", "repo", "broken.md")
        assert excinfo.value.kind == "malformed"
        assert "undecodable" in str(excinfo.value)

    @pytest.mark.parametrize(
        "data",
        [
            {"type": "dir", "size": 1},
            {"type": "file", "size": 5, "encoding": "", "download_url": "https://x/f.md"},
            {"type": "file", "size": 5, "encoding": ""},
        ],
    )
    def test_unusable_payloads_raise_malformed(self, data: dict[str, object]) -> None:
        client, _, _ = build(ok_json(data))
        with pytest.raises(GitHubError) as excinfo:
            client.get_file_content("octo", "repo", "f.md")
        assert excinfo.value.kind == "malformed"


class TestGetTree:
    def test_tree_returns_blob_paths_only(self) -> None:
        tree: list[object] = [
            {"type": "tree", "path": "src"},
            {"type": "blob", "path": "SKILL.md"},
            {"type": "blob"},
            "not-a-dict",
            {"type": "commit", "path": "sub"},
            {"type": "blob", "path": "src/main.py"},
        ]
        client, transport, _ = build(ok_json({"sha": "abc", "tree": tree}))
        assert client.get_tree("octo", "repo") == ["SKILL.md", "src/main.py"]
        assert transport.calls[0].url.endswith("?recursive=1")

    def test_tree_capped_by_env_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOOL_SKILLGEN_GITHUB_MAX_TREE_ENTRIES", "3")
        tree = [{"type": "blob", "path": f"file{i}.md"} for i in range(10)]
        client, _, _ = build(ok_json({"tree": tree}))
        paths = client.get_tree("octo", "repo")
        assert paths == ["file0.md", "file1.md", "file2.md"]

    @pytest.mark.parametrize("data", [{"sha": "abc"}, {"tree": "nope"}])
    def test_malformed_tree_payload_raises_malformed(self, data: dict[str, object]) -> None:
        client, _, _ = build(ok_json(data))
        with pytest.raises(GitHubError) as excinfo:
            client.get_tree("octo", "repo")
        assert excinfo.value.kind == "malformed"


class TestSearchRepositories:
    def test_search_requires_items_list(self) -> None:
        client, _, _ = build(ok_json({"total_count": 0}))
        with pytest.raises(GitHubError) as excinfo:
            client.search_repositories("pdf skill")
        assert excinfo.value.kind == "malformed"

    def test_search_clamps_per_page_and_sorts_by_stars(self) -> None:
        items = [{"name": "a"}, {"name": "b"}]
        client, transport, _ = build(ok_json({"total_count": 2, "items": items}))
        assert client.search_repositories("pdf skill", per_page=100) == items
        url = transport.calls[0].url
        assert "per_page=30" in url
        assert "sort=stars" in url
        assert "q=pdf+skill" in url


class TestTransientRetries:
    def test_5xx_recovers_after_bounded_retry(self) -> None:
        client, transport, delays = build(
            (500, {}, "server exploded"),
            (502, {}, "bad gateway"),
            ok_json({"full_name": "octo/repo"}),
        )
        data = client.get_repository("octo", "repo")
        assert data["full_name"] == "octo/repo"
        assert len(transport.calls) == 3
        assert len(delays) == 2
        assert all(delay <= MAX_BACKOFF_S for delay in delays)

    def test_5xx_retries_are_bounded_not_aggressive(self) -> None:
        client, transport, delays = build((503, {}, "service unavailable"))
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "http"
        assert excinfo.value.status == 503
        assert len(transport.calls) == MAX_RETRIES + 1
        assert len(delays) == MAX_RETRIES
        assert all(delay <= MAX_BACKOFF_S for delay in delays)

    @pytest.mark.parametrize(
        ("failure", "needle"),
        [
            (OSError("connection reset"), "connection reset"),
            (urllib.error.URLError("dns failure"), "dns failure"),
            (TimeoutError("request timed out"), "request timed out"),
        ],
    )
    def test_raw_transport_network_failures_are_wrapped(
        self, failure: Exception, needle: str
    ) -> None:
        client, transport, delays = build(failure)
        with pytest.raises(GitHubError) as excinfo:
            client.get_repository("octo", "repo")
        assert excinfo.value.kind == "network"
        assert needle in str(excinfo.value)
        assert len(transport.calls) == 1
        assert delays == []


class TestCommitSha:
    def test_get_commit_sha_returns_branch_head(self) -> None:
        client, transport, _ = build(ok_json({"sha": "deadbeef", "commit": {}}))
        assert client.get_commit_sha("octo", "repo", "main") == "deadbeef"
        assert "/repos/octo/repo/commits/main" in transport.calls[0].url

    def test_get_commit_sha_defaults_to_head(self) -> None:
        client, transport, _ = build(ok_json({"sha": "cafe1234"}))
        assert client.get_commit_sha("octo", "repo") == "cafe1234"
        assert transport.calls[0].url.endswith("/commits/HEAD")

    @pytest.mark.parametrize("data", [{}, {"sha": 123}, {"nope": "x"}])
    def test_malformed_commit_payload_raises_malformed(self, data: dict[str, object]) -> None:
        client, _, _ = build(ok_json(data))
        with pytest.raises(GitHubError) as excinfo:
            client.get_commit_sha("octo", "repo")
        assert excinfo.value.kind == "malformed"
