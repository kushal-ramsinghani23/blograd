from typing import TypedDict, List
from langchain_groq import ChatGroq
from google import genai
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from models.draft import Draft
from ..extensions import db

import os
os.makedirs("static/images", exist_ok=True)

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
    pending_articles: List[ArticleState]
    current_article: ArticleState
    current_rewritten: RewrittenArticleState
    rewritten_articles: List[RewrittenArticleState]


def rewrite_article(state: RewriterState) -> RewriterState:
    article = state["pending_articles"][0]
    remaining = state["pending_articles"][1:]

    llm = ChatGroq(model="llama-3.3-70b-versatile")

    # Tell LLM exactly what format to return so we can parse reliably
    prompt = f"""You are a blog writer. Rewrite the following article in the same style and tone as the source.

Article Text: {article['text']}
Summary: {article['summary']}

Return your response in EXACTLY this format:
TITLE: <title here>
CONTENT: <full rewritten article here>"""

    response = llm.invoke(prompt)
    text = response.content

    # Parse title and content from structured response
    lines = text.split("\n")
    title = lines[0].replace("TITLE:", "").strip()
    content = "\n".join(lines[1:]).replace("CONTENT:", "").strip()

    rewritten = RewrittenArticleState(
        title=title,
        content=content,
        featured_image_url="",  # filled by generate_image node
        source_url=article["url"],
        matched_keywords=article["matched_keywords"]
    )

    return {
        "pending_articles": remaining,
        "current_article": article,
        "current_rewritten": rewritten
    }

def generate_image(state: RewriterState):
    title = state["current_rewritten"]["title"]
    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-2.0-flash-exp-image-generation",
        contents=f"Blog hero image for: {title}"
    )

    # Build unique filename from title
    filename = title.lower().replace(" ", "_")[:50]
    image_path = f"static/images/{filename}.png"

    for part in response.parts:
        if part.inline_data is not None:
            image = part.as_image()
            image.save(image_path)

    # Build new object, never mutate state
    updated_rewritten = {
        **state["current_rewritten"],
        "featured_image_url": image_path
    }

    return {
        "current_rewritten": updated_rewritten
    }

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

def router_function(state: RewriterState):
    if state["pending_articles"]:
        return "continue"
    return "end"

def create_rewriter_graph():
    builder = StateGraph(RewriterState)

    builder.add_node("rewrite_article", rewrite_article)
    builder.add_node("generate_image", generate_image)
    builder.add_node("save_draft", save_draft)

    builder.add_edge(START, "rewrite_article")
    builder.add_edge("rewrite_article", "generate_image")
    builder.add_edge("generate_image", "save_draft")

    builder.add_conditional_edges(
        "save_draft",
        router_function,
        {
            "continue": "rewrite_article",
            "end": END
        }
    )

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)
