from typing import TypedDict, List
from urllib.parse import urlparse
from langgraph.graph import StateGraph, START, END
from bs4 import BeautifulSoup
from langgraph.checkpoint.memory import MemorySaver

import requests

from ..models.keyword import Keyword
from ..models.website import Website


class ArticleState(TypedDict):
    url: str
    text: str
    source_site: str
    matched_keywords: List[str]

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
    current_article: ArticleState = {
        "url": pending_urls[0],
        "text": soup.get_text(),
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

    builder.add_edge(START, "fetch_websites_and_keywords")
    builder.add_edge("fetch_websites_and_keywords", "crawl_blog_index")
    builder.add_edge("crawl_blog_index", "check_dedup")
    builder.add_edge("check_dedup", "scrape_article")
    builder.add_edge("scrape_article", "match_keywords")

    builder.add_conditional_edges(
        "match_keywords",
        router_function,
        {
            "continue": "check_dedup",
            "end": END
        }
    )

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)
