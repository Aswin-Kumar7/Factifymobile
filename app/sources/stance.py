"""Which pages speak to a claim - on our own server.

The hosted model reads every page a search returns: one metered call per page, five
to eight per claim, a share of them on pages about something else. A local reranker
(`Alibaba-NLP/gte-multilingual-reranker-base`, Apache-2.0, Hindi included, ~70 ms a
pair on a CPU) now scores how much each passage is about the claim, and a page none
of whose passages clears the floor is not sent to the hosted reader
(`local_reading.py` has the measured boundary).

Two NLI models were brought in to answer "does this passage state the claim?" as
well - `DeBERTa-v3-large-mnli-fever-anli-ling-wanli` for English and
`mDeBERTa-v3-base-xnli` for Hindi - and measured on 2,390 pairs from past checks
before being given the job. They did not earn it: the English model, 97% sure of
support, disagreed with the hosted reader on 12 of 90 sentences the hosted reader
read as contradictions, and caught 8 of its 302 contradictions; the multilingual one
read "The ministry said no such scheme exists and the message is fake" as unrelated
to the scheme, at 0.94. They are kept for measurement (`entailment`, used by
scripts/eval_models.py) and are not loaded by the service.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass

import numpy as np

from app.media.detectors.common import model_path, onnx_session

logger = logging.getLogger("factify.sources.stance")

RERANKER = ("gte-reranker", "onnx/model_int8.onnx")
ENGLISH_NLI = ("deberta-v3-large-nli", "onnx/model_quantized.onnx")
MULTILINGUAL_NLI = ("mdeberta-v3-base-xnli", "onnx/model_quantized.onnx")

# Tokens per pair. Passages are cut to 1,200 characters before this.
MAX_TOKENS = 384

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def is_english(text: str) -> bool:
    """No Devanagari at all: the English model reads it."""
    return _DEVANAGARI.search(text) is None


@dataclass(frozen=True, slots=True)
class Entailment:
    entails: float
    neutral: float
    contradicts: float


class _Encoder:
    """One ONNX cross-encoder and its tokenizer."""

    def __init__(self, folder: str, file: str, *, directory: str, threads: int) -> None:
        from tokenizers import Tokenizer  # type: ignore[import-untyped]

        weights = model_path(directory, folder, file)
        vocabulary = model_path(directory, folder, "tokenizer.json")
        if weights is None or vocabulary is None:
            raise FileNotFoundError(folder)
        self.session = onnx_session(weights, threads=threads)
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(str(vocabulary))
        # Longest first: the reranker is given (claim, passage) and the NLI models
        # (passage, claim); "only_first" cut the claim, and a long passage then
        # failed outright - common in the Indian scripts, which take more tokens.
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS, strategy="longest_first")
        self.tokenizer.enable_padding()
        self.name = folder

    def logits(self, pairs: list[tuple[str, str]]) -> np.ndarray:
        encoded = self.tokenizer.encode_batch(pairs)
        feeds = {
            "input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encoded], dtype=np.int64),
        }
        if "token_type_ids" in self.inputs:
            feeds["token_type_ids"] = np.array([e.type_ids for e in encoded], dtype=np.int64)
        return np.asarray(self.session.run(None, feeds)[0], dtype=np.float32)


def _labels(directory: str, folder: str) -> dict[str, int]:
    """Where entailment, neutral and contradiction sit in the model's output."""
    import json

    config = model_path(directory, folder, "config.json")
    if config is None:
        return {"entailment": 0, "neutral": 1, "contradiction": 2}
    id2label = json.loads(config.read_text(encoding="utf-8")).get("id2label", {})
    return {str(label).lower(): int(index) for index, label in id2label.items()}


class LocalStance:
    """The relevance and support models, loaded once and shared."""

    def __init__(self, *, directory: str, threads: int = 4) -> None:
        self._directory = directory
        self._threads = threads
        self._lock = threading.Lock()
        self._reranker: _Encoder | None = None
        self._english: _Encoder | None = None
        self._multilingual: _Encoder | None = None
        self._label_index: dict[str, dict[str, int]] = {}
        self._loaded = False

    @property
    def available(self) -> bool:
        return model_path(self._directory, *RERANKER) is not None

    def load(self) -> None:
        """The reranker only: it is the one model the service uses."""
        with self._lock:
            if self._loaded:
                return
            try:
                self._reranker = _Encoder(
                    *RERANKER, directory=self._directory, threads=self._threads
                )
            except Exception:
                logger.exception("the relevance model could not be loaded")
            self._loaded = True

    def _load_nli(self) -> None:
        """The two NLI models, for measurement only (scripts/eval_models.py)."""
        with self._lock:
            for attribute, (folder, file) in (
                ("_english", ENGLISH_NLI),
                ("_multilingual", MULTILINGUAL_NLI),
            ):
                if getattr(self, attribute) is not None:
                    continue
                try:
                    setattr(
                        self,
                        attribute,
                        _Encoder(folder, file, directory=self._directory, threads=self._threads),
                    )
                    self._label_index[folder] = _labels(self._directory, folder)
                except Exception:
                    logger.exception("NLI model %s could not be loaded", folder)

    @property
    def can_gate(self) -> bool:
        self.load()
        return self._reranker is not None

    def relevance(self, claim: str, passages: list[str]) -> list[float] | None:
        """How much each passage is about the claim, 0-1; None without the model."""
        self.load()
        if self._reranker is None or not passages:
            return None
        logits = self._reranker.logits([(claim, passage) for passage in passages])
        return [float(1.0 / (1.0 + np.exp(-row.reshape(-1)[0]))) for row in logits]

    def entailment(self, premises: list[str], hypothesis: str) -> list[Entailment] | None:
        """Whether each premise states the hypothesis; English model when both are
        English, the multilingual one otherwise; None without either. Measurement
        only: see the module docstring for why the service does not use it."""
        self._load_nli()
        english = is_english(hypothesis) and all(is_english(p) for p in premises)
        encoder = self._english if english else self._multilingual
        if encoder is None or not premises:
            return None
        index = self._label_index[encoder.name]
        logits = encoder.logits([(premise, hypothesis) for premise in premises])
        found = []
        for row in logits:
            probabilities = np.exp(row - row.max())
            probabilities = probabilities / probabilities.sum()
            found.append(
                Entailment(
                    entails=float(probabilities[index.get("entailment", 0)]),
                    neutral=float(probabilities[index.get("neutral", 1)]),
                    contradicts=float(probabilities[index.get("contradiction", 2)]),
                )
            )
        return found
