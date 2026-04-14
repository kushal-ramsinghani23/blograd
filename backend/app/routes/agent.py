from ..agents.rewriter_agent import create_rewriter_graph
from flask import Blueprint, request, jsonify
from ..agents.scraper_agent import create_scraper_graph

agent_bp = Blueprint("agent", __name__)

@agent_bp.route("/agent/scrape", methods=["POST"])
def scrape_agent():
    graph = create_scraper_graph()
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