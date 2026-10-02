"""A claim that reports a denial, in any language the product reads (2026-10-02).

"PIB has debunked claims that ..." is agreed with by a page refuting what PIB
debunked, so for such a claim a "contradiction" is never kept. The guard knew only
English: a Hindi claim that nobody translated, "PIB ने खंडन किया", kept the refutation
as a contradiction of itself and a true report of a debunk could read False. Held
here: the guard reads every supported language and Hinglish, and - like the English
one - not a fabricated quote that merely contains the word "lie", which must stay
refutable by the denial that it was ever said.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.enums import Relation
from app.sources.reasoning import (
    Passage,
    PassageReasoner,
    _ReasoningResponse,
    reports_a_denial,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "claim_text",
    [
        # English, as before.
        "PIB has debunked claims that the RBI will cancel Rs 500 notes.",
        "The ministry denied reports that the scheme was scrapped.",
        "The police called the video fake.",
        # Hindi, in its own script, with and without the nukta.
        "PIB ने इस दावे का खंडन किया है।",
        "PIB फ़ैक्ट चेक ने इस दावे को फ़र्ज़ी बताया।",
        "पीआईबी ने इस खबर को फर्जी करार दिया।",
        "मंत्रालय ने इन खबरों को बेबुनियाद बताया।",
        "सरकार ने रिपोर्टों को नकारा।",
        "कंपनी ने इस दावे से इनकार किया।",
        # Marathi
        "सरकारने हा दावा फेटाळला आहे.",
        "हा संदेश खोटा असल्याचे पोलिसांनी सांगितले.",
        # Hinglish
        "PIB ne is daave ka khandan kiya",
        "PIB ne ise fake bataya",
        "Sarkar ne is khabar se inkaar kiya",
        # Bengali
        "সরকার এই খবর অস্বীকার করেছে।",
        "পিআইবি এটিকে ভুয়া আখ্যা দিয়েছে।",
        # Tamil
        "தமிழக அரசு இந்த செய்தியை மறுத்துள்ளது.",
        "இது போலி என்று காவல்துறை தெரிவித்தது.",
        # Telugu
        "ఈ వార్తను ప్రభుత్వం ఖండించింది.",
        "ఇది నకిలీ అని పోలీసులు తెలిపారు.",
        "ఇది నకిలీదని పీఐబీ స్పష్టం చేసింది.",
        # Kannada
        "ಸರ್ಕಾರ ಈ ವರದಿಯನ್ನು ನಿರಾಕರಿಸಿದೆ.",
        "ಈ ಸುದ್ದಿ ಸುಳ್ಳೆಂದು ಪೊಲೀಸರು ಹೇಳಿದ್ದಾರೆ.",
        # Malayalam
        "സർക്കാർ ഈ റിപ്പോർട്ട് നിഷേധിച്ചു.",
        "ഈ വാർത്ത വ്യാജമാണെന്ന് പോലീസ് അറിയിച്ചു.",
        # Gujarati
        "સરકારે આ દાવાને ખોટો ગણાવ્યો.",
        "કંપનીએ આ અહેવાલનો ઇનકાર કર્યો.",
        # Punjabi
        "ਪੁਲਿਸ ਨੇ ਇਸ ਨੂੰ ਫ਼ਰਜ਼ੀ ਦੱਸਿਆ।",
        "ਸਰਕਾਰ ਨੇ ਇਸ ਖ਼ਬਰ ਦਾ ਖੰਡਨ ਕੀਤਾ।",
        # Odia
        "ସରକାର ଏହି ଖବରକୁ ଖଣ୍ଡନ କରିଛନ୍ତି।",
        # Urdu, and typed with the Arabic letters
        "حکومت نے اس خبر کی تردید کی۔",
        "پولیس نے اسے جعلی قرار دیا۔",
        "پولیس نے اسے جعلي قرار ديا۔",
    ],
)
def test_a_report_of_a_denial_is_recognised(claim_text: str) -> None:
    assert reports_a_denial(claim_text)


@pytest.mark.parametrize(
    "claim_text",
    [
        "Rahul Gandhi said that Modi is a liar.",
        # A quote that contains a falsehood word, but reports no denial.
        "राहुल गांधी ने कहा कि मोदी झूठ बोलते हैं।",
        "गौरव भाटिया ने कहा कि स्वतंत्र भारद्वाज का भाजपा सरकार से कोई लेना-देना नहीं है।",
        "मोदी ने कहा कि नकारात्मक राजनीति देश को पीछे ले जाती है।",
        "Modi ne kaha ki Gandhi khandan ne desh loota",
        "எனக்கு பொய் சொல்ல தெரியாது என்று அவர் கூறினார்.",
        "మోదీ అబద్ధం చెప్పారు అని రాహుల్ అన్నారు.",
        "ఆ కంపెనీ లాభాలు తగ్గాయని మంత్రి చెప్పారు.",
        "वह कंपनी घाटे में है, मंत्री ने कहा।",
        "મંત્રીએ કહ્યું કે કંપની ખોટમાં છે.",
    ],
)
def test_a_quote_that_reports_no_denial_is_not_taken_for_one(claim_text: str) -> None:
    assert not reports_a_denial(claim_text)


PASSAGE = "The quote attributed to him is fabricated, and he made no such statement."


def _judge(claim_text: str, *, claim_type: str = "QUOTE") -> Any:
    response = _ReasoningResponse.model_validate(
        {
            "judgements": [
                {
                    "passage_index": 0,
                    "relation": "CONTRADICTS",
                    "contradiction_basis": "DENIES",
                    "quote": PASSAGE,
                    "reason": "r",
                    "relevance": 0.9,
                }
            ]
        }
    )
    reasoner = PassageReasoner.__new__(PassageReasoner)
    reasoner._model_id = "test"
    return reasoner._verify(
        response,
        [Passage(index=0, text=PASSAGE, char_start=0, char_end=len(PASSAGE))],
        claim_type=claim_type,
        claim_text=claim_text,
    )


class TestTheReaderKeepsOnlyRealContradictions:
    def test_a_hindi_report_of_a_debunk_is_not_contradicted_by_the_debunk(self) -> None:
        [judged] = _judge("PIB ने इस दावे को फ़र्ज़ी बताया कि सभी को 5000 रुपये मिलेंगे।").judgements

        assert judged.relation is Relation.CONTEXTUALIZES

    def test_nor_a_telugu_one(self) -> None:
        [judged] = _judge("ఈ వార్తను ప్రభుత్వం ఖండించింది.", claim_type="ATTRIBUTION").judgements

        assert judged.relation is Relation.CONTEXTUALIZES

    def test_a_fabricated_hindi_quote_can_still_be_called_false(self) -> None:
        [judged] = _judge("राहुल गांधी ने कहा कि मोदी झूठ बोलते हैं।").judgements

        assert judged.relation is Relation.CONTRADICTS

    def test_a_claim_that_is_not_reported_speech_is_never_guarded(self) -> None:
        [judged] = _judge("PIB ने इस दावे का खंडन किया है।", claim_type="EVENT").judgements

        assert judged.relation is Relation.CONTRADICTS
