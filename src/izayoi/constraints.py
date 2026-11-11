"""Placement constraints for the optimizer.

An *area* is a string of space-separated selectors. Selectors of the same
category are combined with OR, different categories with AND, and a
selector prefixed with "!" excludes the slots it matches.

    base / d / k / solo     layer (prefix layers are named after their key;
                            solo is a prefix key pressed on its own)
    top / home / bottom     row
    left / right            hand
    index / middle / ring / pinky   finger
    same / cross            prefix shift with a key on the same / other hand
                            as the prefix key (never matches the base layer)
    @jkl                    explicit keys

Examples: "base home", "right !pinky", "d @jkl;", "base @,", "same".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .keyboard import KEY_INDEX, KEY_INFO

Slot = tuple[str, str]  # (layer, key)


def aligned_slot(slot: Slot, layers: list[str]) -> Slot | None:
    """The same-hand prefix shift on the same key as `slot`, if any."""
    layer, key = slot
    if layer == "solo":
        return None
    hand = KEY_INFO[KEY_INDEX[key]].hand
    prefixes = [p for p in layers if p in KEY_INDEX and KEY_INFO[KEY_INDEX[p]].hand == hand]
    if len(prefixes) > 1:
        raise ConstraintError(f"several prefix keys on the same hand: {prefixes}")
    return (prefixes[0], key) if prefixes else None


ROW_NAMES = {"top": 0, "home": 1, "bottom": 2}
HAND_NAMES = {"left": 0, "right": 1}
FINGER_NAMES = {"pinky": (0, 7), "ring": (1, 6), "middle": (2, 5), "index": (3, 4)}


class ConstraintError(ValueError):
    pass


def _match(token: str, slot: Slot, layers: list[str]) -> tuple[str, bool]:
    """Return (category, matched) for a single selector."""
    layer, key = slot
    info = KEY_INFO[KEY_INDEX[key]]
    if token.startswith("@"):
        return "key", key in token[1:]
    if token in layers:
        return "layer", layer == token
    if token in ROW_NAMES:
        return "row", info.row == ROW_NAMES[token]
    if token in HAND_NAMES:
        return "hand", info.hand == HAND_NAMES[token]
    if token in FINGER_NAMES:
        return "finger", info.finger in FINGER_NAMES[token]
    if token in ("same", "cross"):
        if layer not in KEY_INDEX:  # base or solo
            return "shift", False
        same = KEY_INFO[KEY_INDEX[layer]].hand == info.hand
        return "shift", same == (token == "same")
    raise ConstraintError(f"unknown selector {token!r} (layers: {layers})")


def select(area: str, slots: list[Slot], layers: list[str]) -> set[Slot]:
    tokens = area.split()
    if not tokens:
        raise ConstraintError("empty area")
    result = set()
    for slot in slots:
        groups: dict[str, bool] = {}
        excluded = False
        for token in tokens:
            if token.startswith("!"):
                excluded |= _match(token[1:], slot, layers)[1]
            else:
                cat, ok = _match(token, slot, layers)
                groups[cat] = groups.get(cat, False) or ok
        if not excluded and all(groups.values()):
            result.add(slot)
    return result


def select_any(areas: str | list[str], slots: list[Slot], layers: list[str]) -> set[Slot]:
    if isinstance(areas, str):
        areas = [areas]
    return set().union(*(select(a, slots, layers) for a in areas))


@dataclass
class Constraints:
    pinned: dict[str, str] = field(default_factory=dict)  # unit -> area of exactly one slot
    areas: list[dict] = field(default_factory=list)  # {"units": [...], "in"/"not_in": [...]}
    reserved: list[str] = field(default_factory=list)  # areas kept empty
    # {"area": [...], "units": [...]}: only these units may be placed in the area
    exclusive: list[dict] = field(default_factory=list)
    # follower -> leader: the follower sits on the same key as the leader,
    # in the prefix shift on the same hand as that key (e.g. が follows か)
    aligned: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_toml(cls, data: dict) -> Constraints:
        c = cls(
            pinned=dict(data.get("pinned", {})),
            areas=list(data.get("area", [])),
            reserved=list(data.get("reserved", [])),
            exclusive=list(data.get("exclusive", [])),
            aligned=dict(data.get("aligned", {})),
        )
        leaders = list(c.aligned.values())
        if dup := {u for u in leaders if leaders.count(u) > 1}:
            raise ConstraintError(f"aligned: several units follow {sorted(dup)}")
        if both := set(c.aligned) & set(leaders):
            raise ConstraintError(f"aligned: units both follow and lead: {sorted(both)}")
        for rule in c.exclusive:
            if "area" not in rule or "units" not in rule:
                raise ConstraintError(f"exclusive rule needs area and units: {rule}")
        for rule in c.areas:
            if "units" not in rule or ("in" in rule) == ("not_in" in rule):
                raise ConstraintError(f"area rule needs units and exactly one of in/not_in: {rule}")
        return c

    def allowed(
        self, units: list[str], slots: list[Slot], layers: list[str], strict: bool = True
    ) -> dict[str, set]:
        """Slots each unit may occupy (reserved slots removed).

        With strict=False, rules mentioning units that are not in `units` are
        applied to the known units only (used to check a hand-edited layout).
        """

        def known(u: str, what: str) -> bool:
            if u in allowed:
                return True
            if strict:
                raise ConstraintError(f"{what} refers to unknown unit {u!r}")
            return False

        reserved = select_any(self.reserved, slots, layers) if self.reserved else set()
        free = set(slots) - reserved
        allowed = {u: set(free) for u in units}
        for rule in self.areas:
            for u in rule["units"]:
                if not known(u, "area rule"):
                    continue
                if "in" in rule:
                    allowed[u] &= select_any(rule["in"], slots, layers)
                else:
                    allowed[u] -= select_any(rule["not_in"], slots, layers)
        for rule in self.exclusive:
            area = select_any(rule["area"], slots, layers)
            for u in rule["units"]:
                known(u, "exclusive rule")
            for u in allowed:
                if u not in rule["units"]:
                    allowed[u] -= area
        for u, area in self.pinned.items():
            if not known(u, "pinned"):
                continue
            target = select(area, slots, layers)
            if len(target) != 1:
                raise ConstraintError(f"pinned {u!r} = {area!r} matches {len(target)} slots")
            if not target <= allowed[u]:
                raise ConstraintError(f"pinned {u!r} = {area!r} contradicts other constraints")
            allowed[u] = target
            for other in units:
                if other != u:
                    allowed[other] -= target
        for u, s in allowed.items():
            if not s:
                raise ConstraintError(f"no slot satisfies the constraints for {u!r}")
        return allowed

    def violations(self, placement: dict[str, Slot], slots: list[Slot], layers: list[str]):
        """Human readable violations of an existing placement."""
        units = list(placement)
        allowed = self.allowed(units, slots, layers, strict=False)
        out = []
        for u, slot in placement.items():
            if slot not in allowed[u]:
                out.append(f"{u} は {slot[0]}:{slot[1]} に置けない")
        for follower, leader in self.aligned.items():
            if follower in placement and leader in placement:
                if placement[follower] != aligned_slot(placement[leader], layers):
                    out.append(f"{follower} が {leader} と同じキーの同手シフトにない")
        return out


def assign(allowed: list[set[int]], n_slots: int, order: list[int]) -> list[int]:
    """Find a slot for every unit (bipartite matching), trying units in `order`."""
    owner = [-1] * n_slots

    def augment(u: int, seen: set[int]) -> bool:
        for s in allowed[u]:
            if s in seen:
                continue
            seen.add(s)
            if owner[s] < 0 or augment(owner[s], seen):
                owner[s] = u
                return True
        return False

    for u in order:
        if not augment(u, set()):
            raise ConstraintError("constraints cannot be satisfied simultaneously")
    pos = [-1] * len(allowed)
    for s, u in enumerate(owner):
        if u >= 0:
            pos[u] = s
    return pos
