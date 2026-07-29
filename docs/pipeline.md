# Translation Pipeline

## Overview

The translation pipeline processes manga pages through 5 stages:

```
Page Image → Detect → OCR → Translate → Inpaint → Render → Result
```

## Stage 1: Region Detection

Detects speech bubbles, thought bubbles, and text regions:

```python
from backend.detector import DetectionService

service = DetectionService()
regions = await service.detect_regions(page_image)
# regions.regions contains BubbleRegion objects with x, y, width, height
```

**Supported Models:**
- **CRAFT** (default) — Character Region Awareness for Text Detection
- **DBNet** — Real-time Scene Text Detection
- **YOLO** — Bubble detection trained model

## Stage 2: OCR

Extracts Japanese text from each detected region:

```python
from backend.ocr import OCRService

service = OCRService()
for region in regions:
    text = await service.extract_text(page_image, (region.x, region.y, region.w, region.h))
```

**Supported Engines:**
- **MangaOCR** (default) — Specialized for Japanese manga text
- **PaddleOCR** — Multilingual OCR with good Japanese support
- **Tesseract** — Open-source OCR engine

## Stage 3: Translation

Translates extracted text to target language:

```python
from backend.translator import TranslationService

service = TranslationService()
result = await service.translate("おはよう", "ja", "en")
# result.translated_text = "Good morning"
```

**Supported Backends:**
- **OpenAI** — GPT-4o / GPT-4o-mini
- **Anthropic** — Claude 3 Haiku / Sonnet
- **Google** — Gemini Pro
- **DeepSeek** — DeepSeek Chat
- **Local** — Custom local models

## Stage 4: Inpainting

Removes original text from the page:

```python
from backend.inpainting import InpaintingService

service = InpaintingService()
result = await service.inpaint_batch(page_image, regions)
```

**Supported Models:**
- **LaMa** (default) — Large Mask Inpainting
- **SD Inpainting** — Stable Diffusion-based
- **OpenCV Fallback** — Telea/Navier-Stokes

## Stage 5: Rendering

Renders translated text into the cleaned bubbles:

```python
from backend.renderer import RenderService

service = RenderService()
result = await service.render_page(page_image, bubbles_with_text)
```

**Features:**
- Auto font-size fitting
- Text wrapping
- CJK character support
- Horizontal/Vertical centering
- Custom font support

## Full Pipeline Example

```python
from PIL import Image
from backend.detector import DetectionService
from backend.ocr import OCRService
from backend.translator import TranslationService
from backend.inpainting import InpaintingService
from backend.renderer import RenderService

async def translate_page(image_path: str) -> Image.Image:
    page = Image.open(image_path)

    # 1. Detect bubbles
    detector = DetectionService()
    detection = await detector.detect_regions(page)

    # 2. OCR each bubble
    ocr = OCRService()
    regions = [(r.x, r.y, r.width, r.height) for r in detection.regions]
    ocr_results = await ocr.extract_batch(page, regions)

    # 3. Translate text
    translator = TranslationService()
    bubble_data = []
    for bubble, ocr_result in zip(detection.regions, ocr_results):
        if not ocr_result.text.strip():
            continue
        translation = await translator.translate(ocr_result.text)
        bubble_data.append({
            "x": bubble.x, "y": bubble.y,
            "width": bubble.width, "height": bubble.height,
            "translated_text": translation.translated_text,
        })

    # 4. Inpaint original text
    inpainter = InpaintingService()
    inpainted = await inpainter.inpaint_batch(page, regions)

    # 5. Render translated text
    renderer = RenderService()
    result = await renderer.render_page(inpainted.image, bubble_data)

    return result.image
```
