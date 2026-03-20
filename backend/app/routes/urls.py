from flask import Blueprint

demoBlue = Blueprint("__demo__", __name__)

@demoBlue.route("/urls", methods=["GET"])
def urls():
    return "urls route works"