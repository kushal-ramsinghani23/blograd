from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.website import Website
from ..services.website_service import validate_website

website_bp = Blueprint("website", __name__)

@website_bp.route("/websites", methods=["GET"])
def get_all_websites():
    websites = Website.query.all()
    return jsonify([w.to_dict() for w in websites])

@website_bp.route("/websites", methods=["POST"])
def add_website():
    data = request.get_json()
    is_valid, error = validate_website(data)
    if not is_valid:
        return error, 400

    name = data["name"]
    url = data["url"]

    website = Website(name=name, url=url)
    db.session.add(website)
    db.session.commit()

    return "Website created", 201

@website_bp.route("/websites/<id>", methods=["DELETE"])
def delete_website(id):
    website = Website.query.get(id)
    if website:
        db.session.delete(website)
        db.session.commit()
        return "Website deleted", 204

    return "Website not found", 404
