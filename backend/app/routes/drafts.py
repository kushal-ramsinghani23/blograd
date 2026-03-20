from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.draft import Draft
from ..services.draft_service import validate_draft_update

draft_bp = Blueprint("draft", __name__)

@draft_bp.route("/drafts", methods=["GET"])
def get_all_drafts():
    drafts = Draft.query.all()
    return jsonify([d.to_dict() for d in drafts])

@draft_bp.route("/drafts/<id>", methods=["GET"])
def get_draft_by_id(id):
    draft = Draft.query.filter_by(id=id).first()
    if draft:
        return jsonify(draft.to_dict())
    return "Draft not found", 404

@draft_bp.route("/drafts/<id>", methods=["PATCH"])
def update_draft(id):
    draft = Draft.query.filter_by(id=id).first()
    if draft:
        is_valid, error = validate_draft_update(request.json)
        if not is_valid:
            return error, 400

        draft.title = request.json.get("title", draft.title)
        draft.content = request.json.get("content", draft.content)
        draft.status = request.json.get("status", draft.status)

        db.session.add(draft)
        db.session.commit()
        return "Draft Updated", 200

    return "Draft not found", 404

@draft_bp.route("/drafts/<id>", methods=["DELETE"])
def delete_draft(id):
    draft = Draft.query.filter_by(id=id).first()
    if draft:
        db.session.delete(draft)
        db.session.commit()
        return "Draft deleted", 200

    return "Draft not found", 404