from ..models.keyword import Keyword
from ..models.website import Website
from ..agents.rewriter_agent import create_rewriter_graph
from flask import Blueprint, request, jsonify
from ..agents.scraper_agent import create_scraper_graph

agent_bp = Blueprint("agent", __name__)


@agent_bp.route("/agent/scrape", methods=["POST"])
def scrape_agent():
    data = request.get_json(silent=True) or {}

    website_ids = data.get("website_ids", [])
    keyword_ids = data.get("keyword_ids", [])

    websites = [w.url for w in Website.query.filter(Website.id.in_(website_ids)).all()] if website_ids else []
    keywords = [k.word for k in Keyword.query.filter(Keyword.id.in_(keyword_ids)).all()] if keyword_ids else []

    graph = create_scraper_graph()
    final_state = graph.invoke(
        {
            "websites": websites,
            "keywords": keywords,
            "pending_urls": [],
            "scraped_urls": [],
            "current_article": {},
            "matched_articles": []
        },
        config={"configurable": {"thread_id": "scraper-main"}}
    )
    return jsonify(final_state["matched_articles"]), 200

@agent_bp.route("/agent/rewrite", methods=["POST"])
def rewrite_agent():
    graph = create_rewriter_graph()

    # Get ScraperAgent's response
    data = request.get_json()
    selected_articles = data.get("selected_articles", [])

    final_state = graph.invoke(
        {
            "pending_articles": selected_articles,
            "current_article": {},
            "current_rewritten": {},
            "rewritten_articles": [],
        },
        config={"configurable": {"thread_id": "scraper-main"}}
    )

    return jsonify(final_state["rewritten_articles"]), 200