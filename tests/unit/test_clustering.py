"""M26 — near-duplicate detection and independent-origin counting.

Twenty outlets carrying one wire copy is one source wearing twenty mastheads. Without
that rule corroboration is theatre, so these are the tests that stop a syndication
wave from reading as overwhelming confirmation.
"""

from __future__ import annotations

import pytest

from app.knowledge.clustering import CorroborationCount, OriginClusterer
from app.knowledge.ingest import IngestedItem
from app.knowledge.minhash import Signature, jaccard, shingles, sign

pytestmark = pytest.mark.unit


WIRE_ORIGINAL = (
    "New Delhi, Aug 16 (PTI) The government on Friday announced a relief scheme for "
    "farmers affected by unseasonal rainfall, with an outlay of five hundred crore "
    "rupees. Officials said applications would open next month and that district "
    "collectors had been asked to complete verification within thirty days."
)

# The same wire copy as a second outlet would run it: new headline, localised opening,
# tail trimmed. This is what real syndication looks like.
WIRE_REPRINT = (
    "Relief announced for rain-hit farmers. New Delhi, Aug 16 The government on "
    "Friday announced a relief scheme for farmers affected by unseasonal rainfall, "
    "with an outlay of five hundred crore rupees. Officials said applications would "
    "open next month and that district collectors had been asked to complete "
    "verification within thirty days."
)

# Independent reporting on the same event: same facts, different words.
INDEPENDENT_REPORT = (
    "Farmers hit by this month's unexpected downpours will be able to claim "
    "compensation under a package cleared on Friday. The agriculture ministry put "
    "the total cost at Rs 500 crore and said the claims window opens in September, "
    "with local officials given a month to verify each case."
)

UNRELATED = (
    "The city's transport authority said metro services on the blue line would run "
    "on a reduced schedule this weekend while signalling equipment is replaced at "
    "two stations."
)

# A full-length wire story, the way one actually arrives: distinct paragraphs, each
# adding new vocabulary. Length alone would not do — shingles are a *set*, so copy
# repeated four times produces the same shingles as copy printed once, and a fixture
# built that way would show no truncation effect at all.
LONG_WIRE_ARTICLE = (
    "New Delhi, Aug 16 (PTI) The government on Friday announced a relief scheme for "
    "farmers affected by unseasonal rainfall, with an outlay of five hundred crore "
    "rupees. "
    "Officials said applications would open next month and that district collectors "
    "had been asked to complete verification within thirty days. "
    "The agriculture minister told reporters the package covers eleven districts "
    "where crop damage exceeded thirty three per cent of the sown area. "
    "Under the scheme, cultivators holding up to two hectares receive a higher per "
    "hectare rate, and tenant farmers registered with the state portal are eligible "
    "for the first time. "
    "State officials estimate that about four lakh households will qualify, of whom "
    "roughly a third are sharecroppers without formal title. "
    "A senior official in the department said disbursal would be made directly to "
    "bank accounts seeded with Aadhaar, and that a grievance window would stay open "
    "for sixty days after each district publishes its provisional list. "
    "Opposition leaders in the state assembly called the outlay inadequate, pointing "
    "to earlier estimates of the damage that ran to nearly twice the announced sum. "
    "The minister said the figure would be revised once ground surveys conclude, and "
    "that an interim payment would not preclude a further tranche."
)


class TestShingles:
    def test_word_windows_overlap(self) -> None:
        assert shingles("one two three four five six", size=5) == {
            "one two three four five",
            "two three four five six",
        }

    def test_punctuation_and_case_are_normalised(self) -> None:
        assert shingles("The Government, Announced!", size=2) == shingles(
            "the government announced", size=2
        )

    def test_devanagari_survives_normalisation(self) -> None:
        assert shingles("सरकार ने योजना की घोषणा", size=2)

    def test_short_text_becomes_one_shingle(self) -> None:
        """Rather than an empty set, which would match everything."""
        assert shingles("two words", size=5) == {"two words"}

    def test_empty_text_produces_nothing(self) -> None:
        assert shingles("") == set()


class TestSignature:
    def test_a_signature_round_trips_through_bytes(self) -> None:
        """It is stored in a bytea column and compared days later."""
        original = sign(WIRE_ORIGINAL)

        restored = Signature.from_bytes(original.to_bytes())

        assert restored == original

    def test_the_serialised_width_is_fixed(self) -> None:
        assert len(sign(WIRE_ORIGINAL).to_bytes()) == 128 * 4

    def test_signing_is_deterministic_across_calls(self) -> None:
        """Stored today, compared next week, in a different process."""
        assert sign(WIRE_ORIGINAL) == sign(WIRE_ORIGINAL)

    def test_identical_text_is_fully_similar(self) -> None:
        assert sign(WIRE_ORIGINAL).similarity(sign(WIRE_ORIGINAL)) == 1.0

    def test_the_estimate_tracks_exact_jaccard(self) -> None:
        estimated = sign(WIRE_ORIGINAL).similarity(sign(WIRE_REPRINT))
        exact = jaccard(WIRE_ORIGINAL, WIRE_REPRINT)

        assert abs(estimated - exact) < 0.15

    def test_mismatched_lengths_are_an_error(self) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            sign("text", permutations=8).similarity(sign("text", permutations=16))


