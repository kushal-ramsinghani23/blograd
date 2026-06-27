<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0d1117,1a1a2e,0f3460&height=200&section=header&text=BlogRadar%20%F0%9F%A6%9E&fontSize=64&fontColor=00d4ff&fontAlignY=45&desc=AI-powered%20blog%20intelligence%20%7C%20scrape%20%C2%B7%20match%20%C2%B7%20rewrite&descAlignY=68&descColor=6b7280" />

<br/>

<p>
  <img src="https://img.shields.io/badge/Python-3.12-3776ab?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/LangGraph-Agent%20Graphs-ff6b35?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Groq-LLM-f55036?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Gemini-Vision-4285f4?style=for-the-badge&logo=google&logoColor=white"/>
  <img src="https://img.shields.io/badge/Electron.js-Frontend%20WIP-47848f?style=for-the-badge&logo=electron&logoColor=white"/>
</p>

<br/>

```
  ┌──────────────┐      ┌───────────────────┐      ┌────────────────────┐
  │  🌐 websites│─────►│  🤖 scraper agent │─────►│  📝 rewriteragent │
  │  + keywords  │      │  crawl · match    │      │  rewrite · image   │
  └──────────────┘      │  summarize        │      │  save draft        │
                        └───────────────────┘      └────────────────────┘
                                │                          │
                         matched articles             saved drafts
                                └──────────────────────────┘
                                          │
                                   Flask REST API
```

</div>

---

## 🦞 BlogRadar

BlogRadar is a two-agent AI pipeline that keeps tabs on the corners of the web you care about. Point it at a list of websites and keywords — the **scraper agent** crawls, matches, and summarises relevant articles; the **rewriter agent** takes your picks and rewrites them into publication-ready drafts, complete with a generated image. A Flask backend exposes everything as a clean REST API. An Electron frontend is in the works.

```
blograd/
├── backend/
│   ├── agents/             # LangGraph graphs — scraper + rewriter
│   ├── routes/             # Flask route handlers
│   ├── models/             # DB models
│   ├── run.py
│   └── requirements.txt
├── frontend/               # Electron.js — in progress
└── notes/                  # phase-by-phase build notes
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.12
- Node.js (for the Electron frontend, once it's up and running)
- A [Groq API key](https://console.groq.com) and a [Gemini API key](https://ai.google.dev)

### Backend Setup

```bash
# Clone the repo
git clone <your-repo-url>
cd blograd/backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file inside `backend/`:

```env
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

Run the server:

```bash
python3 run.py
```

The API will be available at `http://127.0.0.1:5000`.

### Frontend Setup *(in progress)*

```bash
cd frontend
npm install
npm start
```

> The Electron app is still being built — `npm start` currently launches a bare window with no UI wired up yet.

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` / `POST` / `DELETE` | `/websites` | Manage tracked websites |
| `GET` / `POST` / `DELETE` | `/keywords` | Manage keywords to match against |
| `GET` / `PATCH` / `DELETE` | `/drafts` | View, edit, or delete generated drafts |
| `POST` | `/agent/scrape` | Run the scraper agent — crawls, matches, and summarizes articles |
| `POST` | `/agent/rewrite` | Run the rewriter agent on selected articles — rewrites, generates an image, and saves a draft |

**Example — trigger a scrape:**

```bash
curl -X POST http://127.0.0.1:5000/agent/scrape
```

**Example — rewrite selected articles:**

```bash
curl -X POST http://127.0.0.1:5000/agent/rewrite \
  -H "Content-Type: application/json" \
  -d '{"selected_articles": [ { ...article object from /agent/scrape... } ]}'
```

---

## 🏗️ Architecture Highlights

- **Decoupled agents** — scraper and rewriter are independent LangGraph graphs with their own state, own endpoint, and own failure boundaries.

---

<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0d1117,1a1a2e,0f3460&height=120&section=footer&text=crawling%20the%20web%20so%20you%20don't%20have%20to&fontSize=14&fontColor=6b7280&fontAlignY=65" />

</div>
