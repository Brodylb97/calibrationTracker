# services/future_hooks.py - Inert placeholders for future multi-user features
#
# These hooks do nothing. They exist to document extension points when
# server-backed multi-user work begins. No networking, no concurrency logic.

# Future: enable when opening DB in read-only for viewing. Not implemented.
READ_ONLY_MODE = False


def check_conflict_before_update(record_id: int, expected_version: str) -> bool:
    """
    Placeholder for future conflict detection.
    Returns False (no conflict) for now. When server-backed: compare with remote version.
    """
    return False  # Inert


# Future: compare row_version or revision for merge strategies. Not implemented.
# def compare_versions(local: str, remote: str) -> str: ...