class TestSeparation:
    """The populations this threshold has to sit between."""

    def test_a_wire_reprint_is_close_to_its_original(self) -> None:
        assert sign(WIRE_ORIGINAL).similarity(sign(WIRE_REPRINT)) > 0.5

    def test_independent_reporting_is_not(self) -> None:
        """Same facts, different words. Two journalists do not pick the same windows."""
        assert sign(WIRE_ORIGINAL).similarity(sign(INDEPENDENT_REPORT)) < 0.3

    def test_unrelated_coverage_is_far_away(self) -> None:
        assert sign(WIRE_ORIGINAL).similarity(sign(UNRELATED)) < 0.15


class TestOriginClustering:
    def test_a_reprint_joins_the_original_cluster(self) -> None:
        clusterer = OriginClusterer()

        first = clusterer.assign(document_id="a", text=WIRE_ORIGINAL, publisher="PTI wire")
        second = clusterer.assign(document_id="b", text=WIRE_REPRINT, publisher="Outlet B")

        assert first.created_new
        assert not second.created_new
        assert first.cluster_id == second.cluster_id

    def test_independent_reporting_forms_its_own_origin(self) -> None:
        clusterer = OriginClusterer()

        first = clusterer.assign(document_id="a", text=WIRE_ORIGINAL, publisher="Outlet A")
        second = clusterer.assign(document_id="b", text=INDEPENDENT_REPORT, publisher="Outlet B")

        assert first.cluster_id != second.cluster_id

    def test_twenty_reprints_count_as_one_origin(self) -> None:
        """The rule the whole module exists for."""
        clusterer = OriginClusterer()

        ids = []
        for index in range(20):
            document_id = f"doc_{index}"
            ids.append(document_id)
            clusterer.assign(
                document_id=document_id, text=WIRE_REPRINT, publisher=f"Outlet {index}"
            )

        assert clusterer.distinct_origins(ids) == 1

    def test_three_independent_reports_count_as_three(self) -> None:
        clusterer = OriginClusterer()
        texts = [WIRE_ORIGINAL, INDEPENDENT_REPORT, UNRELATED]

        ids = []
        for index, text in enumerate(texts):
            document_id = f"doc_{index}"
            ids.append(document_id)
            clusterer.assign(document_id=document_id, text=text, publisher=f"Outlet {index}")

        assert clusterer.distinct_origins(ids) == 3

    def test_a_multi_outlet_cluster_is_identifiable(self) -> None:
        """The M26 gate looks for exactly this in the live corpus."""
        clusterer = OriginClusterer()

        clusterer.assign(document_id="a", text=WIRE_ORIGINAL, publisher="Outlet A")
        clusterer.assign(document_id="b", text=WIRE_REPRINT, publisher="Outlet B")

        multi = clusterer.multi_outlet_clusters()

        assert len(multi) == 1
        assert multi[0].publishers == {"Outlet A", "Outlet B"}

    def test_one_publisher_repeating_itself_is_not_multi_outlet(self) -> None:
        clusterer = OriginClusterer()

        clusterer.assign(document_id="a", text=WIRE_ORIGINAL, publisher="Outlet A")
        clusterer.assign(document_id="b", text=WIRE_REPRINT, publisher="Outlet A")

        assert clusterer.multi_outlet_clusters() == ()

    def test_the_earliest_instance_becomes_canonical(self) -> None:
        """In a syndication wave the first outlet to carry it is nearest an origin."""
        from datetime import UTC, datetime

        clusterer = OriginClusterer()
        later = datetime(2026, 8, 16, 12, tzinfo=UTC)
        earlier = datetime(2026, 8, 16, 9, tzinfo=UTC)

        clusterer.assign(
            document_id="a", text=WIRE_ORIGINAL, publisher="Late Outlet", published_at=later
        )
        clusterer.assign(
            document_id="b", text=WIRE_REPRINT, publisher="Early Outlet", published_at=earlier
        )

        assert clusterer.clusters[0].canonical_publisher == "Early Outlet"

    def test_unclustered_documents_are_their_own_origins(self) -> None:
        """Never silently reported as zero."""
        clusterer = OriginClusterer()

        assert clusterer.distinct_origins(["never-seen-a", "never-seen-b"]) == 2

    def test_no_documents_is_zero_origins(self) -> None:
        assert OriginClusterer().distinct_origins([]) == 0


