"""Translation module for converting manga text between languages.

Supports 11 engines:
- Offline: NLLB, M2M100, MarianMT, Argos Translate
- Cloud: Google Translate, DeepL, LibreTranslate, Gemini, OpenAI, Claude, Ollama

Features:
- Auto-source-language detection
- Context-aware manga translation
- Name/emotion preservation
- Page-level batch translation
"""

from backend.translator.service import TranslationService, TranslationResult
from backend.translator.engines import (
    NLLBEngine,
    M2M100Engine,
    MarianMTEngine,
    ArgosEngine,
    GoogleTranslateEngine,
    DeepLEngine,
    LibreTranslateEngine,
    GeminiEngine,
    OpenAIEngine,
    ClaudeEngine,
    OllamaEngine,
    LanguageDetector,
    EngineTranslationResult,
    MANGA_SYSTEM_PROMPT,
)

__all__ = [
    "TranslationService",
    "TranslationResult",
    "NLLBEngine",
    "M2M100Engine",
    "MarianMTEngine",
    "ArgosEngine",
    "GoogleTranslateEngine",
    "DeepLEngine",
    "LibreTranslateEngine",
    "GeminiEngine",
    "OpenAIEngine",
    "ClaudeEngine",
    "OllamaEngine",
    "LanguageDetector",
    "EngineTranslationResult",
    "MANGA_SYSTEM_PROMPT",
]
