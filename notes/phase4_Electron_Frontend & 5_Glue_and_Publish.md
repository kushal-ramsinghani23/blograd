# Phase 4 — Electron Frontend + Phase 5 — Glue & Publish

## Story

Phase 4 took BlogRadar from a backend-only API to a real desktop application. The challenge was learning Electron from scratch — a completely new paradigm where a desktop app is essentially a Node.js process managing a Chromium browser window. Phase 5 glued everything together: error handling, status checks, copy-to-clipboard publish hook, and the final end-to-end validation that confirmed the full pipeline works.

---

## Phase 4 — Electron Frontend

### Why Electron?

BlogRadar needs to:
- Run alongside a local Flask server on `localhost`
- Access the filesystem (images, drafts)
- Have a proper desktop UI with no browser tab

A regular website can't do this — browsers sandbox everything. Electron wraps a web UI (HTML/CSS/JS) inside a Node.js shell, giving you desktop-app power with web-dev familiarity.

---

### Core Concept — Two Processes

The single most important thing to understand about Electron:

| Process | Analogy | What it does |
|---|---|---|
| **Main process** | Kitchen | One per app. Full Node.js access. Creates windows, manages app lifecycle, talks to OS |
| **Renderer process** | Dining room | One per window. HTML/CSS/JS — exactly like a browser tab. What the user sees |

They never share memory — they communicate via **IPC (Inter-Process Communication)**, like a waiter passing orders between kitchen and dining room.

For BlogRadar, the renderer calls Flask directly (since we disabled `contextIsolation` for simplicity in dev). In production, the main process would handle all Flask calls and pass results to the renderer via IPC.

---

### Project Setup

```bash
cd frontend
npm init -y
npm install electron --save-dev
```

`package.json` — two critical things:
```json
{
  "main": "main.js",
  "scripts": {
    "start": "electron ."
  }
}
```

- `"main": "main.js"` — tells Electron where the main process entry point is
- `electron .` — run Electron in the current directory, it reads `main` from `package.json`

---

### `main.js` — Main Process

```javascript
const { app, BrowserWindow } = require('electron')

function createWindow() {
    const win = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false
        }
    })
    win.loadFile('index.html')
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
})
```

**Key points:**
- `app.whenReady()` — fires when Electron is initialized, then create the window
- `win.loadFile('index.html')` — loads the UI into the window
- `contextIsolation: false` — allows renderer to access Node.js APIs directly (fine for dev)
- `process.platform !== 'darwin'` — on macOS, apps stay open even when all windows are closed (Mac convention)

---

### `index.html` — The Full UI

**Stack used:**
- Tabler Icons (CDN) — clean icon library
- EasyMDE (CDN) — markdown editor with toolbar, preview, side-by-side
- Vanilla JS — no framework needed for this scale

**Pages:**
| Page | What it does |
|---|---|
| Dashboard | Metrics (websites, keywords, drafts count) + recent drafts |
| Websites | Add/delete tracked websites, talks to `GET/POST/DELETE /websites` |
| Keywords | Add/delete keywords, talks to `GET/POST/DELETE /keywords` |
| Drafts | List all drafts, click to open editor |
| Scrape | Trigger scraper, select articles, trigger rewriter |
| Editor | EasyMDE markdown editor, save via `PATCH /drafts/:id`, copy to clipboard |

**Navigation pattern** — single page app with `showPage()`:
```javascript
function showPage(name, el) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'))
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'))
  document.getElementById('page-' + name).classList.add('active')
  if (el) el.classList.add('active')
  // load data for the page
}
```

**Theme toggle** — CSS variables swapped by toggling a class on `:root`:
```javascript
function toggleTheme() {
  const isLight = document.documentElement.classList.toggle('light')
  document.getElementById('theme-icon').className = isLight ? 'ti ti-moon' : 'ti ti-sun'
  document.getElementById('theme-label').textContent = isLight ? 'Dark mode' : 'Light mode'
}
```
Light theme is warm sand/parchment (`#f0ece4`) — not white, easy on the eyes.

---

### Scrape → Select → Rewrite Flow

This is the key UX flow that ties the two agents together:

1. User clicks "Start scraping" → `POST /agent/scrape`
2. Results render as selectable checkbox cards showing URL, source, keywords, summary preview
3. User checks desired articles
4. "Rewrite selected" → `POST /agent/rewrite` with only checked articles
5. On success → auto-redirects to Drafts page

