# Setup Guide

## Local Development Setup

### Backend Setup

1. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp backend/.env.example .env
   ```
   Edit `.env` to add your API keys.

4. **Start the server**
   ```bash
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Frontend Setup

1. **Install dependencies**
   ```bash
   cd frontend
   npm install
   ```

2. **Start development server**
   ```bash
   npm run dev
   ```

3. **Build for production**
   ```bash
   npm run build
   npm start
   ```

## Docker Setup

```bash
# Build and start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

## Getting API Keys

### OpenAI
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Set `OPENAI_API_KEY` in `.env`

### Anthropic Claude
1. Go to https://console.anthropic.com/
2. Create an API key
3. Set `ANTHROPIC_API_KEY` in `.env`

### DeepSeek
1. Go to https://platform.deepseek.com/
2. Create an API key
3. Set `DEEPSEEK_API_KEY` in `.env`
