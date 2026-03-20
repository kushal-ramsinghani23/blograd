from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.keyword import Keyword

keyword_bp = Blueprint("keyword", __name__)

@keyword_bp.route("/keywords", methods=["GET"])
def get_all_keywords():
    keywords = Keyword.query.all()
    return jsonify([k.to_dict() for k in keywords])

@keyword_bp.route("/keywords", methods=["POST"])
def add_keyword():
    data = request.get_json()
    word = data["word"]
    category = data["category"]

    keyword = Keyword(word=word, category=category)
    db.session.add(keyword)
    db.session.commit()

    return "Keyword created", 201

@keyword_bp.route("/keywords/<id>", methods=["DELETE"])
def delete_keyword(id):
    keyword = Keyword.query.get(id)
    if keyword:
        db.session.delete(keyword)
        db.session.commit()
        return "Keyword deleted", 204

    return "Keyword not found", 404