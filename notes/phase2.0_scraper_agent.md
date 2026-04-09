# Phase 2 — Scraper Agent: LangChain, LangGraph & BeautifulSoup

---

## The Story

The Flask backend is solid — it stores websites, keywords, and drafts. But right now it's just a passive data store. Nothing actually *does* anything with that data.

Phase 2 is where the project comes alive. We build the intelligence — a stateful agent that reads websites from the DB, scrapes their blogs, matches articles against keywords, and hands relevant content to the rewriter.

Think of Phase 2 as hiring the first employee for your content team. This employee:
- Knows which websites to watch (from DB)
- Knows what topics matter (keywords from DB)
- Goes out and reads the web every day
- Remembers what they've already read (dedup)
- Flags relevant articles for your review

We are at: **Day 4–7. LangGraph scraper agent is running end-to-end, scraping real websites, matching keywords, and returning structured article data.**

---

## 1. LangChain vs LangGraph — What's the Difference?

### LangChain
A framework that makes it easier to build LLM-powered applications. Instead of manually calling APIs, parsing responses, and chaining steps together, LangChain gives you building blocks.

Without LangChain:
```python
response = openai.chat(prompt)
text = response.choices[0].message.content
result = my_parser(text)
next_response = openai.chat(result)
# ... painful plumbing
```

With LangChain — you define steps declaratively and it handles the wiring.

**A "chain"** = a sequence of steps where the output of step 1 becomes the input of step 2. Like a pipeline.

### LangGraph
Built on top of LangChain. Solves a problem that linear chains can't handle:

> What if your workflow isn't a straight line? What if it needs to loop, branch, and remember what happened in previous runs?

LangGraph models agent workflows as **graphs** — nodes connected by edges, with loops, conditionals, and persistent state.

**Analogy:** LangChain is a conveyor belt (linear). LangGraph is a factory floor (any machine can route to any other, and the factory remembers its state between shifts).

---

## 2. State — The Baton in the Relay Race

### What is State?
State is the **shared memory** that gets passed between every node in the graph. Think of it as a baton in a relay race — each runner (node) picks it up, adds their result, and passes it to the next runner.

Every node:
1. Reads from state
2. Does its work
3. Returns **only the fields that changed** (not the entire state)
4. LangGraph merges those changes back automatically

### How is State defined?
Using Python's `TypedDict` — a class-level dictionary with type hints. It's like defining the "schema" of your shared memory.

```python
from typing import TypedDict, List

class ScraperState(TypedDict):
    websites: List[str]        # URLs to scrape (loaded from DB)
    keywords: List[str]        # Keywords to match (loaded from DB)
    pending_urls: List[str]    # URLs found but not yet scraped
    scraped_urls: List[str]    # URLs already processed (dedup store)
    current_article: ArticleState   # Article being processed right now
    matched_articles: List[ArticleState]  # Articles that passed keyword match
```

### Why a separate ArticleState?
`current_article` is complex — it has multiple fields. Instead of using a plain `dict` (vague), we define exactly what an article contains:

```python
class ArticleState(TypedDict):
    url: str                        # Where the article came from
    text: str                       # Full scraped text
    source_site: str                # Domain (e.g. "hashnode.com")
    matched_keywords: List[str]     # Which keywords matched
```

### Accessing State
State is just a dict. Access it like one:

```python
def some_node(state: ScraperState):
    websites = state["websites"]      # get all websites
    first_url = state["pending_urls"][0]  # get first pending URL
    keywords = state["keywords"]      # get keywords
```

---

## 3. Nodes — Where the Work Happens

### What is a Node?
A LangGraph node is just a Python function. It takes state, does something, and returns a dict of only the fields that changed.

```python
def node_name(state: ScraperState) -> dict:
    # read from state
    websites = state["websites"]
    
    # do work...
    result = do_something(websites)
    
    # return ONLY what changed
    return {"websites": result}
```

LangGraph automatically merges the returned dict into the existing state. You never return the full state.

### Our 5 Nodes

```
fetch_websites_and_keywords  →  crawl_blog_index  →  check_dedup  →  scrape_article  →  match_keywords
        (load from DB)              (find links)        (filter)        (get text)       (check keywords)
```

**Node 1: fetch_websites_and_keywords**
```python
def fetch_websites_and_keywords(state: ScraperState):
    websites = [w.url for w in Website.query.all()]
    keywords = [k.word for k in Keyword.query.all()]
    return {"websites": websites, "keywords": keywords}
```

