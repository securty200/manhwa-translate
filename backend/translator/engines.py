"""Modular translation engines for manga text translation.

Supports 11 engines split into two tiers:

Offline models (transformers-based):
  - NLLB (Meta) — 200 languages, best for manga (ja/ko/zh→en)
  - M2M100 (Facebook) — 100 languages, many-to-many
  - MarianMT (HuggingFace OPUS) — lightweight per-language pairs
  - Argos Translate — offline neural machine translation

Cloud APIs (on-demand):
  - Google Translate — 100+ langs, free tier
  - DeepL — highest quality, generous free tier
  - LibreTranslate — self-hostable, FOSS
  - Gemini — Google's LLM with manga context
  - OpenAI — GPT-4o mini / GPT-4o with manga prompting
  - Claude — Anthropic's models with manga context
  - Ollama — local LLMs via HTTP API

Each engine implements the TranslationEngine protocol:
    async def translate(text, source_lang, target_lang, context) -> EngineTranslationResult
"""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)


# ── Core result type ─────────────────────────────────────────────────────

@dataclass
class EngineTranslationResult:
    """Normalized result from any translation engine."""

    translated_text: str
    confidence: float = 1.0
    engine_name: str = ""
    processing_time_ms: float = 0.0
    detected_source_language: str = ""  # Set by auto-detection engines
    fallback_used: bool = False
    metadata: dict = field(default_factory=dict)


# ── Manga translation prompt for LLM-based engines ───────────────────────

MANGA_SYSTEM_PROMPT = """You are a professional manga (Japanese comic) translator with deep expertise in Japanese-to-{target_lang} translation.

## Core Rules
1. **Natural flow** — Translate the meaning, not the words. The result should read as if originally written in {target_lang}.
2. **Preserve names** — Character names, place names, and unique terms remain in their original form (romanized). NEVER translate names.
3. **Preserve emotions** — Capture the emotional tone: anger, excitement, sadness, whisper, shouting, hesitation. Use appropriate punctuation and word choice.
4. **Speech patterns** — Maintain each character's unique way of speaking (formal, rude, childish, archaic, dialect).
5. **Cultural adaptation** — Adapt Japanese cultural references when needed, but keep honorifics (-san, -kun, -chan, -sama, -sensei) where they convey relationship dynamics.
6. **Sound effects (SFX)** — Onomatopoeia like ドキドキ (thump thump), ガーン (shock), ニヤリ (grin) should be translated to natural {target_lang} equivalents.
7. **Context awareness** — Use the provided manga context (genre, setting, character info) to guide translation choices.
8. **No extra commentary** — Output ONLY the translated text. No explanations, no notes, no quotation marks around the translation.

## Manga Context
{context}

## Text to translate:
{text}"""


# ── Language code normalization ──────────────────────────────────────────

LANGUAGE_CODE_MAP: dict[str, dict[str, str]] = {
    # Maps ISO codes → engine-specific codes
    "nllb": {
        "ja": "jpn_Jpan", "en": "eng_Latn", "zh": "zho_Hans",
        "ko": "kor_Hang", "fr": "fra_Latn", "es": "spa_Latn",
        "ru": "rus_Cyrl", "de": "deu_Latn", "it": "ita_Latn",
        "pt": "por_Latn", "th": "tha_Thai", "vi": "vie_Latn",
        "ar": "arb_Arab", "tr": "tur_Latn", "nl": "nld_Latn",
        "pl": "pol_Latn", "sv": "swe_Latn", "da": "dan_Latn",
        "fi": "fin_Latn", "cs": "ces_Latn", "hu": "hun_Latn",
        "ro": "ron_Latn", "el": "ell_Grek", "he": "heb_Hebr",
        "hi": "hin_Deva", "id": "ind_Latn", "ms": "zsm_Latn",
        "tl": "tgl_Latn", "mn": "mon_Cyrl", "ne": "npi_Deva",
        "uz": "uzn_Latn", "kk": "kaz_Cyrl", "uk": "ukr_Cyrl",
    },
    "m2m100": {
        "ja": "ja", "en": "en", "zh": "zh", "ko": "ko",
        "fr": "fr", "es": "es", "ru": "ru", "de": "de",
        "it": "it", "pt": "pt", "th": "th", "vi": "vi",
        "ar": "ar", "tr": "tr", "nl": "nl", "pl": "pl",
    },
    "argos": {
        "ja": "ja", "en": "en", "zh": "zh", "ko": "ko",
        "fr": "fr", "es": "es", "ru": "ru", "de": "de",
        "it": "it", "pt": "pt", "ar": "ar", "vi": "vi",
        "th": "th", "tr": "tr",
    },
}


