"""Publisher credibility gates which open-web sources are worth citing."""

from __future__ import annotations

import json
import re
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
