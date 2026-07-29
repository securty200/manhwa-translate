# Architecture Overview

## System Design

The AI Manga Translator uses a **modular pipeline architecture** where each translation stage is an independent service that can be swapped or upgraded individually.

## Pipeline Flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Import  │ →  │  Detect  │ →  │   OCR    │ →  │Translate │ →  │  Export  │
│  Pages   │    │  Bubbles │    │  Text    │    │  Text    │    │  Image   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                     ↓
                                              ┌──────────┐
                                              │ Inpaint  │
                                              │ Original │
                                              └──────────┘
                                                     ↓
                                              ┌──────────┐
                                              │  Render  │
                                              │ Translated│
                                              └──────────┘
```

## Component Details

### 1. Text Detection (`backend/detector/`)
- **Input**: Manga page image
- **Process**: Identifies speech bubbles, thought bubbles, narration boxes, and SFX
- **Models**: CRAFT (text), DBNet (text), YOLO (bubbles)
- **Fallback**: OpenCV contour analysis

### 2. OCR (`backend/ocr/`)
- **Input**: Cropped bubble/region images
- **Process**: Extracts Japanese text from each region
- **Engines**: MangaOCR (recommended), PaddleOCR, Tesseract
- **Batching**: Processes multiple regions concurrently

### 3. Translation (`backend/translator/`)
- **Input**: Japanese text strings
- **Process**: Translates to target language with manga-aware prompts
- **Backends**: OpenAI, Anthropic, Google, DeepSeek, Local
- **Features**: Context preservation, honorific handling, cultural adaptation

### 4. Inpainting (`backend/inpainting/`)
- **Input**: Original page + bubble bounding boxes
- **Process**: Removes original text from bubbles
- **Models**: LaMa, Stable Diffusion Inpainting
- **Fallback**: OpenCV inpaint or Gaussian blur

### 5. Rendering (`backend/renderer/`)
- **Input**: Inpainted page + translated text + bubble positions
- **Process**: Renders translated text into bubbles with proper sizing
- **Features**: Auto font-size, text wrapping, CJK support, centering

## Data Flow

```
User Upload → DB Save → Job Created → Worker Processes → WebSocket Updates
                                                                    ↓
                                                     User Downloads Result
```

## Database Schema

```
Manga (1) ──→ Chapter (N) ──→ Page (N) ──→ Bubble (N)
                  ↓
           TranslationJob (1) ──→ TranslationSegment (N)
```

## API Design

- **REST**: CRUD operations for manga, chapters, pages
- **Async Job**: Create translation job, poll status
- **WebSocket**: Real-time progress for long-running jobs
