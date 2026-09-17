"""Publisher credibility gates which open-web sources are worth citing."""

from __future__ import annotations

from app.sources.credibility import SourceCredibility


def _credibility() -> SourceCredibility:
    # The real curated list, so the test breaks if a trusted domain is dropped from it.
    return SourceCredibility.load()


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

    def test_an_empty_list_still_trusts_tld_patterns(self) -> None:
        # An unreadable credibility file must fail closed on named domains but still
        # trust governments and universities — stricter, never looser.
        empty = SourceCredibility(frozenset())
        assert empty.is_credible("https://www.who.int/x")
        assert not empty.is_credible("https://fullfact.org/x")