def normalize_language_code(engine: str, iso_code: str) -> str:
    """Convert an ISO language code to an engine-specific code.

    Falls back to the ISO code if no mapping exists.
    """
    engine_map = LANGUAGE_CODE_MAP.get(engine, {})
    return engine_map.get(iso_code, iso_code)


def _trim_to_sentence(response: str) -> str:
    """Trim a translation response to remove any extra text added by the model."""
    # Remove common prefixes
    for prefix in [
        "Translation:", "Translated text:", "Output:", "Result:",
        "Here is the translation:", "Translated:",
    ]:
        if response.startswith(prefix):
            response = response[len(prefix):].strip()
    return response.strip()


# ═══════════════════════════════════════════════════════════════════════════
# OFFLINE ENGINES
# ═══════════════════════════════════════════════════════════════════════════


class NLLBEngine:
    """Meta's No Language Left Behind — 200 languages, excellent for manga.

    Best model: facebook/nllb-200-distilled-600M (lightweight) or
    facebook/nllb-200-3.3B (high quality).

    Strengths: Japanese→English quality is top-tier among open models.
    Supports many languages relevant to manga translation.
    """

    def __init__(
        self,
        model_name: str = "facebook/nllb-200-distilled-600M",
        device: str = "cpu",
        max_length: int = 200,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self._tokenizer = None
        self._model = None
        self._initialized = False

    def initialize(self) -> None:
        """Load the NLLB model and tokenizer."""
        if self._initialized:
            return
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            logger.info("Loading NLLB model: %s (device: %s)", self.model_name, self.device)
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name).to(self.device)
            self._model.eval()
            self._initialized = True
            logger.info("NLLB model loaded successfully")
        except ImportError:
            logger.warning("transformers not installed. NLLB unavailable.")
        except Exception as e:
            logger.warning("Failed to load NLLB: %s", e)

    def translate(
        self,
        text: str,
        source_lang: str = "jpn_Jpan",
        target_lang: str = "eng_Latn",
    ) -> str:
        """Translate text using NLLB.

        Args:
            text: Text to translate.
            source_lang: NLLB source language code (e.g., 'jpn_Jpan').
            target_lang: NLLB target language code (e.g., 'eng_Latn').

        Returns:
            Translated text string.
        """
        if not self._initialized or self._model is None or self._tokenizer is None:
            return text

        try:
            import torch
            self._tokenizer.src_lang = source_lang
            inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(self.device)

            with torch.no_grad():
                translated = self._model.generate(
                    **inputs,
                    forced_bos_token_id=self._tokenizer.lang_code_to_id[target_lang],
                    max_length=self.max_length,
                    num_beams=4,
                    early_stopping=True,
                )

            result = self._tokenizer.decode(translated[0], skip_special_tokens=True)
            return result.strip()
        except Exception as e:
            logger.error("NLLB translation failed: %s", e)
            return text

    def cleanup(self) -> None:
        """Release model resources."""
        self._model = None
        self._tokenizer = None
        self._initialized = False
        logger.info("NLLB resources released")


