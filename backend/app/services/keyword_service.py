from ..models.keyword import Keyword

def validate_keyword(keyword):
    if not keyword.get("word"): return False, "Word not found"
    if not keyword.get("category"): return False, "Category not found"

    keyword_in_db = Keyword.query.filter_by(word=keyword.get("word")).first()
    if keyword_in_db: return False, "Keyword already exists"

    return True, None