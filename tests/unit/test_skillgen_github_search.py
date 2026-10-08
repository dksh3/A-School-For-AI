"""1A-2Z Phase 2: deterministic query generation and bounded repository search.

A stub client stands in for GitHubClient so no test ever reaches the network.
"""

from __future__ import annotations

import pytest

from core.skillgen.github import search as search_mod
from core.skillgen.github.cache import TTLCache
from core.skillgen.github.client import GitHubError
from core.skillgen.github.models import RepoMeta
from core.skillgen.github.search import generate_queries, repo_meta_from_api, search

Payload = dict[str, object]


class StubClient:
    """Only the search_repositories surface used by search() is implemented."""

    def __init__(self, script: dict[str, list[object] | GitHubError]) -> None:
        self._script = script
        self.calls: list[str] = []

    def search_repositories(self, query: str, per_page: int = 10) -> list[object]:
        self.calls.append(query)
        result = self._script[query]
        if isinstance(result, GitHubError):
            raise result
        return result


def item(owner: str, name: str, **extra: object) -> Payload:
    payload: Payload = {
        "owner": {"login": owner},
        "name": name,
        "html_url": f"https://github.com/{owner}/{name}",
    }
    payload.update(extra)
    return payload


class TestGenerateQueries:
    def test_same_input_yields_identical_queries(self) -> None:
        kwargs = {"capability_gap": "pdf table extraction", "keywords": ["ocr", "tables"]}
        first = generate_queries(**kwargs)
        second = generate_queries(**kwargs)
        assert first == second
        assert first
        assert len(first) <= search_mod.MAX_GITHUB_QUERIES

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"capability_gap": "pdf table extraction"},
            {"task": "extract tables from pdfs"},
            {"keywords": ["ocr"]},
            {"skill_name": "pdf-tools"},
        ],
    )
    def test_any_supplied_input_produces_queries(self, kwargs: dict[str, object]) -> None:
        queries = generate_queries(**kwargs)
        assert queries
        assert all(queries)

    def test_blank_inputs_yield_no_queries(self) -> None:
        assert generate_queries() == []
        assert generate_queries(task="", capability_gap="", keywords=None, skill_name="") == []
        assert generate_queries(task="   ", capability_gap="  ", keywords=["", "  "]) == []

    def test_max_queries_cap_is_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(search_mod, "MAX_GITHUB_QUERIES", 1)
        queries = generate_queries(
            capability_gap="pdf extraction", keywords=["ocr", "tables"], skill_name="pdf-tools"
        )
        assert len(queries) == 1

    def test_queries_are_bounded_clean_and_deduplicated(self) -> None:
        queries = generate_queries(
            capability_gap='"pdf\nextraction" ' + "word " * 40,
            keywords=["ocr", " ocr "],
        )
        assert queries
        assert len(set(queries)) == len(queries)
        for query in queries:
            assert len(query) <= 100
            assert query == query.strip()
            assert '"' not in query
            assert "\n" not in query
            assert "  " not in query