class M2M100Engine:
    """Facebook's Many-to-Many multilingual model — 100 languages.

    Model: facebook/m2m100_418M or facebook/m2m100_1.2B

    Strengths: Good many-to-many support, lighter than NLLB.
    """

    def __init__(
        self,
        model_name: str = "facebook/m2m100_418M",
        device: str = "cpu",
        max_length: int = 200,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self._tokenizer = None
        self._model = None
        self._initialized = False

    def initialize(self) -> None:
        """Load the M2M100 model and tokenizer."""
        if self._initialized:
            return
        try:
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
            logger.info("Loading M2M100 model: %s", self.model_name)
            self._tokenizer = M2M100Tokenizer.from_pretrained(self.model_name)
            self._model = M2M100ForConditionalGeneration.from_pretrained(self.model_name).to(self.device)
            self._model.eval()
            self._initialized = True
            logger.info("M2M100 model loaded")
        except ImportError:
            logger.warning("transformers not installed. M2M100 unavailable.")
        except Exception as e:
            logger.warning("Failed to load M2M100: %s", e)

    def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
    ) -> str:
        """Translate text using M2M100."""
        if not self._initialized or self._model is None or self._tokenizer is None:
            return text

        try:
            import torch
            self._tokenizer.src_lang = source_lang
            inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(self.device)

            with torch.no_grad():
                translated = self._model.generate(
                    **inputs,
                    forced_bos_token_id=self._tokenizer.get_lang_id(target_lang),
                    max_length=self.max_length,
                    num_beams=4,
                )

            result = self._tokenizer.decode(translated[0], skip_special_tokens=True)
            return result.strip()
        except Exception as e:
            logger.error("M2M100 translation failed: %s", e)
            return text

    def cleanup(self) -> None:
        """Release model resources."""
        self._model = None
        self._tokenizer = None
        self._initialized = False
        logger.info("M2M100 resources released")


class MarianMTEngine:
    """HuggingFace MarianMT — lightweight per-language-pair models.

    Models: Helsinki-NLP/opus-mt-ja-en, opus-mt-zh-en, etc.

    Strengths: Fastest offline option, tiny models, good for single language pairs.
    Weaknesses: Requires separate model per language pair, no context awareness.
    """

    # Common manga-relevant model name patterns
    MODEL_PATTERNS = {
        ("ja", "en"): "Helsinki-NLP/opus-mt-ja-en",
        ("zh", "en"): "Helsinki-NLP/opus-mt-zh-en",
        ("ko", "en"): "Helsinki-NLP/opus-mt-ko-en",
        ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
        ("es", "en"): "Helsinki-NLP/opus-mt-es-en",
        ("ru", "en"): "Helsinki-NLP/opus-mt-ru-en",
        ("de", "en"): "Helsinki-NLP/opus-mt-de-en",
        ("it", "en"): "Helsinki-NLP/opus-mt-it-en",
        ("pt", "en"): "Helsinki-NLP/opus-mt-pt-en",
        ("nl", "en"): "Helsinki-NLP/opus-mt-nl-en",
        ("th", "en"): "Helsinki-NLP/opus-mt-th-en",
        ("vi", "en"): "Helsinki-NLP/opus-mt-vi-en",
        ("ar", "en"): "Helsinki-NLP/opus-mt-ar-en",
        ("tr", "en"): "Helsinki-NLP/opus-mt-tr-en",
        ("ja", "zh"): "Helsinki-NLP/opus-mt-ja-zh",
        ("en", "ja"): "Helsinki-NLP/opus-mt-en-ja",
        ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
        ("en", "ko"): "Helsinki-NLP/opus-mt-en-ko",
        ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
        ("en", "es"): "Helsinki-NLP/opus-mt-en-es",
        ("en", "ru"): "Helsinki-NLP/opus-mt-en-ru",
        ("en", "de"): "Helsinki-NLP/opus-mt-en-de",
        ("en", "pt"): "Helsinki-NLP/opus-mt-en-pt",
    }

    def __init__(
        self,
        model_name: str | None = None,
        device: str = "cpu",
    ) -> None:
        self._model_name_override = model_name
        self.device = device
        self._tokenizer = None
        self._model = None
        self._loaded_pair: tuple[str, str] | None = None
        self._initialized = False

    def initialize(self, source_lang: str = "ja", target_lang: str = "en") -> None:
        """Load the MarianMT model for the specified language pair.

        Args:
            source_lang: ISO source language code.
            target_lang: ISO target language code.
        """
        if self._initialized and self._loaded_pair == (source_lang, target_lang):
            return

        pair = (source_lang, target_lang)
        model_name = (
            self._model_name_override
            or self.MODEL_PATTERNS.get(pair)
        )

        if not model_name:
            logger.warning("No MarianMT model for %s→%s", source_lang, target_lang)
            return

        try:
            from transformers import MarianMTModel, MarianTokenizer
            logger.info("Loading MarianMT: %s", model_name)
            self._tokenizer = MarianTokenizer.from_pretrained(model_name)
            self._model = MarianMTModel.from_pretrained(model_name).to(self.device)
            self._model.eval()
            self._loaded_pair = pair
            self._initialized = True
            logger.info("MarianMT loaded for %s→%s", source_lang, target_lang)
        except ImportError:
            logger.warning("transformers not installed. MarianMT unavailable.")
        except Exception as e:
            logger.warning("Failed to load MarianMT %s: %s", model_name, e)

    def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
    ) -> str:
        """Translate text using MarianMT."""
        if not self._initialized or self._model is None or self._tokenizer is None:
            return text

        try:
            import torch
            inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(self.device)
            with torch.no_grad():
                translated = self._model.generate(**inputs, max_length=200, num_beams=4)
            result = self._tokenizer.decode(translated[0], skip_special_tokens=True)
            return result.strip()
        except Exception as e:
            logger.error("MarianMT translation failed: %s", e)
            return text

    def cleanup(self) -> None:
        """Release model resources."""
        self._model = None
        self._tokenizer = None
        self._initialized = False
        self._loaded_pair = None
        logger.info("MarianMT resources released")


