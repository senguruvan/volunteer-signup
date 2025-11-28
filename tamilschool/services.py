"""Business logic helpers for the TamilSchool app.

Keep lightweight helpers here so `ui.py` stays focused on rendering.
"""
from typing import List, Dict


def count_completed_by_vol(assignments: List[Dict]) -> Dict[int, int]:
    """Return a mapping volunteer_id -> number of completed assignments."""
    counts = {}
    for a in assignments:
        if a.get("completed", False):
            vid = a["volunteer_id"]
            counts[vid] = counts.get(vid, 0) + 1
    return counts


def unique_subservices_by_vol(assignments: List[Dict]) -> Dict[int, set]:
    """Return mapping volunteer_id -> set of unique subservice_ids."""
    mapping = {}
    for a in assignments:
        vid = a["volunteer_id"]
        mapping.setdefault(vid, set()).add(a["subservice_id"])
    return mapping
