import time
from typing import TypedDict, List
from urllib.parse import urlparse

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from bs4 import BeautifulSoup
from langgraph.checkpoint.memory import MemorySaver
from playwright.sync_api import sync_playwright
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import requests

from ..models.keyword import Keyword
from ..models.website import Website


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
    websites = [w.url for w in Website.query.all()]
    keywords = [k.word for k in Keyword.query.all()]

    return {
        'websites': websites,
        'keywords': keywords,
    }

def crawl_blog_index(state: ScraperState):
    pending_urls = set()

    for url in state["websites"]:
        try:
            path = urlparse(url).path
            if path == "" or path == "/":
                url = url.rstrip("/") + "/blog"

            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                # fallback to original URL without /blog
                url = url.replace("/blog", "")
                response = requests.get(url, timeout=10)
        except Exception:
            continue
        html_doc = response.text

        soup = BeautifulSoup(html_doc, "html.parser")
        for link in soup.find_all("a"):
            link_href = link.get("href")
            if link_href and link_href.startswith("http"):
                site_domain = urlparse(url).netloc
                if urlparse(link_href).netloc == site_domain:
                    pending_urls.add(link_href)

    return {
        'pending_urls': list(pending_urls),
    }

def check_dedup(state: ScraperState):
    updated_pending_urls = [url for url in state["pending_urls"] if url not in state["scraped_urls"]]
    return {
        'pending_urls': updated_pending_urls,
    }

def scrape_article(state: ScraperState):
    pending_urls = state["pending_urls"]
    scraped_urls = state["scraped_urls"]

    try:
        response = requests.get(pending_urls[0], timeout=10)
    except Exception:
        # skip this URL, move on
        return {
            'pending_urls': pending_urls[1:],
            'scraped_urls': scraped_urls + [pending_urls[0]],
        }
    html_doc = response.text
    soup = BeautifulSoup(html_doc, "html.parser")

    content = soup.get_text(strip=True)
    text = content
    if len(content) < 500:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(pending_urls[0], timeout=60000)
                page.wait_for_load_state("domcontentloaded")
                content = page.content()
                browser.close()
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(strip=True)
        except Exception:
            text = content  # use whatever BS4 got, even if minimal
    current_article: ArticleState = {
        "url": pending_urls[0],
        "text": text,
        "source_site": urlparse(pending_urls[0]).netloc,
        "matched_keywords": []
    }

    scraped_urls.append(pending_urls[0])
    pending_urls = pending_urls[1:]

    return {
        'pending_urls': pending_urls,
        'scraped_urls': scraped_urls,
        'current_article': current_article,
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
