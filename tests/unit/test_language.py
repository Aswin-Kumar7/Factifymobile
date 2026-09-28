"""M19 — deterministic language routing, no model call."""

from __future__ import annotations

import pytest

from app.extraction.language import Language, Script, detect, detect_script, hinglish_ratio

pytestmark = pytest.mark.unit


class TestScriptDetection:
    def test_devanagari_is_hindi(self) -> None:
        result = detect("सरकार ने नई योजना की घोषणा की है")

        assert result.language is Language.HINDI
        assert result.script is Script.DEVANAGARI
        assert result.confident

    def test_latin_prose_is_english(self) -> None:
        result = detect("The government announced a new scheme for farmers on Tuesday.")

        assert result.language is Language.ENGLISH
        assert result.confident

    def test_each_indian_script_names_its_language(self) -> None:
        """Ten more languages since 2026-09-28: the script names the language."""
        result = detect("সরকার নতুন প্রকল্প ঘোষণা করেছে")

        assert result.script is Script.BENGALI
        assert result.language is Language.BENGALI
        assert result.confident
        assert detect("அரசு புதிய திட்டத்தை அறிவித்துள்ளது").language is Language.TAMIL
        assert detect("حکومت نے نئی اسکیم کا اعلان کیا ہے۔").language is Language.URDU
        assert detect("ਸਰਕਾਰ ਨੇ ਨਵੀਂ ਯੋਜਨਾ ਦਾ ਐਲਾਨ ਕੀਤਾ").language is Language.PUNJABI

    def test_marathi_and_hindi_are_told_apart_by_grammar_words(self) -> None:
        assert detect("ही बातमी खरी नाही आणि फसवी आहे").language is Language.MARATHI
        assert detect("यह खबर सच नहीं है और फर्जी है").language is Language.HINDI

    def test_mixed_script_with_devanagari_routes_to_hindi(self) -> None:
        """Common in real forwards: Hindi commentary quoting an English headline."""
        result = detect("BREAKING NEWS: सरकार ने योजना की घोषणा की है aur yeh sach hai")

        assert result.language is Language.HINDI


class TestHinglish:
    """The default register of Indian WhatsApp, and its own language.

    Calling it English would hand an English-only prompt a sentence it cannot
    segment and route the reply to the wrong template.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "Yeh khabar bilkul sach hai, sab log forward karo",
            "Kya aap ko pata hai ki yeh scheme abhi bhi chalu hai",
            "Modi ji ne kaha hai ki sab ko paisa milega, share karein",
        ],
    )
    def test_romanised_hindi_is_detected(self, text: str) -> None:
        result = detect(text)

        assert result.language is Language.HINGLISH
        assert result.script is Script.LATIN
        assert result.confident

    def test_english_prose_is_not_mistaken_for_hinglish(self) -> None:
        text = "The committee said the report would be published in the coming weeks."

        assert detect(text).language is Language.ENGLISH
        assert hinglish_ratio(text) < 0.15

    def test_a_single_borrowed_word_is_not_enough(self) -> None:
        """Function-word ratio, not keyword spotting."""
        result = detect("The minister said the scheme was a success for every citizen here")

        assert result.language is Language.ENGLISH


class TestEdgeCases:
    def test_empty_text_is_confident_and_unknown(self) -> None:
        result = detect("")

        assert result.language is Language.UNKNOWN
        assert result.confident
        assert not result.needs_model_fallback

    def test_very_short_text_defers_to_a_model(self) -> None:
        """The one case a model call is worth spending on, and it is rare."""
        result = detect("ok")

        assert not result.confident
        assert result.needs_model_fallback

    def test_the_common_path_never_needs_a_model(self) -> None:
        for text in (
            "सरकार ने घोषणा की",
            "The government announced a new policy today for all citizens",
            "Yeh sab jhooth hai bhai, mat forward karo",
        ):
            assert not detect(text).needs_model_fallback

    def test_numbers_and_punctuation_alone_do_not_assert_a_language(self) -> None:
        assert detect("12345 !!! ???").language is Language.UNKNOWN


class TestScriptDistribution:
    def test_distribution_is_reported(self) -> None:
        script, counts = detect_script("Hello नमस्ते")

        assert script is Script.MIXED
        assert counts[Script.LATIN] == 5
        # Base characters only: combining vowel marks are category Mn and are not
        # alphabetic, so नमस्ते counts four rather than six.
        assert counts[Script.DEVANAGARI] == 4
