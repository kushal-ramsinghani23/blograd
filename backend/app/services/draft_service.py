from ..models.draft import Draft

def validate_draft_update(draft):
    if draft.get("status") and draft.get("status") not in ["draft", "approved", "published"]:
        return False, "Draft status must be draft/approved/published"

    return True, None