class ArgosEngine:
    """Argos Translate — offline neural machine translation.

    Package: argostranslate
    Models are downloaded on first use.

    Strengths: Simple API, automatic model download, good for many pairs.
    Weaknesses: Model download required first time, quality varies.
    """

    def __init__(self) -> None:
        self._installed = False

    def initialize(self) -> None:
        """Check argostranslate availability. Models are auto-downloaded."""
        if self._installed:
            return
        try:
            import argostranslate.package
            import argostranslate.translate
            self._installed = True
            logger.info("Argos Translate initialized")
        except ImportError:
            logger.warning("argostranslate not installed. Argos unavailable.")

    def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
    ) -> str:
        """Translate text using Argos Translate.

        Downloads the model package if not already cached.
        """
        if not self._installed:
            return text

        try:
            import argostranslate.package
            import argostranslate.translate

            # Download and install package if needed
            argostranslate.package.update_package_index()
            available_packages = argostranslate.package.get_available_packages()
            package_to_install = next(
                (
                    pkg for pkg in available_packages
                    if pkg.from_code == source_lang and pkg.to_code == target_lang
                ),
                None,
            )

            if package_to_install:
                download_path = package_to_install.download()
                argostranslate.package.install_from_path(download_path)

            # Translate
            result = argostranslate.translate.translation(text, source_lang, target_lang)
            return result.strip() if result else text
        except Exception as e:
            logger.error("Argos translation failed: %s", e)
            return text

    def cleanup(self) -> None:
        """Release resources."""
        logger.info("Argos resources released")


# ═══════════════════════════════════════════════════════════════════════════
# CLOUD API ENGINES
# ═══════════════════════════════════════════════════════════════════════════


