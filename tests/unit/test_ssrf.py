"""M09 — the SSRF fixture suite.

The service fetches URLs an attacker chooses, from inside our own network. This is
the gate: every payload below is rejected, including the redirect that looks public
on the first hop and points somewhere internal on the second.
"""

from __future__ import annotations

import pytest

from app.security.fetcher import _www_variant
from app.security.ssrf import (
    BlockedDestination,
    is_blocked_address,
    resolve_and_validate,
    validate_url,
)

pytestmark = pytest.mark.unit


class TestSchemes:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://127.0.0.1:6379/_INFO",
            "ftp://internal.example/secrets",
            "dict://127.0.0.1:11211/stat",
            "jar:http://example.org!/",
            "data:text/plain;base64,aGk=",
            "//example.org/protocol-relative",
        ],
    )
    def test_non_http_schemes_are_refused(self, url: str) -> None:
        with pytest.raises(BlockedDestination):
            validate_url(url)

    def test_http_and_https_are_permitted(self) -> None:
        assert validate_url("http://example.org/a") == ("example.org", 80)
        assert validate_url("https://example.org/a") == ("example.org", 443)

    def test_credentials_in_url_are_refused(self) -> None:
        """Both a smuggling trick and something we must never transmit."""
        with pytest.raises(BlockedDestination, match="credentials"):
            validate_url("https://user:password@example.org/a")


class TestBlockedAddressRanges:
    @pytest.mark.parametrize(
        ("address", "why"),
        [
            ("127.0.0.1", "loopback"),
            ("127.1.1.1", "loopback, non-obvious form"),
            ("0.0.0.0", "unspecified"),
            ("10.0.0.1", "RFC1918"),
            ("172.16.0.1", "RFC1918"),
            ("192.168.1.1", "RFC1918"),
            ("169.254.169.254", "cloud metadata endpoint"),
            ("169.254.0.1", "link-local"),
            ("100.64.0.1", "carrier-grade NAT"),
            ("224.0.0.1", "multicast"),
            ("255.255.255.255", "broadcast"),
            ("::1", "IPv6 loopback"),
            ("fe80::1", "IPv6 link-local"),
            ("fc00::1", "IPv6 unique local"),
            ("::ffff:127.0.0.1", "IPv4-mapped IPv6 loopback"),
            ("::", "IPv6 unspecified"),
        ],
    )
    def test_internal_addresses_are_blocked(self, address: str, why: str) -> None:
        assert is_blocked_address(address) is not None, f"{address} ({why}) was allowed"

    @pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700::1111"])
    def test_public_addresses_are_allowed(self, address: str) -> None:
        assert is_blocked_address(address) is None

    def test_the_metadata_endpoint_is_named_in_the_reason(self) -> None:
        """The single most valuable SSRF target against a hosted service."""
        reason = is_blocked_address("169.254.169.254")

        assert reason is not None
        assert "169.254.169.254" in reason

    def test_nat64_is_judged_by_its_embedded_ipv4(self) -> None:
        """A DNS64 network wraps a real IPv4 in 64:ff9b::/96.

        The address must be judged by the IPv4 it carries, not blocked wholesale as a
        reserved IPv6 range (which stopped every outbound fetch on a NAT64 network),
        and not waved through wholesale (which would smuggle a private IPv4 past the
        guard).
        """
        # 64:ff9b::6439:fbcd embeds the public 100.57.251.205 — allowed.
        assert is_blocked_address("64:ff9b::6439:fbcd") is None
        # 64:ff9b::a00:1 embeds 10.0.0.1, and 64:ff9b::7f00:1 embeds 127.0.0.1 — the
        # guard must still block both.
        assert is_blocked_address("64:ff9b::a00:1") is not None
        assert is_blocked_address("64:ff9b::7f00:1") is not None


class TestResolution:
    def _resolver(self, *addresses: str) -> object:
        def resolve(host: str, port: int) -> list[str]:
            return list(addresses)

        return resolve

    def test_hostname_resolving_to_a_private_address_is_blocked(self) -> None:
        """The classic bypass: a public name pointed at an internal address."""
        with pytest.raises(BlockedDestination, match="is private"):
            resolve_and_validate("https://evil.example/a", resolver=self._resolver("10.0.0.5"))

    def test_every_resolved_address_is_checked_not_just_the_first(self) -> None:
        """A host answering with one public and one private address is refused.

        Which address a connection actually uses is not something we control, so a
        mixed answer is treated as the private one.
        """
        with pytest.raises(BlockedDestination):
            resolve_and_validate(
                "https://mixed.example/a",
                resolver=self._resolver("93.184.216.34", "192.168.0.9"),
            )

    def test_bare_private_ip_in_the_url_is_blocked(self) -> None:
        with pytest.raises(BlockedDestination):
            resolve_and_validate("http://169.254.169.254/latest/meta-data/")

    def test_decimal_encoded_loopback_is_blocked(self) -> None:
        """2130706433 is 127.0.0.1 written as an integer."""
        with pytest.raises(BlockedDestination):
            resolve_and_validate("http://2130706433/", resolver=self._resolver("127.0.0.1"))

    def test_host_that_does_not_resolve_is_blocked(self) -> None:
        def failing(host: str, port: int) -> list[str]:
            raise OSError("NXDOMAIN")

        with pytest.raises(BlockedDestination, match="does not resolve"):
            resolve_and_validate("https://nowhere.invalid/a", resolver=failing)

    def test_host_resolving_to_nothing_is_blocked(self) -> None:
        with pytest.raises(BlockedDestination, match="no addresses"):
            resolve_and_validate("https://empty.example/a", resolver=self._resolver())

    def test_public_host_is_allowed(self) -> None:
        destination = resolve_and_validate(
            "https://example.org/story", resolver=self._resolver("93.184.216.34")
        )

        assert destination.host == "example.org"
        assert destination.port == 443
        assert destination.addresses == ("93.184.216.34",)


class TestBlockedDestinationCarriesItsReason:
    def test_reason_is_available_for_recording(self) -> None:
        """A blocked fetch is an outcome to record, not an error to swallow."""
        try:
            validate_url("file:///etc/passwd")
        except BlockedDestination as blocked:
            assert blocked.reason
            assert blocked.url == "file:///etc/passwd"
        else:
            pytest.fail("expected the fetch to be blocked")


class TestAnApexThatOnlyPublishesWww:
    """`isro.gov.in` has no address; `www.isro.gov.in` answers over IPv6.

    We were reporting India's space agency as unreachable while checking claims about
    Indian space missions. The retry rewrites the URL rather than resolving one host
    and connecting to another, so the `www` form goes through every check from the top
    and the citation records the address that actually served.
    """

    def test_a_bare_apex_offers_its_www_form(self) -> None:
        assert _www_variant("https://isro.gov.in/a?b=1") == "https://www.isro.gov.in/a?b=1"

    def test_a_multi_label_suffix_is_still_an_apex(self) -> None:
        """Counting dots does not work: `gov.in` makes the apex two dots deep."""
        assert _www_variant("https://pib.gov.in/") == "https://www.pib.gov.in/"

    def test_a_host_that_already_has_a_subdomain_is_left_alone(self) -> None:
        assert _www_variant("https://en.wikipedia.org/wiki/X") is None

    def test_www_is_not_retried_into_www_www(self) -> None:
        assert _www_variant("https://www.bbc.com/news") is None

    def test_a_port_survives_the_rewrite(self) -> None:
        assert _www_variant("https://example.com:8443/x") == "https://www.example.com:8443/x"

    def test_nothing_is_offered_for_a_hostless_url(self) -> None:
        assert _www_variant("https:///path") is None
