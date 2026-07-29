# AI Manga Translator

> Production-ready manga translation system powered by AI — OCR, text detection, LLM translation, image inpainting, and rendering pipeline.

![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Next.js](https://img.shields.io/badge/Next.js-14-black)
![License](https://img.shields.io/badge/license-MIT-orange)

## 🚀 Features

- **📖 Manga Management** — Organize manga series, chapters, and pages
- **🔍 Text Detection** — Automatically detect speech bubbles and text regions using CRAFT, DBNet, or YOLO
- **📝 OCR Extraction** — Extract Japanese text using MangaOCR, PaddleOCR, or Tesseract
- **🌐 AI Translation** — Translate text using OpenAI, Anthropic Claude, Google Gemini, DeepSeek, or local models
- **🎨 Image Inpainting** — Remove original text with LaMa, Stable Diffusion, or OpenCV
- **✍️ Text Rendering** — Render translated text with auto-sizing, wrapping, and CJK support
- **⚡ Async Pipeline** — Background workers process multiple chapters concurrently
- **🔌 WebSocket Updates** — Real-time progress tracking for translation jobs
- **🖥️ Modern UI** — Next.js 14 with TypeScript, Tailwind CSS, and shadcn/ui

## 🏗️ Architecture

```
manga-translator/
├── backend/                  # Python FastAPI server
│   ├── api/                  # REST API routes
│   ├── config/               # Settings & logging
│   ├── database/             # SQLAlchemy async session
│   ├── detector/             # Text bubble detection
│   ├── inpainting/           # Image inpainting
│   ├── middleware/           # CORS & middleware
│   ├── models/               # SQLAlchemy ORM models
│   ├── ocr/                  # Optical character recognition
│   ├── renderer/             # Text rendering
│   ├── schemas/              # Pydantic request/response
│   ├── translator/           # LLM translation backends
│   └── workers/              # Async background workers
├── frontend/                 # Next.js TypeScript app
│   ├── src/
│   │   ├── app/              # App router pages
│   │   ├── components/       # UI components
│   │   ├── lib/              # API client & utilities
│   │   └── styles/           # Global CSS
│   └── Dockerfile
├── models/                   # ML model checkpoints
├── cache/                    # Cached translations
├── assets/fonts/             # Font files
├── logs/                     # Application logs
├── tests/                    # Test suite
├── docs/                     # Documentation
├── Dockerfile                # Backend Dockerfile
├── docker-compose.yml        # Full stack Docker compose
└── requirements.txt          # Python dependencies
```

## 🛠️ Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| **Python 3.13** | Core language |
| **FastAPI** | Web framework with async support |
| **Uvicorn** | ASGI server |
| **SQLAlchemy** | Async ORM with SQLite |
| **WebSocket** | Real-time progress updates |
| **OpenAI / Anthropic / etc.** | LLM translation backends |
| **MangaOCR / PaddleOCR** | Japanese text OCR |
| **OpenCV** | Image processing & inpainting |

### Frontend
| Technology | Purpose |
|---|---|
| **Next.js 14** | React framework |
| **TypeScript** | Type safety |
| **Tailwind CSS** | Utility-first styling |
| **shadcn/ui** | Accessible UI components |
| **Lucide React** | Icons |

## 🚦 Quick Start

### Prerequisites
- Python 3.13+
- Node.js 20+
- Docker (optional)

### Local Development

**1. Clone and setup backend:**

```bash
git clone <repository-url>
cd manga-translator

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

cp backend/.env.example .env
# Edit .env with your API keys
```

**2. Start the backend:**

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**3. Setup and start the frontend:**

```bash
cd frontend
npm install
npm run dev
```

**4. Open in browser:**
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/v1/health

### Docker Setup

```bash
# Build and start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop all services
docker compose down
```

## 📡 API Reference

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/manga` | List manga |
| `POST` | `/api/v1/manga` | Create manga |
| `GET` | `/api/v1/manga/{id}` | Get manga |
| `PUT` | `/api/v1/manga/{id}` | Update manga |
| `DELETE` | `/api/v1/manga/{id}` | Delete manga |
| `GET` | `/api/v1/manga/{id}/chapters` | List chapters |
| `POST` | `/api/v1/manga/{id}/chapters` | Create chapter |
| `POST` | `/api/v1/translate/text` | Translate text |
| `POST` | `/api/v1/translate/batch` | Batch translate |
| `POST` | `/api/v1/translate/jobs` | Create translation job |
| `GET` | `/api/v1/translate/jobs/{id}` | Get job status |
| `WS` | `/api/v1/ws/progress/{job_id}` | Real-time progress |

## 🔧 Configuration

Configuration is managed via environment variables in `.env`:

```env
# Server
HOST=0.0.0.0
PORT=8000
ENV=development
DEBUG=true

# Translation Backend
TRANSLATOR_BACKEND=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# OCR
OCR_ENGINE=manga_ocr
OCR_DEVICE=cpu

# Detector
DETECTOR_MODEL=craft

# Inpainting
INPAINTING_MODEL=lama
```

## 🧪 Testing

```bash
# Backend tests
pytest tests/backend/ -v

# With coverage
pytest tests/backend/ -v --cov=backend

# Frontend type check
cd frontend && npm run typecheck

# Linting
ruff check backend/
```

## 📁 Database

The project uses SQLite by default for local development:
- File: `backend/database/manga_translator.db`
- Tables created automatically on startup
- Alembic migration support (run `alembic init migrations` to set up)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- [MangaOCR](https://github.com/kha-white/manga-ocr) — Japanese text OCR
- [LaMa](https://github.com/advimman/lama) — Image inpainting
- [CRAFT](https://github.com/clovaai/CRAFT-pytorch) — Text detection
- [shadcn/ui](https://ui.shadcn.com/) — UI components