**Node 2: crawl_blog_index**
- Uses BeautifulSoup to find all links on each website
- Filters to same-domain only (no Twitter, LinkedIn noise)
- Uses `set()` to deduplicate links found on the same page
```python
def crawl_blog_index(state: ScraperState):
    pending_urls = set()
    for url in state["websites"]:
        try:
            response = requests.get(url, timeout=10)
        except Exception:
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        site_domain = urlparse(url).netloc
        for link in soup.find_all("a"):
            href = link.get("href")
            if href and href.startswith("http"):
                if urlparse(href).netloc == site_domain:
                    pending_urls.add(href)
    return {"pending_urls": list(pending_urls)}
```

**Node 3: check_dedup**
- Filters out URLs already in `scraped_urls`
- This runs every loop iteration (not just once at the start!)
```python
def check_dedup(state: ScraperState):
    updated = [url for url in state["pending_urls"]
               if url not in state["scraped_urls"]]
    return {"pending_urls": updated}
```

**Node 4: scrape_article**
- Takes `pending_urls[0]` (first unprocessed URL)
- Fetches HTML, extracts text with BeautifulSoup
- Moves URL from `pending_urls` to `scraped_urls`
```python
def scrape_article(state: ScraperState):
    pending_urls = state["pending_urls"]
    scraped_urls = state["scraped_urls"]
    try:
        response = requests.get(pending_urls[0], timeout=10)
    except Exception:
        return {
            "pending_urls": pending_urls[1:],
            "scraped_urls": scraped_urls + [pending_urls[0]],
        }
    soup = BeautifulSoup(response.text, "html.parser")
    current_article: ArticleState = {
        "url": pending_urls[0],
        "text": soup.get_text(),
        "source_site": urlparse(pending_urls[0]).netloc,
        "matched_keywords": []
    }
    return {
        "pending_urls": pending_urls[1:],
        "scraped_urls": scraped_urls + [pending_urls[0]],
        "current_article": current_article,
    }
```

**Node 5: match_keywords**
- Checks if any keyword appears in the article text
- If yes → adds to `matched_articles`
- If no → returns `{}` (no state change)
```python
def match_keywords(state: ScraperState):
    current_article = state["current_article"]
    keywords = state["keywords"]
    keywords_present = [k for k in keywords if k in current_article["text"]]
    if keywords_present:
        updated_article = {**current_article, "matched_keywords": keywords_present}
        return {
            "current_article": updated_article,
            "matched_articles": state["matched_articles"] + [updated_article],
        }
    return {}
```

---

## 4. Edges — Where to Go Next

### Normal Edges
```python
builder.add_edge(START, "fetch_websites_and_keywords")
builder.add_edge("fetch_websites_and_keywords", "crawl_blog_index")
builder.add_edge("crawl_blog_index", "check_dedup")
builder.add_edge("check_dedup", "scrape_article")
builder.add_edge("scrape_article", "match_keywords")
```

### Conditional Edges — The Loop
After `match_keywords`, we need to decide: are there more URLs to scrape, or are we done?

```python
def router_function(state: ScraperState):
    if state["pending_urls"]:
        return "continue"   # loop back
    return "end"            # we're done

builder.add_conditional_edges(
    "match_keywords",
    router_function,
    {"continue": "check_dedup", "end": END}
)
```

**Why loop back to `check_dedup` not `scrape_article`?**
Because without going through `check_dedup` every iteration, we'd re-scrape URLs we already processed. The dedup filter must run on every loop.

```
START → fetch → crawl → check_dedup → scrape → match
                             ↑                    |
                             |____ continue ______|
                                        ↓
                                       END (when pending_urls empty)
```

---

## 5. Super-Steps — How LangGraph Executes

LangGraph uses a **message-passing** model inspired by Google's Pregel system. Execution proceeds in discrete rounds called **super-steps**.

### Node States
At any point in time, every node is in one of three states:

| State | Meaning |
|---|---|
| **Inactive** | Waiting — no message received yet. Node is idle. |
| **Active** | Running — received a message, currently executing its function. |
| **Halted** | Done — voted to stop. No more incoming messages for this node. |

### How a Super-Step Works
1. At the **start of a super-step**, all nodes that received a message in the previous step become **active**
2. Each active node runs its function, updates state, and **sends a message** along its outgoing edge(s)
3. At the **end of the super-step**, nodes that received no new messages vote to **halt**
4. The graph **terminates** when: all nodes are halted AND no messages are in transit

