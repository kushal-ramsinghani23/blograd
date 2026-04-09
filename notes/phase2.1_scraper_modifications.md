# Phase 2.1 — Scraper Agent Modifications

---

## The Story

The scraper agent was working — but it had three meaningful gaps. BS4 was missing JS-rendered content, we were only scraping homepages instead of blog indexes, and all matched articles were treated equally regardless of how relevant they actually were.

This phase fixes all three before we hand off to the rewriter. No new agents, no new tools — just making the scraper smarter.

We are at: **Scraper agent fully optimised. Output is deduplicated, domain-filtered, relevance-ranked, and ready to be summarized and passed to Agent B.**

---

## 1. Playwright Fallback — Handling JS-Rendered Content

### The Problem
BeautifulSoup parses whatever HTML the server sends in the initial HTTP response. But modern blog platforms (Hashnode, Medium, Dev.to) work like this:

```
Browser requests page
  → Server sends near-empty HTML skeleton
  → Browser runs JavaScript
  → JavaScript fetches content and fills in the page
  → User sees the full article
```

`requests.get()` mimics only the first step — it gets the skeleton. JavaScript never runs. So BS4 sees an almost empty page and `get_text()` returns a few hundred characters at most.

**Before (BS4 only):**
```python
response = requests.get(url)
soup = BeautifulSoup(response.text, "html.parser")
text = soup.get_text()   # might be nearly empty for JS-rendered sites
```

**After (BS4 + Playwright fallback):**
```python
text = soup.get_text(strip=True)
if len(text) < 500:   # suspiciously little content → probably JS-rendered
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.wait_for_load_state("networkidle")  # wait for all JS to finish
        content = page.content()                 # full rendered HTML
        browser.close()
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(strip=True)             # now properly populated
```

### Why 500 characters as the threshold?
A real article is thousands of characters. If BS4 returns less than 500, something is wrong — it's either a JS-rendered page or a genuinely empty page. Either way, Playwright either fixes it or confirms there's nothing there.

### BS4 vs Playwright — the one-line summary

| | BeautifulSoup | Playwright |
|---|---|---|
| What it does | Parses raw HTML | Launches a real browser |
| JavaScript | Never runs | Fully executes |
| Speed | Fast | Slow (real browser overhead) |
| Use when | Static sites, most pages | JS-heavy sites, empty BS4 output |

**Analogy:** BS4 reads the blueprint of a building. Playwright walks through the fully constructed building.

### Why not just use Playwright for everything?
Speed. Launching a browser for every URL adds 2-5 seconds per page. BS4 is nearly instant. We use Playwright only as a fallback — best of both worlds.

---

## 2. Blog Path Optimization — Scraping the Right Page

### The Problem
When a user adds `https://hashnode.com` to our websites list, `crawl_blog_index` was fetching the homepage. Homepages typically show 5-10 featured articles. The `/blog` page shows the full article index — many more relevant links.

### The Fix
Before making the request, check if the URL is a bare homepage (no path beyond `/`). If so, append `/blog`:

```python
path = urlparse(url).path
if path == "" or path == "/":
    url = url.rstrip("/") + "/blog"
```

### What if the site doesn't have a /blog page?
Some sites use `/articles`, `/posts`, or just don't have a dedicated blog index. We handle this with a status code check:

```python
response = requests.get(url, timeout=10)
if response.status_code != 200:
    # /blog doesn't exist — fall back to original homepage
    url = url.replace("/blog", "")
    response = requests.get(url, timeout=10)
```

This makes the optimization **safe** — if `/blog` doesn't exist, we silently fall back to the homepage and continue normally.

### When does this NOT apply?
If the user already added a specific path like `https://techcrunch.com/category/artificial-intelligence`, the path is not empty — we leave it untouched.

```python
urlparse("https://techcrunch.com").path          # "" → append /blog
urlparse("https://techcrunch.com/").path         # "/" → append /blog
urlparse("https://techcrunch.com/ai").path       # "/ai" → leave as is
```

---

## 3. rank_articles Node — Relevance Ordering

### The Problem
After `match_keywords`, all matched articles are treated equally. An article that mentions "AI" once and an article that deeply covers AI across 5000 words both end up in `matched_articles` with no distinction. The rewriter would process them in arbitrary order.

### The Fix
Add a `rank_articles` node that sorts matched articles by **total keyword frequency** — the sum of how many times each matched keyword appears in the article text.

```python
def rank_articles(state: ScraperState):
    matched_articles = state["matched_articles"]

    def keyword_frequency(article: ArticleState) -> int:
        return sum(
            article["text"].count(keyword)
            for keyword in article["matched_keywords"]
        )

    ranked = sorted(matched_articles, key=keyword_frequency, reverse=True)
    return {"matched_articles": ranked}
```

### Why total occurrences and not just number of matched keywords?
- **Number of matched keywords** (Option A): An article matching 3 keywords — "AI", "startup", "funding" — scores 3. But it might only mention each once.
- **Total occurrences** (Option B): An article matching just "AI" but mentioning it 47 times scores 47. It deeply covers the topic.

Option B is more accurate — it tells us how much a topic is actually covered, not just whether it was mentioned.

### Where does rank_articles sit in the graph?
After all URLs are processed — not inside the loop. The conditional edge on `match_keywords` now routes:
- `"continue"` → `check_dedup` (more URLs to process)
- `"end"` → `rank_articles` (all URLs done, now rank everything)

```
START → fetch → crawl → check_dedup → scrape → match_keywords
                             ↑                        |
                             |______ continue _________|
                                          |
                                        end
                                          ↓
                                    rank_articles → END
```

### Graph Wiring Fix
An earlier version had the conditional edge on `rank_articles` instead of `match_keywords`, and `"end"` incorrectly looping back to `rank_articles`. Fixed:

```python
# Wrong
builder.add_conditional_edges("rank_articles", router_function, {"continue": "check_dedup", "end": "rank_articles"})

# Correct
builder.add_conditional_edges("match_keywords", router_function, {"continue": "check_dedup", "end": "rank_articles"})
builder.add_edge("rank_articles", END)
```

---

## What We Changed → Why

| Change | Reason |
|---|---|
| Playwright fallback when `len(text) < 500` | BS4 misses JS-rendered content on modern blog platforms |
| `/blog` path appended to bare homepage URLs | Blog index pages have more articles than homepages |
| Status code check with fallback | Not all sites have a `/blog` page — fail gracefully |
| `rank_articles` node added | All matched articles were treated equally — most relevant should be processed first |
| Conditional edge moved from `rank_articles` to `match_keywords` | Router checks pending URLs after matching, not after ranking |
| `"end"` routes to `rank_articles` not `END` | Ranking happens once, after all URLs are processed |

---

## Commit

```
feat(backend): add Playwright fallback, blog path optimization, rank_articles node, and fix graph wiring

- Add Playwright fallback in scrape_article when BS4 returns < 500 chars
- Append /blog to bare homepage URLs in crawl_blog_index
- Add status code check with fallback to original URL
- Add rank_articles node sorting matched articles by keyword frequency
- Fix conditional edge routing: match_keywords loops to check_dedup, ends at rank_articles
```

---

*Next: Phase 3 — Rewriter Agent. Gemini LLM summarization, style analysis, blog rewriting, Nano Banana image generation, draft saved to DB.*