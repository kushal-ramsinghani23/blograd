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