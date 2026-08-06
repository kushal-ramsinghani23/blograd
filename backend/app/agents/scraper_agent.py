import time
from typing import TypedDict, List
from urllib.parse import urlparse

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ..models.keyword import Keyword
from ..models.website import Website

from firecrawl import FirecrawlApp

class ArticleState(TypedDict):
    url: str
    text: str
    source_site: str
    matched_keywords: List[str]
    summary: str

class ScraperState(TypedDict):
    websites: List[str]
    keywords: List[str]
    pending_urls: List[str]
    scraped_urls: List[str]
    current_article: ArticleState
    matched_articles: List[ArticleState]


def fetch_websites_and_keywords(state: ScraperState):
    websites = state.get("websites") or [w.url for w in Website.query.all()]
    keywords = state.get("keywords") or [k.word for k in Keyword.query.all()]
    return {
        "websites": websites,
        "keywords": keywords
    }


def crawl_blog_index(state: ScraperState) -> ScraperState:
    firecrawl = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
    all_urls = []
    for website in state["websites"]:
        try:
            result = firecrawl.crawl_url(
                website,
                limit=5,
                scrape_options={"formats": ["markdown"]}
            )
            # result is a CrawlJob object — access .data
            pages = result.data if hasattr(result, 'data') else result.get("data", [])
            urls = [
                page_url for page_url in urls
                if any(segment in page_url for segment in ['/2024/', '/2025/', '/2026/', '/posts/', '/blog/'])
                    and 'sitemap' not in page_url
                    and '/tag/' not in page_url
            ]
            for page in pages:
                meta = page.metadata if hasattr(page, 'metadata') else page.get("metadata", {})
                url = meta.get("sourceURL") if isinstance(meta, dict) else getattr(meta, 'source_url', None)
                if url:
                    urls.append(url)
            print(f"[DEBUG] URLs found for {website}: {urls}")
            all_urls.extend(urls)
            time.sleep(2)  # respect rate limit
        except Exception as e:
            print(f"[WARN] Failed to crawl {website}: {e}")
    return {"pending_urls": list(set(all_urls))}

def check_dedup(state: ScraperState) -> ScraperState:
    pending = [url for url in state["pending_urls"] if url not in state["scraped_urls"]]
    return {"pending_urls": pending}

def scrape_article(state: ScraperState) -> ScraperState:
    if not state["pending_urls"]:
        return {
            "pending_urls": [],
            "current_article": {"url": "", "text": "", "source_site": "", "matched_keywords": [], "summary": ""}
        }

    firecrawl = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
    url = state["pending_urls"][0]
    remaining = state["pending_urls"][1:]

    try:
        result = firecrawl.scrape_url(url, formats=["markdown"])
        # result is a Document object — access attribute directly
        text = getattr(result, 'markdown', None) or ""
        source_site = url.split("/")[2]
        time.sleep(6)  # 10 req/min = 1 every 6s
    except Exception as e:
        print(f"[WARN] Failed to scrape {url}: {e}")
        text = ""
        source_site = url.split("/")[2] if "/" in url else url

    return {
        "pending_urls": remaining,
        "current_article": {
            "url": url,
            "text": text,
            "source_site": source_site,
            "matched_keywords": [],
            "summary": ""
        }
    }

def match_keywords(state: ScraperState):
    current_article = state["current_article"]
    keywords = state["keywords"]

    keywords_present = [k for k in keywords if k in current_article["text"]]
    if keywords_present:
        current_article: ArticleState = {
            "url": current_article["url"],
            "text": current_article["text"],
            "source_site": current_article["source_site"],
            "matched_keywords": keywords_present,
        }
        return {
            'current_article' : current_article,
            'matched_articles': state["matched_articles"] + [current_article], # New updated list
        }

    return {}

def rank_articles(state: ScraperState):
    matched_articles = state["matched_articles"]

    def keyword_frequency(article: ArticleState) -> int:
        return sum(
            article["text"].count(keyword)
            for keyword in article["matched_keywords"]
        )

    ranked = sorted(matched_articles, key=keyword_frequency, reverse=True)

    return {"matched_articles": ranked}

def summarize_articles(state: ScraperState):
    matched_articles = state["matched_articles"][:5]

    # model = ChatGoogleGenerativeAI(
    #     model="models/gemini-2.0-flash",
    #     temperature=0.3,
    #     google_api_key=os.getenv("GEMINI_API_KEY")
    # )
    model = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        max_tokens=500,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )

    summarized = []
    for article in matched_articles:
        messages = [
            (
                "system",
                "You are a content analyst. Given a blog article, extract a structured summary."
                "Respond in this exact format:\n"
                "SUMMARY: (2-3 sentence summary of the article)\n"
                "STYLE: (tone, structure, vocabulary level — 1-2 sentences)\n"
                "KEY POINTS: (3-5 bullet points of main ideas)"
            ),
            (
                "human",
                f"Article URL: {article['url']}\n\n"
                f"Matched keywords: {', '.join(article['matched_keywords'])}\n\n"
                f"Article text:\n{article['text'][:3000]}"  # first 3000 chars to stay within token limits
            )
        ]

        try:
            response = model.invoke(messages)
            summarized.append({
                **article,
                "summary": response.content
            })
            time.sleep(0.5)
        except Exception as e:
            print(f"[WARN] Skipping article {article['url']}: {e}")

    return {"matched_articles": summarized}

def router_function(state: ScraperState):
    if state["pending_urls"]:
        return "continue"
    return "end"

def create_scraper_graph():
    builder = StateGraph(ScraperState)

    builder.add_node("fetch_websites_and_keywords", fetch_websites_and_keywords)
    builder.add_node("crawl_blog_index", crawl_blog_index)
    builder.add_node("check_dedup", check_dedup)
    builder.add_node("scrape_article", scrape_article)
    builder.add_node("match_keywords", match_keywords)
    builder.add_node("rank_articles", rank_articles)
    builder.add_node("summarize_articles", summarize_articles)

    builder.add_edge(START, "fetch_websites_and_keywords")
    builder.add_edge("fetch_websites_and_keywords", "crawl_blog_index")
    builder.add_edge("crawl_blog_index", "check_dedup")
    builder.add_edge("check_dedup", "scrape_article")
    builder.add_edge("scrape_article", "match_keywords")
    builder.add_edge("rank_articles", "summarize_articles")
    builder.add_edge("summarize_articles", END)

    builder.add_conditional_edges(
        "match_keywords",
        router_function,
        {
            "continue": "check_dedup",
            "end": "rank_articles"
        }
    )

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)