```javascript
async function rewriteSelected() {
  const selected = scrapedArticles.filter((_, i) => document.getElementById(`art-${i}`)?.checked)
  if (!selected.length) { alert('Select at least one article'); return }
  await fetch(`${API}/agent/rewrite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selected_articles: selected })
  })
  setTimeout(() => showPage('drafts', ...), 800)
}
```

---

### EasyMDE Editor

```javascript
easyMDE = new EasyMDE({
  element: document.getElementById('editor-content'),
  initialValue: draft.content || '',
  spellChecker: false,
  toolbar: ['bold','italic','heading','|','quote','unordered-list','ordered-list','|','link','|','preview','side-by-side','fullscreen'],
  minHeight: '420px'
})
```

**Key pattern** — destroy and recreate on each open:
```javascript
if (easyMDE) { easyMDE.toTextArea(); easyMDE = null }
easyMDE = new EasyMDE({...})
```
If you don't destroy first, opening a second draft stacks two editors on the same textarea.

---

## Phase 5 — Glue & Publish

### 1. Copy to Clipboard

Simplest publish hook — one line:
```javascript
async function copyDraft() {
  await navigator.clipboard.writeText(easyMDE.value())
  // show "Copied!" feedback briefly
}
```

### 2. Flask Status Check

Status pill in sidebar actually pings Flask every 30 seconds:

```javascript
async function checkFlaskStatus() {
  const dot = document.querySelector('.status-dot')
  const text = document.querySelector('.status-text')
  try {
    await fetch(`${API}/websites`)
    dot.style.background = '#3B6D11'
    text.textContent = 'Flask running on :5000'
  } catch(e) {
    dot.style.background = '#e24b4a'
    text.textContent = 'Flask offline'
  }
}

checkFlaskStatus()
setInterval(checkFlaskStatus, 30000)
```

### 3. Error Toasts

Every fetch wrapped in try/catch, failures show a toast bottom-right:

```javascript
function showToast(message, type = 'error') {
  const toast = document.createElement('div')
  toast.style.cssText = `position:fixed;bottom:24px;right:24px;padding:12px 18px;
    border-radius:var(--radius);font-size:13px;color:#fff;
    background:${type === 'error' ? '#e24b4a' : '#3B6D11'};z-index:9999;transition:opacity .3s`
  toast.textContent = message
  document.body.appendChild(toast)
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300) }, 3000)
}
```

Pattern used on every async function:
```javascript
async function loadWebsites() {
  try {
    const data = await fetch(`${API}/websites`).then(r => r.json())
    // update UI
  } catch(e) { showToast('Failed to load websites') }
}
```

---

## Commits

```
feat(frontend): add Electron main process with BrowserWindow setup
feat(frontend): add full UI with dashboard, websites, keywords, drafts, scrape pages and theme toggle
feat(frontend): add EasyMDE markdown editor for draft editing with save and status update
feat(frontend): add copy to clipboard button in draft editor
feat(frontend): add Flask connection status check with auto-refresh every 30s
feat(frontend): add error toast notifications for all API failures
chore(project): end-to-end validation complete — all phases working
```

---

## Key Things to Remember

- **Electron = Node.js shell + Chromium window.** Main process is Node, renderer is browser.
- **`electron .` reads `"main"` from `package.json`** — always set this correctly.
- **`app.whenReady().then(createWindow)`** — never create windows before app is ready.
- **CSS variables + class toggle = theme switching** — no JS needed to change individual colors.
- **EasyMDE must be destroyed before recreating** — `easyMDE.toTextArea()` then `null` before opening a new draft.
- **`navigator.clipboard.writeText()`** — async, always `await` it.
- **`setInterval` for health checks** — ping Flask every 30s, update UI based on response.
- **Toast pattern** — create DOM element, append, auto-remove after timeout. No library needed.

---

## v1.0 — What's Shipped

| Feature | Status |
|---|---|
| Flask backend + full CRUD | ✅ |
| Scraper agent (LangGraph) | ✅ |
| Rewriter agent (LangGraph) | ✅ |
| Electron desktop app | ✅ |
| Dashboard with metrics | ✅ |
| Website + keyword manager | ✅ |
| Scrape → select → rewrite flow | ✅ |
| Markdown draft editor | ✅ |
| Copy to clipboard | ✅ |
| Flask status check | ✅ |
| Error toasts | ✅ |
| Theme toggle | ✅ |

---

## Post v1.0 — Deferred

- `@tool` pattern — let LLM decide when to call tools
- Dedup memory — prevent rewriting same article twice
- Scheduler — auto-scrape on a cron
- Publish webhook — push draft directly to a CMS
- Better image generation — once Gemini quota sorted
