"""Enhanced translation service with 11 modular engines and manga-optimized translation.

Orchestrates offline (NLLB, M2M100, MarianMT, Argos) and cloud (Google, DeepL,
LibreTranslate, Gemini, OpenAI, Claude, Ollama) engines with:
- Auto-source-language detection
- Page-context-aware batch translation
- Name/emotion preservation via LLM prompting
- Engine priority fallback

Engines are initialized LAZILY — only when first used, not all upfront.
Each initialization has a timeout to prevent hanging on model downloads.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from backend.config import settings
from backend.translator.engines import (
    NLLBEngine, M2M100Engine, MarianMTEngine, ArgosEngine,
    GoogleTranslateEngine, DeepLEngine, LibreTranslateEngine,
    GeminiEngine, OpenAIEngine, ClaudeEngine, OllamaEngine,
    LanguageDetector, normalize_language_code,
)

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """Result of a single text translation."""

    translated_text: str
    source_language: str = "ja"
    target_language: str = "en"
    confidence: float = 1.0
    processing_time_ms: float = 0.0
    model_used: str = ""
    detected_source_language: str = ""
    metadata: dict = field(default_factory=dict)


class TranslationService:
    """Enhanced translation service with modular engine support.

    Supports 11 engines across two tiers:
    - Offline: NLLB, M2M100, MarianMT, Argos
    - Cloud: Google, DeepL, LibreTranslate, Gemini, OpenAI, Claude, Ollama

    Engines are initialized LAZILY on first use. This prevents the service
    from hanging on model downloads during startup or testing.
    """

    ENGINE_TYPES = {
        "nllb": "offline",
        "m2m100": "offline",
        "marianmt": "offline",
        "argos": "offline",
        "google": "cloud",
        "deepl": "cloud",
        "libre": "cloud",
        "gemini": "cloud",
        "openai": "cloud",
        "claude": "cloud",
        "ollama": "cloud",
    }

    def __init__(self, engine_priority: list[str] | None = None) -> None:
        self.engine_priority = engine_priority or [
            "openai", "claude", "gemini",
            "deepl", "google", "libre",
            "ollama",
            "nllb", "m2m100", "marianmt", "argos",
        ]
        self._engines: dict = {}
        self._initialized: dict[str, bool] = {}
        self._detector = None

    @property
    def active_engine(self) -> str | None:
        """Return the name of the first successfully initialized engine."""
        for name in self.engine_priority:
            if self._initialized.get(name, False):
                return name
        return None

    async def _ensure_detector(self) -> None:
        """Lazy-init the language detector."""
        if self._detector is not None:
            return
        try:
            from backend.translator.engines import LanguageDetector
            self._detector = LanguageDetector()
            loop = asyncio.get_event_loop()

            def _init() -> None:
                self._detector.initialize()

            await loop.run_in_executor(None, _init)
        except Exception as e:
            logger.debug("Language detector init: %s", e)

    async def _ensure_engine(
        self,
        engine_name: str,
        source_lang: str = "ja",
        target_lang: str = "en",
    ) -> bool:
        """Lazy-initialize a single engine if not already initialized.

        Returns True if engine is available, False otherwise.
        Has a short timeout to prevent hanging on model downloads.
        """
        if self._initialized.get(engine_name, False):
            return True

        if engine_name in self._initialized and not self._initialized[engine_name]:
            return False  # Previously failed to init

        loop = asyncio.get_event_loop()
        timeout = min(settings.TRANSLATION_TIMEOUT_SECONDS, 10)

        try:
            eng = None
            init_fn = None

            if engine_name == "nllb":
                eng = NLLBEngine(device=settings.OCR_DEVICE)
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "m2m100":
                eng = M2M100Engine(device=settings.OCR_DEVICE)
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "marianmt":
                eng = MarianMTEngine(device=settings.OCR_DEVICE)
                def _init(e): e.initialize(source_lang, target_lang)
                init_fn = _init
            elif engine_name == "argos":
                eng = ArgosEngine()
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "google":
                eng = GoogleTranslateEngine()
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "deepl":
                eng = DeepLEngine()
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "libre":
                eng = LibreTranslateEngine()
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "gemini":
                eng = GeminiEngine()
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "openai":
                eng = OpenAIEngine()
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "claude":
                eng = ClaudeEngine()
                def _init(e): e.initialize()
                init_fn = _init
            elif engine_name == "ollama":
                eng = OllamaEngine()
                def _init(e): e.initialize()
                init_fn = _init

            if eng is not None and init_fn is not None:
                await asyncio.wait_for(
                    loop.run_in_executor(None, init_fn, eng),
                    timeout=timeout,
                )
                self._engines[engine_name] = eng
                self._initialized[engine_name] = True
                logger.info("Engine '%s' initialized", engine_name)
                return True

        except asyncio.TimeoutError:
            logger.warning("Engine '%s' init timed out after %ds", engine_name, timeout)
        except ImportError as e:
            logger.debug("Engine '%s' package not available: %s", engine_name, e)
        except Exception as e:
            logger.debug("Engine '%s' not available: %s", engine_name, e)

        self._initialized[engine_name] = False
        return False

    async def detect_language(self, text: str) -> str:
        """Detect the language of a text string."""
        if not text.strip():
            return "unknown"
        await self._ensure_detector()
        if self._detector is not None:
            loop = asyncio.get_event_loop()
            def _detect():
                return self._detector.detect(text)
            return await loop.run_in_executor(None, _detect)
        return "unknown"

    async def translate(
        self,
        text: str,
        source_language: str = "auto",
        target_language: str = "en",
        context: str | None = None,
        use_cache: bool = True,
    ) -> TranslationResult:
        """Translate a single text string using the best available engine.

        Results are cached for performance. Auto-detects source language
        if set to 'auto'. Engines are lazily initialized one at a time
        in priority order. Falls back through engine priority if one
        fails or times out.

        Args:
            text: Text to translate.
            source_language: Source language code ('auto' for auto-detect).
            target_language: Target language code.
            context: Optional manga context (genre, characters, setting).
            use_cache: Whether to check/populate the translation cache.

        Returns:
            TranslationResult with translated text.
        """
        if not text.strip():
            return TranslationResult(
                translated_text="",
                source_language=source_language,
                target_language=target_language,
            )

        # Check translation cache
        if use_cache:
            import hashlib
            cache_key = f"trans:{hashlib.md5(text.encode()).hexdigest()}:{source_language}:{target_language}"
            if context:
                context_hash = hashlib.md5(context.encode()).hexdigest()[:16]
                cache_key += f":ctx={context_hash}"
            from backend.services.cache_service import translation_cache
            cached = await translation_cache.get(cache_key)
            if cached is not None:
                logger.debug("Translation cache hit: %s...", text[:30])
                return cached

        start_time = time.perf_counter()

        # Auto-detect source language
        detected_source = ""
        if source_language == "auto":
            detected_source = await self.detect_language(text)
            if detected_source != "unknown":
                source_language = detected_source

        # Try engines lazily in priority order
        timeout = settings.TRANSLATION_TIMEOUT_SECONDS

        for engine_name in self.engine_priority:
            # Lazy-init this engine (skips quickly if already tried and failed)
            available = await self._ensure_engine(engine_name, source_language, target_language)
            if not available:
                continue

            engine = self._engines.get(engine_name)
            if engine is None:
                continue

            try:
                if engine_name in ("nllb", "m2m100", "marianmt", "argos"):
                    result = await asyncio.wait_for(
                        self._translate_offline(engine, engine_name, text,
                                                 source_language, target_language),
                        timeout=timeout,
                    )
                elif engine_name in ("google", "deepl", "libre"):
                    result = await asyncio.wait_for(
                        self._translate_api(engine, engine_name, text,
                                            source_language, target_language),
                        timeout=timeout,
                    )
                elif engine_name in ("gemini", "openai", "claude", "ollama"):
                    result = await asyncio.wait_for(
                        self._translate_llm(engine, engine_name, text,
                                            source_language, target_language, context),
                        timeout=timeout,
                    )
                else:
                    continue

                if not (result and result.strip()):
                    logger.debug("Engine %s returned empty, trying next", engine_name)
                    continue

                elapsed = (time.perf_counter() - start_time) * 1000
                final_result = TranslationResult(
                    translated_text=result.strip(),
                    source_language=source_language,
                    target_language=target_language,
                    confidence=0.95,
                    processing_time_ms=round(elapsed, 2),
                    model_used=engine_name,
                    detected_source_language=detected_source,
                )

                # Cache the result
                if use_cache:
                    try:
                        from backend.services.cache_service import translation_cache
                        asyncio.create_task(
                            translation_cache.set(
                                cache_key, final_result,
                                ttl=settings.CACHE_TRANSLATION_TTL,
                            )
                        )
                    except Exception:
                        pass

                return final_result

            except asyncio.TimeoutError:
                logger.warning("Engine %s timed out after %ds", engine_name, timeout)
                continue
            except Exception as e:
                logger.warning("Engine %s failed: %s", engine_name, e)
                continue

        # All engines failed — return original as fallback
        elapsed = (time.perf_counter() - start_time) * 1000
        logger.error("All engines failed for text: %s...", text[:50])
        return TranslationResult(
            translated_text=text,
            source_language=source_language,
            target_language=target_language,
            confidence=0.0,
            processing_time_ms=round(elapsed, 2),
            model_used="fallback",
            detected_source_language=detected_source,
        )

    async def _translate_offline(
        self, engine, engine_name: str, text: str,
        source_lang: str, target_lang: str,
    ) -> str:
        """Translate using an offline model engine."""
        nsrc = normalize_language_code(engine_name, source_lang)
        ntgt = normalize_language_code(engine_name, target_lang)
        loop = asyncio.get_event_loop()

        if engine_name in ("nllb", "m2m100", "argos"):
            def _run():
                return engine.translate(text, source_lang=nsrc, target_lang=ntgt)
        elif engine_name == "marianmt":
            def _run():
                return engine.translate(text, source_lang=source_lang, target_lang=target_lang)
        else:
            return text

        return await loop.run_in_executor(None, _run)

    async def _translate_api(
        self, engine, engine_name: str, text: str,
        source_lang: str, target_lang: str,
    ) -> str:
        """Translate using a cloud API engine."""
        return await engine.translate(text, source_lang=source_lang, target_lang=target_lang)

    async def _translate_llm(
        self, engine, engine_name: str, text: str,
        source_lang: str, target_lang: str, context: str | None,
    ) -> str:
        """Translate using an LLM engine with manga context."""
        return await engine.translate(
            text, source_lang=source_lang, target_lang=target_lang,
            context=context or "",
        )

    async def translate_batch(
        self,
        texts: list[str],
        source_language: str = "auto",
        target_language: str = "en",
        context: str | None = None,
        use_cache: bool = True,
    ) -> list[TranslationResult]:
        """Translate multiple texts with concurrent processing.

        Uses configurable concurrency from settings and checks cache first.

        Args:
            texts: List of texts to translate.
            source_language: Source language code.
            target_language: Target language code.
            context: Optional manga context.
            use_cache: Whether to check the translation cache.

        Returns:
            List of TranslationResult objects.
        """
        if not texts:
            return []

        effective_source = source_language
        if source_language == "auto":
            first_text = next((t for t in texts if t.strip()), "")
            if first_text:
                detected = await self.detect_language(first_text)
                if detected != "unknown":
                    effective_source = detected

        semaphore = asyncio.Semaphore(settings.TRANSLATOR_BATCH_CONCURRENCY)

        async def _translate_one(text: str) -> TranslationResult:
            async with semaphore:
                return await self.translate(
                    text, source_language=effective_source,
                    target_language=target_language, context=context,
                    use_cache=use_cache,
                )

        tasks = [_translate_one(t) for t in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final_results: list[TranslationResult] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Batch item %d failed: %s", idx, result)
                final_results.append(TranslationResult(
                    translated_text=texts[idx],
                    source_language=effective_source,
                    target_language=target_language,
                    confidence=0.0, model_used="fallback",
                ))
            else:
                final_results.append(result)
        return final_results

    async def translate_page_bubbles(
        self, bubbles: list[dict], source_language: str = "auto",
        target_language: str = "en", manga_context: str | None = None,
    ) -> list[dict]:
        """Translate all bubbles on a manga page with shared context."""
        if not bubbles:
            return []

        texts = [
            b.get("original_text", "")
            for b in sorted(bubbles, key=lambda x: x.get("reading_order", 0))
        ]
        page_context = manga_context or ""
        non_empty = [t for t in texts if t.strip()]
        if non_empty:
            first_text = non_empty[0][:100]
            if first_text:
                page_context = f"{manga_context or ''}\nPage contains {len(texts)} text bubbles. First: '{first_text}'"

        results = await self.translate_batch(
            texts, source_language=source_language,
            target_language=target_language,
            context=page_context.strip() or None,
        )

        translated_bubbles = []
        for idx, bubble in enumerate(sorted(bubbles, key=lambda x: x.get("reading_order", 0))):
            result = results[idx] if idx < len(results) else TranslationResult(
                translated_text=bubble.get("original_text", "")
            )
            translated_bubbles.append({
                **bubble,
                "translated_text": result.translated_text,
                "translation_confidence": result.confidence,
                "translation_engine": result.model_used,
            })
        return translated_bubbles

    def get_engine_status(self) -> list[dict]:
        """Get the status of all translation engines."""
        return [
            {"name": name, "type": self.ENGINE_TYPES.get(name, "unknown"),
             "available": self._initialized.get(name, False)}
            for name in self.engine_priority
        ]

    async def cleanup(self) -> None:
        """Release resources used by all translation engines."""
        for engine_name, engine in self._engines.items():
            try:
                if hasattr(engine, "cleanup"):
                    engine.cleanup()
            except Exception as e:
                logger.debug("Cleanup %s: %s", engine_name, e)
        if self._detector is not None:
            try:
                self._detector.cleanup()
            except Exception:
                pass
        self._engines.clear()
        self._initialized.clear()
        self._detector = None
        logger.info("All translation resources released")
