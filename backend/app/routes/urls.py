from flask import Blueprint

website_bp = Blueprint("website", __name__)

@website_bp.route("/urls", methods=["GET"])
def urls():
    return "urls route works"