class TestCorroborationCount:
    def test_both_numbers_are_reported(self) -> None:
        """Showing only one of them is the mistake this rule exists to prevent."""
        count = CorroborationCount(documents=19, origins=3)

        assert str(count) == "19 articles, 3 independent origins"

    def test_syndication_is_visible(self) -> None:
        assert CorroborationCount(documents=19, origins=3).is_syndicated
        assert not CorroborationCount(documents=3, origins=3).is_syndicated


class TestClusteringTextIsTheArticleNotTheExcerpt:
    """Why `IngestedItem.clustering_text` prefers the body.

    The M26 gate failed for a whole build cycle against a corpus of national outlets,
    and the second time it failed the cause was this: every CMS truncates its RSS
    excerpt at a different length, so the Jaccard between two feeds' excerpts of one
    wire story is bounded by where the two happened to cut rather than by how alike
    the articles are. Measured live on three PTI stories — 0.301, 0.265 and 0.205 on
    excerpts against 0.787, 0.792 and 0.770 on bodies.

    These tests fail if anyone reverts clustering to the excerpt, without needing a
    network or a database to notice.
    """

    @staticmethod
    def _item(publisher: str, *, title: str, body: str, excerpt_chars: int) -> IngestedItem:
        return IngestedItem(
            canonical_url=f"https://{publisher.lower().replace(' ', '')}.example/story",
            content_hash=f"sha256:{publisher}",
            title=title,
            # Each outlet's feed cuts the same copy at its own length.
            excerpt=body[:excerpt_chars],
            publisher=publisher,
            published_at=None,
            language="en",
            body=body,
        )

    def test_excerpt_truncation_hides_syndication(self) -> None:
        """Two truncations of one story look less alike than the story is."""
        long_wire = LONG_WIRE_ARTICLE

        short_cut = long_wire[:200]
        long_cut = long_wire[:900]

        assert jaccard(short_cut, long_cut) < 0.5, (
            "expected differing truncations to fall below the clustering threshold; "
            "if this passes, the fixture no longer models the failure"
        )
        assert jaccard(long_wire, long_wire) == 1.0

    def test_the_same_article_clusters_when_bodies_are_used(self) -> None:
        long_wire = LONG_WIRE_ARTICLE

        first = self._item(
            "Wire Carrier A", title="Relief for farmers", body=long_wire, excerpt_chars=200
        )
        second = self._item(
            "Wire Carrier B", title="Rain-hit farmers get relief", body=long_wire, excerpt_chars=900
        )

        clusterer = OriginClusterer()
        clusterer.assign(document_id="a", text=first.clustering_text, publisher=first.publisher)
        clusterer.assign(document_id="b", text=second.clustering_text, publisher=second.publisher)

        assert len(clusterer.clusters) == 1
        assert clusterer.clusters[0].is_multi_outlet

    def test_the_same_article_does_not_cluster_on_excerpts(self) -> None:
        """The old behaviour, kept as a test so the regression is visible."""
        long_wire = LONG_WIRE_ARTICLE

        first = self._item(
            "Wire Carrier A", title="Relief for farmers", body=long_wire, excerpt_chars=200
        )
        second = self._item(
            "Wire Carrier B", title="Rain-hit farmers get relief", body=long_wire, excerpt_chars=900
        )

        clusterer = OriginClusterer()
        clusterer.assign(
            document_id="a", text=f"{first.title}\n{first.excerpt}", publisher=first.publisher
        )
        clusterer.assign(
            document_id="b", text=f"{second.title}\n{second.excerpt}", publisher=second.publisher
        )

        assert len(clusterer.clusters) == 2
        assert not any(cluster.is_multi_outlet for cluster in clusterer.clusters)

    def test_an_unhydrated_item_falls_back_to_its_excerpt(self) -> None:
        """A page that would not load still gets ingested and still clusters."""
        item = IngestedItem(
            canonical_url="https://example.org/story",
            content_hash="sha256:x",
            title="Headline",
            excerpt="the feed snippet",
            publisher="Some Outlet",
            published_at=None,
            language="en",
        )

        assert not item.is_hydrated
        assert item.clustering_text == "Headline\nthe feed snippet"

    def test_independent_reporting_still_does_not_cluster_on_bodies(self) -> None:
        """Body clustering must not become a machine for merging distinct reporting."""
        clusterer = OriginClusterer()
        clusterer.assign(document_id="a", text=WIRE_ORIGINAL, publisher="Wire Carrier")
        clusterer.assign(document_id="b", text=INDEPENDENT_REPORT, publisher="Own Reporting")

        assert len(clusterer.clusters) == 2
