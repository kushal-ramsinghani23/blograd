# Phase 3 — Rewriter Agent

## Story

Phase 3 is where BlogRadar became a real content pipeline. The scraper could find and summarize articles — but that was just research. Phase 3 added the writer: an agent that takes those summaries, rewrites them as original blog posts, generates a hero image, and saves them as drafts ready for publishing.

The key architectural decision of this phase was keeping the rewriter as a **separate agent with its own endpoint**, giving the user control over what gets rewritten — not just blindly processing everything the scraper found.

---

## Architecture Decision — Separate Endpoint

### The question
After the scraper returns `matched_articles`, how should the rewriter be triggered?

| Option | How it works | Problem |
|--------|-------------|---------|
| Same endpoint | Scraper runs → rewriter runs automatically → drafts saved | No checkpoint. If rewriter crashes, scraper results are lost. User never sees what was scraped. |
| Separate endpoint | Scraper returns results → user reviews → calls rewriter with selected articles | Each agent is isolated. Failures don't cascade. User has control. |

### The real-world analogy
Think of a researcher and a writer working together:
- **Option 1**: You tell the researcher "go find articles AND immediately hand them to the writer." You wait. If the writer crashes, you've lost everything.
- **Option 2**: The researcher brings articles to **you** first. You review them. You pick the best 3 out of 10. You hand only those to the writer.

Option 2 enables a product feature that Option 1 simply cannot: **the user selects which articles to rewrite.**

### Why this matters
- Saves LLM calls — no point rewriting garbage articles
- Scraper results are safe regardless of rewriter failures
- Each agent is independently retryable
- No single long blocking HTTP request

### Decision
`POST /agent/rewrite` — separate endpoint. Frontend calls scraper first, shows results to user, user selects articles, then calls rewriter.

---

## State Design

### Analogy
Just like the scraper used `pending_urls` as a queue — popping one URL at a time, processing it, moving to the next — the rewriter uses `pending_articles` as a queue of articles to rewrite.

### Why two article state types?

`ArticleState` = what comes **in** from the scraper (raw scraped data)
`RewrittenArticleState` = what comes **out** of the rewriter (blog post data)

These have different shapes so they need different TypedDicts. Reusing `ArticleState` for rewritten content would be wrong — a rewritten article has a `title`, `content`, and `featured_image_url`, not a `text` or `source_site`.

```python
from typing import TypedDict, List

class ArticleState(TypedDict):
    url: str
    text: str
    source_site: str
    matched_keywords: List[str]
    summary: str

class RewrittenArticleState(TypedDict):
    title: str
    content: str
    featured_image_url: str
    source_url: str
    matched_keywords: List[str]

class RewriterState(TypedDict):
    pending_articles: List[ArticleState]      # queue — pop from front each loop
    current_article: ArticleState             # article being processed right now
    current_rewritten: RewrittenArticleState  # rewrite in progress
    rewritten_articles: List[RewrittenArticleState]  # completed rewrites
```

### Key insight — `matched_articles` → `pending_articles`
The scraper called it `matched_articles`. The rewriter calls it `pending_articles`. Same data, different name — because in the rewriter's context, these are articles **pending processing**, and we pop from the front each loop iteration. The name reflects the intent.

---

## Graph Design

### Nodes

```
rewrite_article → generate_image → save_draft → (loop or end)
```

| Node | Responsibility |
|------|---------------|
| `rewrite_article` | Pop next article, call Groq, produce title + content |
| `generate_image` | Call Gemini image API, save PNG, store path |
| `save_draft` | Save `Draft` record to DB, append to `rewritten_articles` |

### Conditional edge — the loop

```
START → rewrite_article → generate_image → save_draft
              ↑                                  |
              |__________ continue _______________|
                                                  |
                                                end
                                                  ↓
                                                 END
```

```python
def router_function(state: RewriterState):
    if state["pending_articles"]:
        return "continue"
    return "end"
```

If `pending_articles` still has items → loop back to `rewrite_article`.
If empty → go to END.