### Super-Steps in Our Scraper Graph

```
Initial state: all nodes INACTIVE, no messages

Super-step 1:
  fetch_websites_and_keywords → ACTIVE (received START message)
  crawl, check_dedup, scrape, match → INACTIVE
  → fetch runs, sends message to crawl
  → fetch HALTS

Super-step 2:
  crawl_blog_index → ACTIVE (received message from fetch)
  fetch → HALTED
  check_dedup, scrape, match → INACTIVE
  → crawl runs, finds all links, sends message to check_dedup
  → crawl HALTS

Super-step 3:
  check_dedup → ACTIVE
  → filters pending_urls, sends message to scrape_article
  → check_dedup HALTS

Super-step 4:
  scrape_article → ACTIVE
  → scrapes pending_urls[0], builds current_article
  → sends message to match_keywords
  → scrape HALTS

Super-step 5:
  match_keywords → ACTIVE
  → checks keywords, adds to matched_articles
  → router returns "continue" → sends message BACK to check_dedup
  → match HALTS

Super-step 6:
  check_dedup → ACTIVE again (new message arrived)
  → loop continues for next URL...

Super-step N:
  match_keywords → ACTIVE
  → router returns "end" → sends message to END
  → ALL nodes HALTED, no messages in transit → GRAPH TERMINATES
```

**Key rule:** A node only activates when it receives a message. A node halts when it has no more incoming messages. The graph only terminates when BOTH conditions are true simultaneously — all nodes halted AND the message queue is empty.

> Visual reference of Graph → Super-steps → Checkpoints → Thread → StateSnapshot hierarchy:
>
> *(See diagram: Graph passes state through nodes via super-steps. Each super-step produces a Checkpoint (StateSnapshot). All checkpoints from a single run are grouped into a Thread.)*

---

## 6. Persistence — "Remember What You Scraped Yesterday"

### The Problem
The scheduler runs the scraper every day. On Day 1 it scrapes 50 articles. On Day 2, it should skip those 50 and only process new ones.

But if the server restarts between runs, everything in memory is wiped. `scraped_urls` is empty again — Day 2 re-scrapes everything.

### The Solution: Checkpointer
A checkpointer saves a **snapshot of graph state** at every super-step, organized into **threads**.

```
Run 1 (Day 1):
  Thread "scraper-main" → saves state after each super-step
  scraped_urls = ["url1", "url2", ..., "url50"]

Server restarts...

Run 2 (Day 2):
  Thread "scraper-main" → loads last saved state
  scraped_urls = ["url1", "url2", ..., "url50"]  ← still there!
  check_dedup filters all 50 out → only new URLs get scraped
```

**Checkpointer types:**
- `MemorySaver` — in-memory, lost on restart. Good for dev.
- `SqliteSaver` — persists to a `.db` file. Good for production.

We use `MemorySaver` for now (SqliteSaver had a context manager issue with the version we installed):

```python
from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)
```

### What is a Thread?
A thread is a unique session identifier for your graph. More precisely — **a thread is the chronological accumulation of all checkpoints (StateSnapshots) produced across every super-step of a graph run**, organized under a single `thread_id`.

Think of it like a Git commit history — each checkpoint is a commit, and the thread is the branch that holds all of them in sequence.

- Same `thread_id` every run → loads the most recent checkpoint → state persists across days
- Different `thread_id` each run → starts fresh → no memory

```python
graph.invoke(
    {"websites": [], "keywords": [], ...},
    config={"configurable": {"thread_id": "scraper-main"}}
    #                                       ↑
    #   Always the same ID → loads previous thread → dedup works across runs
)
```

**Thread → Checkpoints relationship:**
```
Thread "scraper-main"
├── Checkpoint at super-step 1  (StateSnapshot: websites loaded)
├── Checkpoint at super-step 2  (StateSnapshot: pending_urls found)
├── Checkpoint at super-step 3  (StateSnapshot: dedup filtered)
├── Checkpoint at super-step 4  (StateSnapshot: article scraped)
├── Checkpoint at super-step 5  (StateSnapshot: article matched)
│   ... loop repeats ...
└── Checkpoint at super-step N  (StateSnapshot: final, all URLs processed)
```

