from typing import TypedDict, List
from langchain_groq import ChatGroq
from google import genai
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from ..models.draft import Draft
from ..extensions import db

from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

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
    prompt = f"""You are a professional blog writer. Rewrite the following article as a polished, original blog post.

    Summary: {article['summary']}
    Source URL: {article['url']}

    Return your response in EXACTLY this format:
    TITLE: <compelling title here>
    CONTENT:
    # <title>

    > <one line hook>

    ---

    ## Introduction

    <2-3 paragraphs>

    ---

    ## <Section 1 heading based on content>

    <content>

    ---

    ## <Section 2 heading based on content>

    <content>

    ---

    ## <Section 3 heading based on content>

    <content>

    ---

    ## Key Takeaways

    - <takeaway 1>
    - <takeaway 2>
    - <takeaway 3>

    ---

    ## Conclusion

    <1-2 paragraphs>

    ---

    *Sources: {article['url']}*

    Write at least 800 words. Use the STYLE from the summary to match tone and vocabulary."""

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

@tool
def generate_image_tool(title: str) -> str:
    """Generate a hero image for a blog post given its title.
    Only call this if the article topic is visual, concrete, or product-related.
    Skip for abstract, opinion, or policy articles."""
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=f"Blog hero image for: {title}"
        )
        filename = title.lower().replace(" ", "_")[:50]
        image_path = f"static/images/{filename}.png"
        for part in response.parts:
            if part.inline_data is not None:
                image = part.as_image()
                image.save(image_path)
                return image_path
        return "static/images/default.png"
    except Exception as e:
        print(f"[WARN] Image generation failed: {e}")
        return "static/images/default.png"

def agent_node(state: RewriterState) -> RewriterState:
    rewritten = state["current_rewritten"]
    tools = [generate_image_tool]
    llm = ChatGroq(model="llama-3.3-70b-versatile").bind_tools(tools)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a blog post finisher. You have a rewritten article.
        Decide whether to generate a hero image based on the article title and content.
        Generate an image ONLY if the topic is visual, concrete, or product-related.
        SKIP image generation for abstract, opinion, or policy articles.
        After deciding, return the image path or 'static/images/default.png'."""),
        ("human", f"Article title: {rewritten['title']}\nContent preview: {rewritten['content'][:200]}")
    ])

    chain = prompt | llm
    response = chain.invoke({})

    image_path = "static/images/default.png"
    if response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call["name"] == "generate_image_tool":
                image_path = generate_image_tool.invoke(tool_call["args"])

    updated_rewritten = {
        **rewritten,
        "featured_image_url": image_path
    }

    return {"current_rewritten": updated_rewritten}

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
    builder.add_node("generate_image", agent_node)
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