---

## Node Implementation

### `rewrite_article`

**Key pattern — structured LLM output:**
Always tell the LLM the exact format you want back so parsing is reliable.

```python
def rewrite_article(state: RewriterState) -> RewriterState:
    article = state["pending_articles"][0]
    remaining = state["pending_articles"][1:]

    llm = ChatGroq(model="llama-3.3-70b-versatile")

    prompt = f"""You are a blog writer. Rewrite the following article in the same style and tone as the source.

Summary: {article['summary']}

Return your response in EXACTLY this format:
TITLE: <title here>
CONTENT: <full rewritten article here>"""

    response = llm.invoke(prompt)
    text = response.content

    lines = text.split("\n")
    title = lines[0].replace("TITLE:", "").strip()
    content = "\n".join(lines[1:]).replace("CONTENT:", "").strip()

    rewritten = RewrittenArticleState(
        title=title,
        content=content,
        featured_image_url="",
        source_url=article["url"],
        matched_keywords=article["matched_keywords"]
    )

    return {
        "pending_articles": remaining,
        "current_article": article,
        "current_rewritten": rewritten
    }
```

**Why use only `summary` and not `text`?**
The scraper's `summarize_articles` node already extracts `SUMMARY`, `STYLE`, and `KEY POINTS` from the full article text. Passing the full `text` to the rewriter is redundant and hits Groq's token limit (413 error). The summary is a distilled version — everything the rewriter needs.

**Why not return `rewritten_articles` here?**
In LangGraph, fields you don't return stay unchanged in state. `rewritten_articles` is only updated in `save_draft` after the image is generated. No need to carry it through every node.

### `generate_image`

**How the Gemini image API works:**
Unlike APIs that return a URL, Gemini returns the image as raw base64 bytes (`inline_data`) inside a `parts` list. The response can contain mixed content — text captions and image data — so you loop through parts and handle each type.

```python
for part in response.parts:
    if part.inline_data is not None:  # this is the image
        image = part.as_image()       # convert to PIL Image
        image.save(image_path)        # save to disk yourself
        break
```

**Full node with fallback:**

```python
def generate_image(state: RewriterState):
    title = state["current_rewritten"]["title"]
    image_path = "static/images/default.png"  # fallback

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=f"Blog hero image for: {title}"
        )

        filename = title.lower().replace(" ", "_")[:50]
        generated_path = f"static/images/{filename}.png"

        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()
                image.save(generated_path)
                image_path = generated_path
                break

    except Exception as e:
        print(f"Image generation failed: {e}, using default image")

    updated_rewritten = {
        **state["current_rewritten"],
        "featured_image_url": image_path
    }

    return {"current_rewritten": updated_rewritten}
```

**Why `try/except Exception`?**
Catches everything — quota errors, model not found, network failures. The rewriter should never crash because image generation failed. A default image is always better than a broken pipeline.

**The `**` spread pattern:**
```python
updated_rewritten = {
    **state["current_rewritten"],  # copy all existing fields
    "featured_image_url": image_path  # override just this one
}
```
Never mutate state directly. Always build a new object.

### `save_draft`

```python
def save_draft(state: RewriterState):
    rewritten = state["current_rewritten"]

    draft = Draft(
        title=rewritten["title"],
        content=rewritten["content"],
        image_path=rewritten["featured_image_url"],
        source_url=rewritten["source_url"],
        matched_keywords=",".join(rewritten["matched_keywords"]),
        status="draft",
    )

    db.session.add(draft)
    db.session.commit()

    return {
        "rewritten_articles": state["rewritten_articles"] + [rewritten]
    }
```

**Why `",".join(matched_keywords)`?**
The `Draft` model stores `matched_keywords` as a `str` column, not a list. Python lists can't go into SQLite directly. Join them as a comma-separated string on save; split them back on read.

---

## Flask Endpoint