### Checkpoint = State Snapshot
A checkpoint is the state of a thread at a particular super-step. Represented as a `StateSnapshot` object. Enables:
- **Memory** — remember scraped URLs across runs
- **Fault tolerance** — resume from last successful step if a node crashes
- **Time travel** — debug by replaying from any checkpoint
- **Human-in-the-loop** — pause and wait for human input between steps

![persistence flow](https://mintcdn.com/langchain-5e9cc07a/-_xGPoyjhyiDWTPJ/oss/images/checkpoints.jpg?fit=max&auto=format&n=-_xGPoyjhyiDWTPJ&q=85&s=966566aaae853ed4d240c2d0d067467c)
---

## 7. StateGraph vs compile() — Blueprint vs Building

### StateGraph — The Blueprint
`StateGraph` is the **architect's blueprint**. You use it to describe the structure of your graph — what nodes exist, how they connect, what state schema they share. Nothing actually runs yet. It's just a definition.

```python
builder = StateGraph(ScraperState)   # blueprint parameterized by state schema
builder.add_node(...)                # add rooms to the blueprint
builder.add_edge(...)                # add corridors between rooms
```

**Analogy:** `StateGraph` is like a building blueprint. It describes what the building will look like, but you can't live in it yet.

### compile() — The Actual Building
`compile()` takes the blueprint and **constructs the executable graph**. This is where:
1. The graph structure is validated (missing edges, orphan nodes, etc. are caught here)
2. The checkpointer is attached
3. The runnable object is returned — something you can actually call `.invoke()` on

```python
graph = builder.compile(checkpointer=memory)
# Now graph is a live, runnable object
```

**Analogy:** `compile()` is the construction crew that builds the actual building from the blueprint. After this, you can move in and use it.

```python
def create_scraper_graph():
    builder = StateGraph(ScraperState)

    # Add nodes
    builder.add_node("fetch_websites_and_keywords", fetch_websites_and_keywords)
    builder.add_node("crawl_blog_index", crawl_blog_index)
    builder.add_node("check_dedup", check_dedup)
    builder.add_node("scrape_article", scrape_article)
    builder.add_node("match_keywords", match_keywords)

    # Add edges
    builder.add_edge(START, "fetch_websites_and_keywords")
    builder.add_edge("fetch_websites_and_keywords", "crawl_blog_index")
    builder.add_edge("crawl_blog_index", "check_dedup")
    builder.add_edge("check_dedup", "scrape_article")
    builder.add_edge("scrape_article", "match_keywords")

    # Conditional edge (the loop)
    builder.add_conditional_edges(
        "match_keywords",
        router_function,
        {"continue": "check_dedup", "end": END}
    )

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)  # build it, attach memory
```

**Why wrap in a function?** If graph building happens at module level, it executes the moment anyone imports the file — even if they just need `ScraperState`. Wrapping in `create_scraper_graph()` means the graph is only built when explicitly called, keeping imports clean and fast.

---

## 8. Invoking the Graph — `.invoke()`

`.invoke()` is how you actually **run** the compiled graph. It blocks until the graph terminates and returns the final state.

```python
final_state = graph.invoke(
    # Argument 1: Initial state
    # Every field in ScraperState needs an initial value here.
    # Nodes will fill them in as the graph runs.
    {
        "websites": [],           # empty — fetch_websites_and_keywords fills this
        "keywords": [],           # empty — fetch_websites_and_keywords fills this
        "pending_urls": [],       # empty — crawl_blog_index fills this
        "scraped_urls": [],       # empty — grows as articles are scraped
        "current_article": {},    # empty — scrape_article fills this each loop
        "matched_articles": []    # empty — match_keywords adds to this
    },
    # Argument 2: Runtime config
    # thread_id ties this invocation to a specific checkpoint thread.
    # Using the same thread_id every time loads the previous run's state.
    config={"configurable": {"thread_id": "scraper-main"}}
)

# .invoke() returns the COMPLETE final state after the graph terminates
matched = final_state["matched_articles"]   # this is what we return to the frontend
```

### `.invoke()` Arguments Reference

| Argument | Type | Purpose | Our usage |
|---|---|---|---|
| `input` (1st arg) | `dict` | Initial values for every state field. Nodes update these as they run. | Empty lists — let the nodes populate from DB |
| `config` (2nd arg) | `dict` | Runtime configuration passed to every node and the checkpointer | `thread_id: "scraper-main"` — persistent memory |
| `config.thread_id` | `str` | Identifies which checkpoint thread to load/save state to | Always `"scraper-main"` so dedup persists across days |

### What `.invoke()` returns
The **final state dict** — the complete `ScraperState` after all nodes have run and the graph has terminated. You access individual fields like a regular dict:

```python
final_state["matched_articles"]   # list of ArticleState dicts
final_state["scraped_urls"]       # all URLs processed in this run
final_state["websites"]           # websites that were scraped
```

---

## 9. BeautifulSoup — Web Scraping

### What it is
BeautifulSoup is a Python library for parsing HTML. You give it raw HTML, it gives you a clean, navigable tree. It never fetches pages itself — it only parses. The `requests` library handles the fetching.

### Fetching HTML
```python
import requests
from bs4 import BeautifulSoup

response = requests.get("https://hashnode.com", timeout=10)
html_doc = response.text  # raw HTML string

soup = BeautifulSoup(html_doc, "html.parser")
```

### Extracting all links
```python
for link in soup.find_all("a"):       # find all <a> tags
    href = link.get("href")           # get the href attribute
    if href and href.startswith("http"):
        print(href)
```

### Extracting all text (no HTML tags)
```python
text = soup.get_text()   # strips all HTML, returns plain text
```

### Domain filtering with urlparse
```python
from urllib.parse import urlparse

site_domain = urlparse("https://hashnode.com/blog").netloc
# site_domain = "hashnode.com"

link_domain = urlparse("https://twitter.com/hashnode").netloc
# link_domain = "twitter.com"

if link_domain == site_domain:
    # keep it — same domain
```

---

## 10. The Flask Endpoint — Wiring the Agent to the API

The scraper agent is a self-contained Python module. To make it accessible from the outside world (frontend, scheduler), we expose it as a Flask route.

```python
# app/routes/agent.py
from flask import Blueprint, jsonify
from ..agents.scraper_agent import create_scraper_graph

agent_bp = Blueprint("agent", __name__)

@agent_bp.route("/agent/scrape", methods=["POST"])
def scrape_agent():
    # 1. Build the graph fresh for this request
    graph = create_scraper_graph()

    # 2. Run the graph — this blocks until all URLs are processed
    final_state = graph.invoke(
        {
            "websites": [],
            "keywords": [],
            "pending_urls": [],
            "scraped_urls": [],
            "current_article": {},
            "matched_articles": []
        },
        config={"configurable": {"thread_id": "scraper-main"}}
    )

    # 3. Return only the matched articles to the caller
    return jsonify(final_state["matched_articles"]), 200
```

**Why `POST` and not `GET`?**
`GET` is for fetching existing data. `POST` is for triggering an action that causes side effects — the scrape run hits external websites, processes data, and would eventually save drafts to DB. That's an action, not a retrieval.

**Why `/agent/scrape` not `/websites/scrape`?**
The endpoint triggers an agent job, not a CRUD operation on a resource. It lives under `/agent` to separate it from resource routes (`/websites`, `/keywords`, `/drafts`).

**Registration in `app/__init__.py`:**
```python
from .routes.agent import agent_bp
app.register_blueprint(agent_bp)
```

**Testing:**
```
POST http://127.0.0.1:5000/agent/scrape
Body: (empty)
Response: JSON array of matched ArticleState objects
```

---

## 11. Python Concepts Used

### List Comprehension
A compact way to build a list with a condition:

```python
# Filter URLs not already scraped
clean_urls = [url for url in pending_urls if url not in scraped_urls]

# Extract keywords that appear in text
matches = [k for k in keywords if k in article_text]

# Extract URLs from link objects
urls = [link.get("href") for link in soup.find_all("a")
        if link.get("href") and link.get("href").startswith("http")]
```

Pattern: `[expression for item in iterable if condition]`

### set() for Deduplication
```python
urls = set()           # empty set — no duplicates allowed
urls.add("url1")
urls.add("url1")       # ignored — already in set
urls.add("url2")
print(urls)            # {"url1", "url2"}

list(urls)             # convert back to list for state
```

### try/except for Resilient Scraping
```python
try:
    response = requests.get(url, timeout=10)
except Exception:
    continue   # skip this URL, move to next
```

Without this: one broken URL crashes the entire graph run.

---

## What We Got Wrong → How We Fixed It

### Mistake 1: Route method syntax in decorator
**Wrong:** `@website_bp.route("GET /urls")`
**Right:** `@agent_bp.route("/agent/scrape", methods=["POST"])`

### Mistake 2: `add_conditional_edge` (missing 's')
**Wrong:** `builder.add_conditional_edge(...)`
**Right:** `builder.add_conditional_edges(...)`
Python won't catch typos until runtime — always test immediately after writing.

### Mistake 3: SqliteSaver context manager issue
`SqliteSaver.from_conn_string()` returns a context manager, not the saver directly. Needed `with` statement but that closed the connection before compile. Fixed by switching to `MemorySaver` for dev.

### Mistake 4: Dedup loop going to wrong node
**Wrong:** Conditional edge looped back to `scrape_article`
**Right:** Looped back to `check_dedup`
Without this, URLs scraped in previous loop iterations wouldn't be filtered on the next pass.

### Mistake 5: `pending_urls = {}` instead of `set()`
`{}` creates an empty dict in Python. `set()` creates an empty set. Easy mistake, silent bug — dict doesn't have `.add()` so it would crash at runtime.

### Mistake 6: Not filtering relative URLs
BeautifulSoup returns all hrefs including `/latest/`, `#section`, `mailto:`. Fixed by filtering with `.startswith("http")`.

### Mistake 7: Not filtering to same domain
Crawling Hashnode collected links to Twitter, LinkedIn, GitHub. Fixed by comparing `urlparse(href).netloc == site_domain`.

### Mistake 8: `continue` vs `return` in loop
**Wrong:** `return {"pending_urls": []}` inside the loop — exits the entire function on first failed URL
**Right:** `continue` — skips that URL and moves to the next website

---

## Commit History After Phase 2

```
refactor(backend): written clean logic for check_dedup node
fix(backend): deduplicate pending URLs, filter same-domain links, fix dedup loop
feat(backend): implement LangGraph scraper agent with BS4 crawling, dedup, and keyword matching
chore(backend): add agents package for LangGraph agent modules
```

---

## Note — Why LangGraph and Not Plain Python?

For the scraper agent alone, plain Python would work fine. It's just a loop with BeautifulSoup calls. So why LangGraph?

**The scraper is the simple half. The rewriter is where LangGraph earns its place.**

| Problem | Plain Python | LangGraph |
|---|---|---|
| LLM tool calling (rewriter) | Manually orchestrate every call, parse responses, decide next step | `@tool` decorator + agent executor handles routing automatically |
| Shared state between agents | Pass data manually between functions, easy to lose context | Single state schema flows through both agents cleanly |
| Conditional routing | if/else chains threading through function calls | Declarative conditional edges |
| Fault tolerance | Crash = start over | Resumes from last checkpoint |
| Adding a third agent | Refactor the entire flow | Add one node and two edges |

**Bottom line:** For the scraper in isolation, LangGraph is overkill. But once Agent B (rewriter) is wired in — the shared state, tool calling, and checkpoint persistence make the entire pipeline significantly cleaner than equivalent plain Python would be.

The scraper agent benefits from LangGraph indirectly — it sits in the same graph as the rewriter, sharing state and checkpoints for free.


---

## Key Highlights to Remember

| Concept | Remember this |
|---|---|
| LangGraph vs LangChain | LangChain = linear pipeline. LangGraph = stateful graph with loops and memory |
| State | Shared memory passed between all nodes. TypedDict schema. Each node returns only changed fields |
| Node | Just a Python function: `def node(state) -> dict` |
| Conditional edge | Router function returns a string key that maps to the next node |
| Loop back to `check_dedup` | Not `scrape_article` — dedup must run every iteration |
| `thread_id` | Same ID every run = loads previous state = dedup works across days |
| Checkpointer | Snapshots state at every super-step. MemorySaver for dev, SqliteSaver for prod |
| Super-step | One round of node execution. Graph terminates when all nodes halt + no messages in transit |
| `set()` not `{}` | `{}` is a dict. `set()` is a set. Use `set()` for deduplication |
| `continue` not `return` | In a loop, `return` exits the function. `continue` skips to next iteration |
| BeautifulSoup | Parse HTML, extract links with `find_all("a")`, extract text with `get_text()` |
| `urlparse().netloc` | Extracts domain from URL. Use for same-domain filtering |
| `try/except` in scraper | Wrap every `requests.get()` — one broken site shouldn't crash the whole graph |

---

*Next: Phase 3 — Rewriter Agent (Agent B). LLM rewriting in matching article's style, Nano Banana image generation, saving draft to DB.*