class GoogleTranslateEngine:
    """Google Translate API.

    Uses google.cloud.translate (preferred) or googletrans (free fallback).

    Strengths: 100+ languages, free tier available, good quality.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._use_cloud_api = bool(settings.GOOGLE_API_KEY)

    def initialize(self) -> None:
        self._initialized = True

    async def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
    ) -> str:
        """Translate using Google Translate."""
        if self._use_cloud_api:
            return await self._translate_cloud(text, source_lang, target_lang)
        return await self._translate_free(text, source_lang, target_lang)

    async def _translate_cloud(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        """Use Google Cloud Translation API."""
        try:
            from google.cloud import translate_v2 as translate
            client = translate.Client()
            result = client.translate(
                text, source_language=source_lang, target_language=target_lang
            )
            return result.get("translatedText", text)
        except Exception as e:
            logger.error("Google Cloud Translate failed: %s", e)
            return text

    async def _translate_free(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        """Use googletrans free library."""
        try:
            import googletrans
            translator = googletrans.Translator()
            result = translator.translate(text, src=source_lang, dest=target_lang)
            return result.text if result and result.text else text
        except Exception as e:
            logger.error("googletrans failed: %s", e)
            return text

    def cleanup(self) -> None:
        logger.info("Google Translate resources released")


class DeepLEngine:
    """DeepL translation API — highest quality machine translation.

    Requires DEEPL_API_KEY env var.
    Free tier: 500k characters/month.

    Strengths: Best quality for European languages, excellent for
    Japanese→English manga translation.
    """

    def __init__(self) -> None:
        self._client = None
        self._api_key = os.environ.get("DEEPL_API_KEY", "")

    def initialize(self) -> None:
        if not self._api_key:
            logger.warning("DEEPL_API_KEY not set. DeepL unavailable.")
            return
        try:
            import deepl
            self._client = deepl.Translator(self._api_key)
            logger.info("DeepL initialized")
        except ImportError:
            logger.warning("deepl library not installed. DeepL unavailable.")
        except Exception as e:
            logger.warning("DeepL init failed: %s", e)

    async def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "EN-US",
    ) -> str:
        """Translate using DeepL.

        DeepL uses uppercase language codes with region: EN-US, JA, etc.
        """
        if self._client is None:
            return text

        try:
            source_upper = source_lang.upper()
            target_upper = self._map_target(target_lang)

            result = self._client.translate_text(
                text,
                source_lang=source_upper,
                target_lang=target_upper,
            )
            return result.text if result else text
        except Exception as e:
            logger.error("DeepL translation failed: %s", e)
            return text

    @staticmethod
    def _map_target(lang: str) -> str:
        """Map ISO codes to DeepL target language codes."""
        mapping = {
            "en": "EN-US", "ja": "JA", "zh": "ZH", "ko": "KO",
            "fr": "FR", "es": "ES", "de": "DE", "it": "IT",
            "pt": "PT-BR", "ru": "RU", "nl": "NL", "pl": "PL",
            "sv": "SV", "da": "DA", "fi": "FI", "cs": "CS",
            "hu": "HU", "ro": "RO", "el": "EL", "bg": "BG",
            "lt": "LT", "lv": "LV", "et": "ET", "sl": "SL",
            "sk": "SK", "hr": "HR", "uk": "UK",
        }
        return mapping.get(lang, "EN-US")

    def cleanup(self) -> None:
        self._client = None
        logger.info("DeepL resources released")


class LibreTranslateEngine:
    """LibreTranslate — self-hostable, FOSS translation API.

    Default: https://libretranslate.com (rate-limited)
    Recommended: Self-host via Docker: docker run -p 5000:5000 libretranslate/libretranslate

    Strengths: Free, no API key needed for self-hosted, good privacy.
    """

    def __init__(
        self,
        api_url: str = "https://libretranslate.com",
        api_key: str = "",
    ) -> None:
        self.api_url = api_url or os.environ.get("LIBRETRANSLATE_URL", "https://libretranslate.com")
        self.api_key = api_key or os.environ.get("LIBRETRANSLATE_API_KEY", "")
        self._initialized = False

    def initialize(self) -> None:
        self._initialized = True

    async def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
    ) -> str:
        """Translate using LibreTranslate."""
        try:
            import aiohttp

            payload = {
                "q": text,
                "source": source_lang,
                "target": target_lang,
                "format": "text",
            }
            if self.api_key:
                payload["api_key"] = self.api_key

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/translate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("translatedText", text)
                    else:
                        body = await resp.text()
                        logger.warning("LibreTranslate HTTP %d: %s", resp.status, body)
                        return text
        except ImportError:
            logger.warning("aiohttp not installed. LibreTranslate unavailable.")
            return text
        except Exception as e:
            logger.error("LibreTranslate failed: %s", e)
            return text

    def cleanup(self) -> None:
        logger.info("LibreTranslate resources released")


class GeminiEngine:
    """Google Gemini LLM — context-aware manga translation.

    Model: gemini-1.5-flash (fast, cheap) or gemini-1.5-pro (quality).
    Uses the full manga prompt with context awareness.

    Strengths: Excellent context understanding, preserves names/emotions.
    """

    def __init__(self) -> None:
        self._model = None
        self._api_key = settings.GOOGLE_API_KEY

    def initialize(self) -> None:
        if not self._api_key:
            logger.warning("GOOGLE_API_KEY not set. Gemini unavailable.")
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel("gemini-1.5-flash")
            logger.info("Gemini initialized")
        except ImportError:
            logger.warning("google-generativeai not installed. Gemini unavailable.")
        except Exception as e:
            logger.warning("Gemini init failed: %s", e)

    async def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
        context: str = "",
    ) -> str:
        """Translate using Gemini with manga context."""
        if self._model is None:
            return text

        try:
            prompt = MANGA_SYSTEM_PROMPT.format(
                target_lang=target_lang,
                context=context or "General manga",
                text=text,
            )
            response = await self._model.generate_content_async(prompt)
            result = response.text if response and hasattr(response, 'text') else text
            return result.strip()
        except Exception as e:
            logger.error("Gemini translation failed: %s", e)
            return text

    def cleanup(self) -> None:
        self._model = None
        logger.info("Gemini resources released")


class OpenAIEngine:
    """OpenAI GPT — context-aware manga translation.

    Models: gpt-4o-mini (fast, cheap), gpt-4o (best quality).
    Uses the full manga prompt with name/emotion preservation.

    Strengths: Best manga translation quality, understands cultural context.
    """

    def __init__(self) -> None:
        self._client = None
        self._api_key = settings.OPENAI_API_KEY
        self._model = settings.OPENAI_MODEL

    def initialize(self) -> None:
        if not self._api_key:
            logger.warning("OPENAI_API_KEY not set. OpenAI unavailable.")
            return
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self._api_key)
            logger.info("OpenAI initialized (model: %s)", self._model)
        except ImportError:
            logger.warning("openai library not installed.")
        except Exception as e:
            logger.warning("OpenAI init failed: %s", e)

    async def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
        context: str = "",
    ) -> str:
        """Translate using OpenAI GPT with manga context."""
        if self._client is None:
            return text

        try:
            prompt = MANGA_SYSTEM_PROMPT.format(
                target_lang=target_lang,
                context=context or "General manga",
                text=text,
            )
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=len(text) * 3 + 128,
            )
            result = response.choices[0].message.content or text
            return result.strip()
        except Exception as e:
            logger.error("OpenAI translation failed: %s", e)
            return text

    def cleanup(self) -> None:
        self._client = None
        logger.info("OpenAI resources released")


class ClaudeEngine:
    """Anthropic Claude — context-aware manga translation.

    Models: claude-3-haiku (fast, cheap), claude-3-sonnet (balanced),
    claude-3-opus (best quality).

    Strengths: Excellent at following complex instructions, tone preservation.
    """

    def __init__(self) -> None:
        self._client = None
        self._api_key = settings.ANTHROPIC_API_KEY
        self._model = settings.ANTHROPIC_MODEL

    def initialize(self) -> None:
        if not self._api_key:
            logger.warning("ANTHROPIC_API_KEY not set. Claude unavailable.")
            return
        try:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self._api_key)
            logger.info("Claude initialized (model: %s)", self._model)
        except ImportError:
            logger.warning("anthropic library not installed.")
        except Exception as e:
            logger.warning("Claude init failed: %s", e)

    async def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
        context: str = "",
    ) -> str:
        """Translate using Claude with manga context."""
        if self._client is None:
            return text

        try:
            prompt = MANGA_SYSTEM_PROMPT.format(
                target_lang=target_lang,
                context=context or "General manga",
                text=text,
            )
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=len(text) * 3 + 128,
                system="You are a professional manga translator.",
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.content[0].text if response.content else text
            return result.strip()
        except Exception as e:
            logger.error("Claude translation failed: %s", e)
            return text

    def cleanup(self) -> None:
        self._client = None
        logger.info("Claude resources released")


class OllamaEngine:
    """Ollama — local LLMs via HTTP API.

    Run: ollama run llama3.2 (or any model)
    API: http://localhost:11434/api/generate

    Strengths: Completely free, private, works offline.
    Can use llama3.2, mistral, mixtral, or fine-tuned manga models.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
    ) -> None:
        self.base_url = base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.2")
        self._initialized = False

    def initialize(self) -> None:
        try:
            import aiohttp
            self._initialized = True
            logger.info("Ollama engine ready (url: %s, model: %s)", self.base_url, self.model)
        except ImportError:
            logger.warning("aiohttp not installed. Ollama unavailable.")

    async def translate(
        self,
        text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
        context: str = "",
    ) -> str:
        """Translate using Ollama's local LLM."""
        if not self._initialized:
            return text

        try:
            import aiohttp

            prompt = MANGA_SYSTEM_PROMPT.format(
                target_lang=target_lang,
                context=context or "General manga",
                text=text,
            )

            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": len(text) * 3 + 128,
                },
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("response", text)
                        return result.strip()
                    else:
                        body = await resp.text()
                        logger.warning("Ollama HTTP %d: %s", resp.status, body)
                        return text
        except ImportError:
            logger.warning("aiohttp not installed. Ollama unavailable.")
            return text
        except Exception as e:
            logger.error("Ollama translation failed: %s", e)
            return text

    def cleanup(self) -> None:
        logger.info("Ollama resources released")


