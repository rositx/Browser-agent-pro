# Browser-Agent-Pro

**Production-grade autonomous browser agent** built with Playwright, stealth anti-detection, and dual-LLM orchestration.

## Overview

Browser-Agent-Pro is an intelligent browser automation system that can:
- Navigate websites with human-like behaviour
- Fill forms using vector-stored profile data
- Generate and upload tailored documents
- Self-correct on failures with AX tree diffing
- Enforce safety gates on sensitive actions

## Tech Stack

| Layer | Technology |
|---|---|
| Browser Runtime | Playwright (Async) + playwright-stealth |
| Configuration | Pydantic Settings + python-dotenv |
| AI / LLM | Anthropic (Claude) + OpenAI (GPT-4o) |
| Vector Store | ChromaDB |
| Visual Processing | Pillow + OpenCV |
| Document Generation | Jinja2 + WeasyPrint |
| Task Queue | Celery + Redis |
| Logging | Loguru (JSONL) |

## Project Structure

```
Browser-agent-pro/
├── agent/
│   ├── core/
│   │   ├── config.py       # Pydantic Settings configuration
│   │   ├── browser.py      # Playwright runtime & stealth engine
│   │   ├── session.py      # Manifest parser & session state
│   │   ├── driver.py       # Action dispatcher with stealth timing
│   │   ├── parser.py       # AX tree & visual overlay (Phase 2)
│   │   ├── brain.py        # Dual-LLM orchestrator (Phase 2)
│   │   └── corrector.py    # Self-correction loop (Phase 3)
│   ├── storage/
│   │   ├── schema.py       # Pydantic action schemas (Phase 2)
│   │   ├── knowledge.py    # ChromaDB vector store (Phase 2)
│   │   └── cache.py        # SQLite selector cache (Phase 3)
│   └── utils/
│       ├── document.py     # PDF generation (Phase 3)
│       └── logger.py       # Structured logging (Phase 3)
├── manifests/               # Task manifest JSON files
├── profiles/                # Persistent browser profiles
├── tests/                   # Pytest test suite
├── main.py                  # CLI entrypoint
└── requirements.txt         # Python dependencies
```

## Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/YOUR_USERNAME/Browser-agent-pro.git
cd Browser-agent-pro
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your API keys (required for Phase 2+)
```

### 3. Run
```bash
python main.py --manifest manifests/example_manifest.json
python main.py --manifest manifests/example_manifest.json --headless
```

### 4. Test
```bash
pytest tests/ -v
```

## Development Phases

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Foundation, Runtime & Browser Stealth | 🚧 In Progress |
| Phase 2 | Perception, Brain & Vector Store | ⏳ Pending |
| Phase 3 | Resilience, Self-Correction & Production | ⏳ Pending |

## License

Private — All rights reserved.