```python
@agent_bp.route("/agent/rewrite", methods=["POST"])
def rewrite_agent():
    graph = create_rewriter_graph()

    data = request.get_json()
    selected_articles = data.get("selected_articles", [])

    final_state = graph.invoke(
        {
            "pending_articles": selected_articles,
            "current_article": {},
            "current_rewritten": {},
            "rewritten_articles": [],
        },
        config={"configurable": {"thread_id": "rewriter-main"}}
    )

    return jsonify(final_state["rewritten_articles"]), 200
```

**Flow:**
1. Frontend calls `POST /agent/scrape` — gets `matched_articles`
2. User reviews, selects articles
3. Frontend calls `POST /agent/rewrite` with `{ "selected_articles": [...] }`
4. Graph runs, drafts saved to DB
5. Returns `rewritten_articles` as JSON

---

## Errors Encountered & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| Groq 413 — request too large | Passing full `article['text']` (~15k tokens) to Groq | Use only `article['summary']` — already distilled |
| Gemini 404 — model not found | Wrong model name `gemini-2.0-flash-exp-image-generation` | Correct name: `gemini-3.1-flash-image-preview` |
| Gemini 429 — quota exhausted | Free tier daily limit hit | Added `try/except` fallback to `default.png` |

---

## Your Mistakes & What They Teach

**1. Mutating state directly**
```python
# WRONG
state["current_rewritten"]["featured_image_url"] = "path"

# RIGHT
updated = {**state["current_rewritten"], "featured_image_url": "path"}
```
LangGraph state should never be mutated in place. Always return a new object.

**2. `updated_rewritten` assignment bug**
```python
# WRONG — this assigns the string "path", not the dict
updated_rewritten = state["current_rewritten"]["featured_image_url"] = "path"

# RIGHT — build a new dict explicitly
updated_rewritten = {**state["current_rewritten"], "featured_image_url": "path"}
```

**3. Hardcoded image path**
Using `"static/images/image.png"` for every article means each new image overwrites the previous one. Use the article title to generate a unique filename.

**4. Over-engineered image prompt**
Long instructions to the image model hurt more than help. For image generation, simple and descriptive is better: `"Blog hero image for: {title}"`.

**5. Redundant `article_url` field in state**
Initially added both `article_url: str` and `current_article: ArticleState` to `RewriterState`. Since `ArticleState` already has a `url` field, `article_url` was redundant. Keep state lean — no duplicate data.

---

## Key Things to Remember

- **Separate endpoints = isolated failures.** Scraper and rewriter can fail independently without affecting each other.
- **The Groq call pattern:** `llm.invoke(prompt)` → `response.content`. That's it.
- **The Gemini image pattern:** response comes as `parts` list → loop → check `inline_data` → `as_image()` → `.save()`.
- **Always tell the LLM the exact output format** — `TITLE: ... CONTENT: ...` makes parsing reliable.
- **`try/except Exception` for external APIs** — quota errors, rate limits, model changes. Never let image generation crash your pipeline.
- **`**spread` pattern** for updating nested state objects without mutation.
- **LangGraph partial returns** — only return fields you're changing. Everything else stays as-is.
- **`matched_keywords` is a list in Python, a string in SQLite** — always `.join()` on save.

---

## Decisions Deferred to Post v1.0

- `@tool` pattern — letting the LLM decide when to call tools instead of hardcoded node sequence
- Dedup memory — preventing the same article from being rewritten across multiple scraper runs

---

## Commits

```
feat(agents): add rewriter agent with LangGraph pipeline

- add rewriter_agent.py with LangGraph graph and MemorySaver checkpointer
- rewrite matched articles using Groq Llama 3.3 70B
- generate hero images via Gemini image generation API
- save rewritten articles as Draft records to SQLite DB
- add POST /agent/rewrite endpoint to trigger rewriter with selected articles
```

```
fix(agents): fix matched_keywords list-to-string conversion for DB compatibility and add static/images directory init
```

```
fix(agents): add image generation fallback to default on API failure
```

```
chore(static): add default placeholder image for blog hero fallback
```