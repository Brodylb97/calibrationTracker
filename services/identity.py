# services/identity.py - User identity abstraction (future-facing)
#
# Placeholder for future user identity when server-backed multi-user is implemented.
# Currently returns local operator name from settings or "local".


def get_current_user_id(repo=None) -> str:
    """
    Placeholder for future user identity.
    Returns local operator name from settings, or "local" if unavailable.
    When server-backed work begins, this will return authenticated user ID.
    """
    if repo is None:
        return "local"
    try:
        name = repo.get_setting("operator_name", "")
        return (name or "").strip() or "local"
    except Exception:
        return "local"