# ── Language auto-detection ──────────────────────────────────────────────


class LanguageDetector:
    """Automatic language detection for source text.

    Uses fasttext (preferred) or langdetect (fallback).
    Detects the language of OCR output to auto-select source language.
    """

    # Pre-trained fasttext lid model
    FASTTEXT_MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin"

    def __init__(self) -> None:
        self._fasttext_model = None
        self._initialized = False

    def initialize(self) -> None:
        """Try fasttext first, fall back to langdetect."""
        if self._initialized:
            return

        # Try fasttext
        try:
            import fasttext
            import os
            model_path = str(settings.MODELS_DIR / "lid.176.bin")
            if os.path.exists(model_path):
                self._fasttext_model = fasttext.load_model(model_path)
                logger.info("fasttext language detector loaded")
            else:
                logger.info("fasttext model not found at %s, using langdetect fallback", model_path)
        except ImportError:
            logger.info("fasttext not installed, using langdetect fallback")

        self._initialized = True

    def detect(self, text: str) -> str:
        """Detect the language of a text string.

        Returns ISO 639-1 language code (e.g., 'ja', 'en', 'ko').
        Returns 'unknown' if detection fails.
        """
        if not text.strip():
            return "unknown"

        # Fasttext detection
        if self._fasttext_model is not None:
            try:
                predictions = self._fasttext_model.predict(text.replace("\n", " "), k=1)
                lang = predictions[0][0].replace("__label__", "")
                # fasttext returns ISO 639-1 codes
                return lang if len(lang) <= 3 else lang[:2]
            except Exception:
                pass

        # langdetect fallback
        try:
            from langdetect import detect
            return detect(text)
        except ImportError:
            pass
        except Exception:
            pass

        # Simple heuristic fallback
        return self._heuristic_detect(text)

    @staticmethod
    def _heuristic_detect(text: str) -> str:
        """Simple character-range-based language detection."""
        if not text:
            return "unknown"

        # Count characters per script
        has_hiragana = any(0x3040 <= ord(c) <= 0x309F for c in text)
        has_katakana = any(0x30A0 <= ord(c) <= 0x30FF for c in text)
        has_hangul = any(0xAC00 <= ord(c) <= 0xD7AF for c in text)
        has_cjk = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
        has_arabic = any(0x0600 <= ord(c) <= 0x06FF for c in text)
        has_thai = any(0x0E00 <= ord(c) <= 0x0E7F for c in text)
        has_cyrillic = any(0x0400 <= ord(c) <= 0x04FF for c in text)

        if has_hiragana or has_katakana:
            return "ja"
        if has_hangul:
            return "ko"
        if has_cjk:
            return "zh"
        if has_arabic:
            return "ar"
        if has_thai:
            return "th"
        if has_cyrillic:
            return "ru"

        # Default to English for Latin text
        latin_chars = sum(1 for c in text if c.isascii() and c.isalpha())
        if latin_chars > len(text) * 0.5:
            return "en"

        return "unknown"

    def cleanup(self) -> None:
        self._fasttext_model = None
        self._initialized = False
        logger.info("Language detector resources released")
