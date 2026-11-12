"""Placement policies: order candidate nodes for an allocation request."""


def first_fit(fabric, anchor, cands, amount):
    return [c for c in cands if c.free > 0]


def nearest_fit(fabric, anchor, cands, amount):
    """Prefer low hop count to the app's anchor; among equals prefer nodes that fit fully, then tightest fit."""
    def key(c):
        hops = fabric.hops(anchor, c.name) if anchor else 0
        return (hops, 0 if c.free >= amount else 1, c.free)
    return sorted((c for c in cands if c.free > 0), key=key)


POLICIES = {"first_fit": first_fit, "nearest_fit": nearest_fit}
