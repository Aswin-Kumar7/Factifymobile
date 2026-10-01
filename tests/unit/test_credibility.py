"""Publisher credibility gates which open-web sources are worth citing."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from app.sources.credibility import SourceCredibility

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "source_credibility.json"

# A bare registrable host: lowercase labels of letters, digits and inner hyphens, at
# least two of them. No scheme, no path, no port, no www, no trailing dot.
_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
_HOST = re.compile(rf"^(?!www\.)(?:{_LABEL}\.)+{_LABEL}$")


def _credibility() -> SourceCredibility:
    # The real curated list, so the test breaks if a trusted domain is dropped from it.
    return SourceCredibility.load()


def _raw() -> dict[str, object]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _entries() -> list[tuple[str, str]]:
    return [
        (category, entry)
        for category, value in _raw().items()
        if not category.startswith("_") and isinstance(value, list)
        for entry in value
    ]


class TestIsCredible:
    def test_listed_fact_checkers_and_outlets_are_citable(self) -> None:
        cred = _credibility()
        for url in (
            "https://fullfact.org/online/5g-and-coronavirus",
            "https://www.theatlantic.com/technology/archive/2020/05/x",
            "https://apnews.com/article/x",
            "https://en.wikipedia.org/wiki/5G_misinformation",
        ):
            assert cred.is_credible(url), url

    def test_government_education_and_intl_tlds_are_citable_by_pattern(self) -> None:
        cred = _credibility()
        for url in (
            "https://www.gov.uk/guidance/5g-and-coronavirus",
            "https://www.who.int/news/item/x",
            "https://www.mit.edu/research/x",
            "https://pib.gov.in/PressRelease.aspx",
        ):
            assert cred.is_credible(url), url

    def test_a_subdomain_of_a_trusted_domain_is_citable(self) -> None:
        assert _credibility().is_credible("https://news.bbc.co.uk/story/1")

    def test_unknown_and_junk_domains_are_not_citable(self) -> None:
        cred = _credibility()
        for url in (
            "https://frankreport.com/2020/03/25/5g-and-covid",
            "https://beforeitsnews.com/x",
            "https://randomblog12345.xyz/post",
            "https://mybroadband.co.za/news/5g/x",  # a real outlet, but not on the list
        ):
            assert not cred.is_credible(url), url

    def test_missing_or_malformed_input_is_not_citable(self) -> None:
        cred = _credibility()
        assert not cred.is_credible(None)
        assert not cred.is_credible("")
        assert not cred.is_credible("not a url")
        assert not cred.is_credible("http://[::1")

    def test_an_empty_list_still_trusts_tld_patterns(self) -> None:
        # An unreadable credibility file must fail closed on named domains but still
        # trust governments and universities — stricter, never looser.
        empty = SourceCredibility(frozenset())
        assert empty.is_credible("https://www.who.int/x")
        assert not empty.is_credible("https://fullfact.org/x")

    def test_a_commercial_site_under_a_trusted_suffix_is_not_citable(self) -> None:
        # academia.edu holds a pre-restriction .edu registration but is an upload site;
        # the exception holds even with no data file, and a real university still passes.
        for cred in (_credibility(), SourceCredibility(frozenset())):
            assert not cred.is_credible("https://www.academia.edu/12345/uploaded_paper")
            assert cred.is_credible("https://web.mit.edu/news/x")

    def test_lookalike_and_userinfo_hosts_are_judged_by_the_real_host(self) -> None:
        cred = SourceCredibility(frozenset({"thehindu.com"}))
        assert not cred.is_credible("https://thehindu.com.evil.net/x")
        assert not cred.is_credible("https://fakethehindu.com/x")
        # userinfo is not the host: this request goes to evil.com
        assert not cred.is_credible("https://thehindu.com@evil.com/x")
        assert cred.is_credible("https://evil.com@thehindu.com/x")

    def test_an_open_user_section_on_a_credible_host_is_not_citable(self) -> None:
        cred = SourceCredibility(
            frozenset({"timesofindia.indiatimes.com"}),
            {"timesofindia.indiatimes.com": ("/readersblog/",)},
        )
        reporting = "https://timesofindia.indiatimes.com/india/x/articleshow/1.cms"
        reader_post = "https://timesofindia.indiatimes.com/readersblog/someone/post-1/"
        assert cred.is_credible(reporting)
        assert not cred.is_credible(reader_post)
        # the exclusion is a path rule, so a bare host is still credible
        assert cred.is_credible("timesofindia.indiatimes.com")


class TestCoverage:
    """The list reaches beyond English-language national outlets — regional and international."""

    def test_regional_language_indian_publishers_are_citable(self) -> None:
        cred = _credibility()
        for url in (
            "https://www.manoramaonline.com/news/latest-news/2026/09/17/x.html",  # Malayalam
            "https://www.bhaskar.com/local/rajasthan/news/x-123.html",  # Hindi
            "https://www.anandabazar.com/west-bengal/x/cid/1",  # Bengali
            "https://www.eenadu.net/telugu-news/india/x/1",  # Telugu
            "https://www.dailythanthi.com/news/state/x-1",  # Tamil
            "https://www.prajavani.net/district/x-1",  # Kannada
            "https://www.lokmat.com/maharashtra/x/",  # Marathi
            "https://www.gujaratsamachar.com/news/gujarat/x",  # Gujarati
            "https://www.asomiyapratidin.in/assam/x",  # Assamese
            "https://sambad.in/odisha/x",  # Odia
            "https://www.greaterkashmir.com/srinagar/x",  # Jammu & Kashmir
        ):
            assert cred.is_credible(url), url

    def test_south_asian_and_international_publishers_are_citable(self) -> None:
        cred = _credibility()
        for url in (
            "https://www.dawn.com/news/1900000",  # Pakistan
            "https://www.thedailystar.net/news/bangladesh/x",  # Bangladesh
            "https://kathmandupost.com/national/2026/09/17/x",  # Nepal
            "https://www.lemonde.fr/international/article/2026/09/17/x.html",  # France
            "https://maldita.es/malditobulo/x",  # EFCSN fact-checker
            "https://www.un.org/en/x",  # international organisation
            "https://www.kantei.go.jp/jp/x",  # a government suffix outside the code patterns
            "https://www.tifr.res.in/x",  # India's restricted research suffix
        ):
            assert cred.is_credible(url), url

    def test_sports_newsrooms_are_citable(self) -> None:
        """ "India won the 2024 T20 World Cup" abstained: every cricket source was dropped."""
        cred = _credibility()
        for url in (
            "https://www.espncricinfo.com/series/icc-men-s-t20-world-cup-2024",
            "https://www.cricbuzz.com/cricket-news/1",
            "https://www.espn.com/cricket/story/_/id/1",
        ):
            assert cred.is_credible(url), url
            assert cred.credibility(url).value == "MEDIUM", url

    def test_outlets_added_on_2026_09_26_are_citable_and_read_early(self) -> None:
        """An MEA debunk reported by News18 and Firstpost read "Unconfirmed": both
        were dropped as not credible, and neither had ever been assessed."""
        cred = _credibility()
        for url in (
            "https://www.news18.com/india/brics-summit-mea-fact-check-9571234.html",
            "https://www.firstpost.com/india/mea-fact-check-breakfast-13901234.html",
            "https://www.freepressjournal.in/india/mea-debunks-breakfast-claim",
            "https://thehill.com/homenews/administration/6110866-trump-xi-white-house-dinner/",
        ):
            assert cred.is_credible(url), url
            assert cred.credibility(url).value == "MEDIUM", url
            assert cred.is_prominent(url), url

    def test_times_of_india_reporting_is_citable_but_its_open_sections_are_not(self) -> None:
        cred = _credibility()
        assert cred.is_credible("https://timesofindia.indiatimes.com/india/x/articleshow/1.cms")
        assert not cred.is_credible(
            "https://timesofindia.indiatimes.com/readersblog/someone/post-1/"
        )
        assert not cred.is_credible("https://timesofindia.indiatimes.com/blogs/voices/x/")

    def test_documented_exclusions_stay_excluded(self) -> None:
        # Each is sourced in the file's _criteria; adding one back is a decision, not a typo.
        cred = _credibility()
        for url in (
            "https://www.aninews.in/news/x",  # EU DisinfoLab: quoted fabricated sources
            "https://english.news.cn/x",  # Xinhua: state propaganda outlet
            "https://www.sakshi.com/news/x",  # controlled by the YSRCP president's family
            "https://www.academia.edu/1/x",  # open upload site under .edu
            "https://arxiv.org/abs/2601.00001",  # preprint server, not peer reviewed
        ):
            assert not cred.is_credible(url), url


class TestCredibilityData:
    """The curated file itself: shape, hygiene, and that every entry actually loads."""

    def test_categories_are_lists_except_the_user_content_map(self) -> None:
        for key, value in _raw().items():
            if key.startswith("_"):
                continue
            if key == "user_content_paths":
                assert isinstance(value, dict), key
            else:
                # A nested object here would be silently skipped by the loader.
                assert isinstance(value, list) and value, key

    def test_every_entry_is_a_bare_lowercase_host(self) -> None:
        bad = [f"{c}: {e!r}" for c, e in _entries() if not _HOST.match(e)]
        assert not bad, bad

    def test_no_entry_is_listed_twice(self) -> None:
        seen: dict[str, str] = {}
        dupes = []
        for category, entry in _entries():
            if entry in seen:
                dupes.append(f"{entry} in {seen[entry]} and {category}")
            seen[entry] = category
        assert not dupes, dupes

    def test_no_entry_is_redundant(self) -> None:
        # Redundant under another listed entry (news.x.com beside x.com) or already
        # trusted by a code pattern (anything under gov.in) — it adds nothing but noise.
        hosts = {entry for _, entry in _entries()}
        patterns_only = SourceCredibility(frozenset())
        redundant = sorted(
            entry
            for entry in hosts
            if any(entry.endswith("." + other) for other in hosts if other != entry)
            or patterns_only.is_credible(entry)
        )
        assert not redundant, redundant

    def test_the_loader_reads_every_entry(self) -> None:
        cred = _credibility()
        missing = [entry for _, entry in _entries() if not cred.is_credible(entry)]
        assert not missing, missing

    def test_user_content_paths_are_well_formed_and_on_listed_hosts(self) -> None:
        cred = _credibility()
        for host, prefixes in dict(_raw().get("user_content_paths") or {}).items():
            assert cred.is_credible(host), host
            assert prefixes, host
            for prefix in prefixes:
                assert prefix.startswith("/") and prefix.endswith("/"), (host, prefix)


class TestFactCheckerClassification:
    """What a page found on the open web *is* depends on who published it."""

    def test_verified_fact_checkers_are_recognised(self) -> None:
        cred = _credibility()
        for url in (
            "https://www.factcheck.org/2026/01/x/",
            "https://www.snopes.com/fact-check/x/",
            "https://www.altnews.in/x/",  # accreditation lapsed; still a fact-checker
            "https://www.boomlive.in/fact-check/x",
        ):
            assert cred.is_fact_checker(url), url

    def test_ordinary_publishers_and_unknowns_are_not(self) -> None:
        cred = _credibility()
        for url in (
            "https://www.thehindu.com/news/national/x",  # credible, but reporting
            "https://www.bbc.com/news/x",
            "https://frankreport.com/x",  # not credible at all
        ):
            assert not cred.is_fact_checker(url), url

    def test_the_resolver_labels_each_source_for_what_it_is(self) -> None:
        from datetime import UTC, datetime

        from app.domain.enums import EvidenceKind, Method, Tier
        from app.sources.base import SourceSnapshot
        from app.sources.websearch import WebSearchResolver

        resolver = WebSearchResolver(
            fetcher=object(),  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="",
            credibility=_credibility(),
        )

        def _snapshot(url: str) -> SourceSnapshot:
            return SourceSnapshot(
                id="s",
                url=url,
                final_url=url,
                content_hash="sha256:x",
                fetched_at=datetime.now(UTC),
                text="...",
            )

        # A published adjudication, reached by search instead of by the fact-check API.
        assert resolver.classify(_snapshot("https://www.factcheck.org/2026/01/x/")) == (
            Tier.C,
            EvidenceKind.FACT_CHECK,
            Method.CLAIM_REVIEW,
        )
        # Credible reporting that bears on the claim.
        assert resolver.classify(_snapshot("https://www.bbc.com/news/x")) == (
            Tier.D,
            EvidenceKind.CORROBORATION,
            Method.PASSAGE_ENTAILMENT,
        )
        # A fact-checker's own news report is reporting, not an adjudication.
        news = replace(
            _snapshot("https://www.altnews.in/indore-water-deaths/"),
            title="Indore deaths to sewage-contaminated water",
        )
        assert resolver.classify(news) == (
            Tier.D,
            EvidenceKind.CORROBORATION,
            Method.PASSAGE_ENTAILMENT,
        )


class TestWhichSourcesAreReadFirst:
    """Wires, the national press and the bodies that settle claims take the read slots.

    On a story PTI, The Hindu and the Times of India all carried, two of six slots went
    to Wikipedia and a regional paper while four candidates were never opened.
    """

    def test_wires_national_press_broadcasters_and_fact_checkers_are_prominent(self) -> None:
        cred = _credibility()
        for url in (
            "https://www.ptinews.com/story/1",
            "https://www.thehindu.com/news/national/x",
            "https://indianexpress.com/article/india/x",
            "https://www.bbc.com/news/x",
            "https://www.reuters.com/world/x",
            "https://www.boomlive.in/fact-check/x",
            "https://pib.gov.in/PressReleasePage.aspx?PRID=1",
            "https://www.who.int/news/x",
        ):
            assert cred.is_prominent(url), url

    def test_regional_and_reference_sources_are_read_after_them(self) -> None:
        cred = _credibility()
        for url in (
            "https://morungexpress.com/x",
            "https://en.wikipedia.org/wiki/X",
            "https://www.dawn.com/news/1",
            "https://www.iitm.ac.in/news/x",
        ):
            assert cred.is_credible(url), url
            assert not cred.is_prominent(url), url

    def test_the_resolver_reads_prominent_sources_first_in_search_order(self) -> None:
        import asyncio

        from app.sources.websearch import WebSearchResolver
        from tests.unit.factories import claim

        resolver = WebSearchResolver(
            fetcher=object(),  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="",
            credibility=_credibility(),
            max_results=3,
        )
        found = [
            "https://en.wikipedia.org/wiki/X",
            "https://morungexpress.com/x",
            "https://www.thehindu.com/news/national/x",
            "https://www.ptinews.com/story/1",
            "https://timesofindia.indiatimes.com/india/x",
        ]

        async def _queries(_: object) -> list[dict[str, object]]:
            return [{"url": url, "content": "x"} for url in found]

        resolver._queries = _queries  # type: ignore[method-assign]
        shortlist = asyncio.run(resolver.candidates(claim()))

        assert [c.url for c in shortlist] == [
            "https://www.thehindu.com/news/national/x",
            "https://www.ptinews.com/story/1",
            "https://timesofindia.indiatimes.com/india/x",
        ]

    def test_the_same_page_found_twice_is_read_once(self) -> None:
        """www.politifact.com and politifact.com were both read, one model call wasted."""
        import asyncio

        from app.sources.websearch import WebSearchResolver
        from tests.unit.factories import claim

        resolver = WebSearchResolver(
            fetcher=object(),  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="",
            credibility=_credibility(),
        )

        async def _queries(_: object) -> list[dict[str, object]]:
            return [
                {"url": "https://www.politifact.com/factchecks/2026/x/", "content": "x"},
                {"url": "https://politifact.com/factchecks/2026/x", "content": "x"},
            ]

        resolver._queries = _queries  # type: ignore[method-assign]
        shortlist = asyncio.run(resolver.candidates(claim()))

        assert [c.url for c in shortlist] == ["https://www.politifact.com/factchecks/2026/x/"]


class TestAListChangeReachesTheCache:
    """The verdict cache is keyed on the search resolver's version. Adding a host
    changes what a check may read, so it must change that version too, or answers
    cached before the host was trusted keep being served."""

    def test_adding_a_host_changes_the_fingerprint(self) -> None:
        before = SourceCredibility(frozenset({"thehindu.com"}))
        after = SourceCredibility(frozenset({"thehindu.com", "news18.com"}))

        assert before.fingerprint != after.fingerprint
        assert before.fingerprint == SourceCredibility(frozenset({"thehindu.com"})).fingerprint

    def test_the_search_resolver_version_carries_it(self) -> None:
        from app.sources.websearch import VERSION, WebSearchResolver

        def resolver(hosts: frozenset[str]) -> WebSearchResolver:
            return WebSearchResolver(
                fetcher=None,  # type: ignore[arg-type]
                reasoner=None,
                provider="tavily",
                endpoint="https://example.invalid/search",
                api_key="k",
                credibility=SourceCredibility(hosts),
            )

        old = resolver(frozenset({"thehindu.com"}))
        new = resolver(frozenset({"thehindu.com", "news18.com"}))

        assert old.version.startswith(VERSION)
        assert old.version != new.version