class TestSearch:
    def test_deduplicates_repos_by_full_name(self) -> None:
        first = item("octo", "pdf-tools")
        second = item("octo", "ocr-tools")
        client = StubClient({"q1": [first], "q2": [first, second]})
        result = search(client, ["q1", "q2"], cache=TTLCache())
        assert [repo.full_name for repo in result.repos] == ["octo/pdf-tools", "octo/ocr-tools"]
        assert result.repos_found == 2
        assert result.filtered_out == {"duplicate_repo": 1}
        assert result.queries == ["q1", "q2"]
        assert result.errors == []

    def test_malformed_items_are_counted_and_skipped(self) -> None:
        bad: list[object] = [
            None,
            "not-a-dict",
            {"name": "missing-owner"},
            {"owner": {"login": "o"}, "name": ""},
        ]
        client = StubClient({"q1": [*bad, item("octo", "good")]})
        result = search(client, ["q1"], cache=TTLCache())
        assert result.filtered_out == {"malformed_item": 4}
        assert [repo.full_name for repo in result.repos] == ["octo/good"]
        assert result.errors == []

    def test_rate_limited_error_stops_search_and_keeps_partial_results(self) -> None:
        client = StubClient(
            {
                "q1": [item("octo", "one")],
                "q2": GitHubError("rate_limited", "rate limited (retry-after=1)", 429),
                "q3": [item("octo", "three")],
            }
        )
        result = search(client, ["q1", "q2", "q3"], cache=TTLCache())
        assert client.calls == ["q1", "q2"]
        assert [repo.full_name for repo in result.repos] == ["octo/one"]
        assert result.repos_found == 1
        assert len(result.errors) == 1
        assert "github_rate_limited" in result.errors[0]

    def test_network_error_stops_search_early(self) -> None:
        client = StubClient(
            {
                "q1": [item("octo", "one")],
                "q2": GitHubError("network", "connection refused"),
                "q3": [item("octo", "three")],
            }
        )
        result = search(client, ["q1", "q2", "q3"], cache=TTLCache())
        assert client.calls == ["q1", "q2"]
        assert [repo.full_name for repo in result.repos] == ["octo/one"]
        assert len(result.errors) == 1
        assert "github_network" in result.errors[0]

    def test_http_error_is_recorded_but_search_continues(self) -> None:
        client = StubClient(
            {
                "q1": GitHubError("http", "status 500", 500),
                "q2": [item("octo", "two")],
            }
        )
        result = search(client, ["q1", "q2"], cache=TTLCache())
        assert client.calls == ["q1", "q2"]
        assert [repo.full_name for repo in result.repos] == ["octo/two"]
        assert len(result.errors) == 1
        assert "github_http" in result.errors[0]

    def test_repeated_queries_are_served_from_cache(self) -> None:
        client = StubClient({"q1": [item("octo", "one")]})
        cache = TTLCache()
        first = search(client, ["q1"], cache=cache)
        second = search(client, ["q1"], cache=cache)
        assert client.calls == ["q1"]
        assert second.repos == first.repos
        assert second.repos_found == first.repos_found

    def test_cache_is_keyed_per_query(self) -> None:
        client = StubClient({"q1": [item("octo", "one")], "q2": [item("octo", "two")]})
        cache = TTLCache()
        search(client, ["q1"], cache=cache)
        search(client, ["q1", "q2"], cache=cache)
        assert client.calls == ["q1", "q2"]

    def test_max_repositories_cap_is_enforced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(search_mod, "MAX_REPOSITORIES", 2)
        client = StubClient({f"q{i}": [item("octo", f"r{i}")] for i in range(5)})
        result = search(client, [f"q{i}" for i in range(5)], cache=TTLCache())
        assert result.repos_found == 2
        assert client.calls == ["q0", "q1"]


class TestRepoMetaFromApi:
    def test_valid_payload_becomes_repo_meta(self) -> None:
        meta = repo_meta_from_api(
            item(
                "octo",
                "pdf-tools",
                description="pdf helpers",
                stargazers_count=7,
                forks_count=2,
                watchers_count=7,
                language="Python",
                topics=["ocr", "pdf"],
                license={"spdx_id": "MIT", "url": "https://x/mit"},
                default_branch="trunk",
                archived=True,
                fork=True,
                size=12,
            )
        )
        assert isinstance(meta, RepoMeta)
        assert meta.full_name == "octo/pdf-tools"
        assert meta.url == "https://github.com/octo/pdf-tools"
        assert meta.stars == 7
        assert meta.topics == ["ocr", "pdf"]
        assert meta.license == "MIT"
        assert meta.default_branch == "trunk"
        assert meta.archived is True
        assert meta.fork is True
        assert meta.size_kb == 12

    @pytest.mark.parametrize(
        "payload",
        [
            {"name": "orphan"},
            {"owner": {"login": "o"}},
            {"owner": {"login": "o"}, "name": "n", "stargazers_count": "many"},
        ],
    )
    def test_malformed_payloads_become_none(self, payload: Payload) -> None:
        assert repo_meta_from_api(payload) is None
