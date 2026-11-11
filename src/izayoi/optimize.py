"""Search for a low-cost placement by simulated annealing."""

from __future__ import annotations

import math
import random
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .constraints import ConstraintError, Constraints, aligned_slot, assign
from .evaluate import Spec, UnitStats, composites_from_postfix, omission_composites
from .keyboard import KEY_INDEX, CostModel
from .layout import (
    KEYS,
    ROWS,
    SHADOW,
    SOLO,
    TERMINATOR,
    Layout,
    layer_names,
    make_slots,
    parse,
    parse_postfix,
    shadow,
)

# Added to cost/kana for each shift-omission unit whose prefix cannot be omitted,
# for each postfix rule overridden by a shift omission, and for each preferred
# postfix rule (omit_preferred) whose prefix cannot be omitted.
OMISSION_PENALTY = 1.0
NO_RULE = 1 << 30


@dataclass
class Config:
    prefix_keys: list[str]
    solo: bool
    postfix: dict[str, dict[str, str]]
    units: list[str]
    constraints: Constraints
    omit_units: list[str]
    omit_triggers: list[str]
    omit_postfix: bool
    omit_overridable: list[str]
    omit_preferred: list[str]
    iterations: int
    restarts: int
    seed: int

    @property
    def omit_pairs(self) -> list[tuple[str, str]]:
        """(preceding unit, trigger) of the postfix rules that may be typed without the prefix."""
        if not self.omit_postfix:
            return []
        return [
            (before, t)
            for t in self.omit_triggers
            for before in self.postfix.get(t, {})
            if before in self.units and before not in self.omit_units
        ]

    @property
    def spec(self) -> Spec:
        composites = composites_from_postfix(self.postfix)
        composites.update(omission_composites(self.omit_units, self.omit_triggers))
        # Whether the prefix can be omitted depends on the placement, so each such
        # rule gets its own shadow unit ("ふ*ゃ"), typed with or without the prefix.
        pairs = self.omit_pairs
        for before, t in pairs:
            composites[self.postfix[t][before]] = (shadow(before) + t, t)
        units = sorted(self.units) + [shadow(k) for k in self.omit_units]
        return Spec(units + [shadow(b) + t for b, t in pairs], composites)

    @property
    def layers(self) -> list[str]:
        return layer_names(self.prefix_keys, self.solo)

    @property
    def slots(self) -> list[tuple[str, str]]:
        return make_slots(self.prefix_keys, self.solo)


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    opt = cfg["optimize"]
    units = list(opt["units"])
    if len(set(units)) != len(units):
        raise ValueError("optimize.units contains duplicates")
    prefix = cfg.get("prefix", {})
    return Config(
        prefix_keys=list(prefix.get("keys", [])),
        solo=bool(prefix.get("solo", False)),
        postfix=parse_postfix(cfg.get("postfix", [])),
        units=units,
        constraints=Constraints.from_toml(cfg.get("constraints", {})),
        omit_units=list(cfg.get("shift_omission", {}).get("units", [])),
        omit_triggers=list(cfg.get("shift_omission", {}).get("triggers", [])),
        omit_postfix=bool(cfg.get("shift_omission", {}).get("postfix", False)),
        omit_overridable=list(cfg.get("shift_omission", {}).get("overridable", [])),
        omit_preferred=list(cfg.get("shift_omission", {}).get("preferred", [])),
        iterations=int(opt.get("iterations", 200_000)),
        restarts=int(opt.get("restarts", 4)),
        seed=int(opt.get("seed", 0)),
    )


class Annealer:
    """Places units on slots.

    Aligned units ("followers", e.g. が) are never moved on their own: they
    always sit on the slot aligned with their leader (e.g. か) and move with it.
    """

    def __init__(
        self,
        cfg: Config,
        us: UnitStats,
        cost: CostModel,
        init: Layout | None = None,
        free: set[str] | None = None,
    ):
        """With `init`, start from that layout. If `free` is also given, only those
        units (and units whose initial slot breaks a constraint) are moved."""
        self.cfg = cfg
        # Shadow units (units typed without their prefix) come last in the stats and
        # are never placed themselves: they follow the slot of their kana. Those of
        # omit_units ("に*") come first, then those of postfix rules ("ふ*ゃ").
        self.units = [u for u in us.units if SHADOW not in u]
        n_real = len(self.units)
        shadows = us.units[n_real:]
        n_omit = sum(u.endswith(SHADOW) for u in shadows)
        if any(SHADOW in u for u in us.units[:n_real]) or any(
            u.endswith(SHADOW) for u in shadows[n_omit:]
        ):
            raise ValueError("shadow units must come after the placed units")
        self.shadow_src = np.array(
            [self.units.index(u[: -len(SHADOW)]) for u in shadows[:n_omit]], dtype=int
        )
        pairs = [u.split(SHADOW) for u in shadows[n_omit:]]
        self.pair_src = np.array([self.units.index(b) for b, _ in pairs], dtype=int)
        self.pair_trigger = np.array([cfg.omit_triggers.index(t) for _, t in pairs], dtype=int)
        # Rank of each unit's postfix rule for each trigger (rules written earlier take
        # precedence over later ones on the same base key); NO_RULE if there is none.
        self.rule_rank = np.full((n_real + 1, max(len(cfg.omit_triggers), 1)), NO_RULE)
        for j, t in enumerate(cfg.omit_triggers):
            for r, before in enumerate(cfg.postfix.get(t, {})):
                if before in self.units:
                    self.rule_rank[self.units.index(before), j] = r
        self.pair_rank = self.rule_rank[self.pair_src, self.pair_trigger]
        # Postfix rules to keep at two strokes (their prefix must be omittable).
        self.pair_preferred = np.array(
            [cfg.postfix[t][b] in cfg.omit_preferred for b, t in pairs], dtype=bool
        )
        # Whether each unit has a rule for each trigger that a postfix omission may not
        # override (rules whose replacement is in omit_overridable give way).
        self.rule_blocks = self.rule_rank != NO_RULE
        for j, t in enumerate(cfg.omit_triggers):
            for before, after in cfg.postfix.get(t, {}).items():
                if before in self.units and after in cfg.omit_overridable:
                    self.rule_blocks[self.units.index(before), j] = False
        self.freq = us.freq
        self.bigram = us.bigram
        self.n_kana = us.n_kana
        self.T = cost.bigram

        self.layers = layers = cfg.layers
        self.slots = cfg.slots
        if len(self.slots) < len(self.units):
            raise ValueError(f"{len(self.units)} units do not fit in {len(self.slots)} slots")
        slot_index = {s: i for i, s in enumerate(self.slots)}
        n = len(self.slots)

        self.first = np.empty(n, dtype=int)
        self.last = np.empty(n, dtype=int)
        self.slot_cost = np.empty(n)
        for i, (layer, k) in enumerate(self.slots):
            key = KEY_INDEX[k]
            if layer == "base":
                self.first[i] = self.last[i] = key
                self.slot_cost[i] = cost.effort[key]
            elif layer == SOLO:
                end = KEY_INDEX[TERMINATOR]
                self.first[i], self.last[i] = key, end
                self.slot_cost[i] = cost.effort[key] + cost.effort[end] + cost.bigram[key, end]
            else:
                p = KEY_INDEX[layer]
                self.first[i], self.last[i] = p, key
                self.slot_cost[i] = cost.effort[p] + cost.effort[key] + cost.bigram[p, key]

        # Key without prefix, used by shadow units.
        self.key_only = np.array([KEY_INDEX[k] for _, k in self.slots], dtype=int)
        self.key_only_cost = cost.effort[self.key_only]
        # For a prefix slot, the base slot on the same key (-1 if none); -2 for base slots.
        self.base_of = np.full(n, -1)
        for i, (layer, k) in enumerate(self.slots):
            if layer == "base":
                self.base_of[i] = -2
            elif layer != SOLO and ("base", k) in slot_index:
                self.base_of[i] = slot_index[("base", k)]
        # For a prefix slot, the slots on the same key in the other prefix layers.
        others = [
            [slot_index[(q, k)] for q in cfg.prefix_keys if q != layer]
            if layer in cfg.prefix_keys
            else []
            for layer, k in self.slots
        ]
        width = max(map(len, others), default=0)
        self.siblings = np.array([o + [n] * (width - len(o)) for o in others], dtype=int)
        self.omit_idx = np.array(
            [self.units.index(k) for k in cfg.omit_units if k in self.units], dtype=int
        )
        self.is_omit = np.zeros(n_real + 1, dtype=bool)  # index -1 means "empty"
        self.is_omit[self.omit_idx] = True
        # Postfix rules (with a shift-omission trigger) that start from each unit; a
        # shift omission on the same key would override them.
        self.omit_rules = np.zeros(n_real + 1, dtype=int)  # index -1 means "empty"
        for t in cfg.omit_triggers:
            for before, after in cfg.postfix.get(t, {}).items():
                if before in self.units and after not in cfg.omit_overridable:
                    self.omit_rules[self.units.index(before)] += 1

        self.partner = np.full(n, -1)
        for i, s in enumerate(self.slots):
            t = aligned_slot(s, layers)
            if t is not None and t in slot_index:
                self.partner[i] = slot_index[t]

        ui = {u: i for i, u in enumerate(self.units)}
        self.follower_of: dict[int, int] = {}
        self.leader_of: dict[int, int] = {}
        for f, lead in cfg.constraints.aligned.items():
            if f not in ui or lead not in ui:
                raise ConstraintError(f"aligned: {f!r} = {lead!r} refers to an unknown unit")
            self.follower_of[ui[lead]] = ui[f]
            self.leader_of[ui[f]] = ui[lead]

        allowed = {
            ui[u]: {slot_index[s] for s in ss}
            for u, ss in cfg.constraints.allowed(self.units, self.slots, layers).items()
        }
        # A leader may only go where its follower's aligned slot is allowed.
        for lead, f in self.follower_of.items():
            allowed[lead] = {s for s in allowed[lead] if self.partner[s] in allowed[f]}
            if not allowed[lead]:
                raise ConstraintError(
                    f"no slot for {self.units[lead]!r} with {self.units[f]!r} aligned to it"
                )

        # Starting placement taken from an existing layout, where it is allowed.
        self.init_pos: dict[int, int] = {}
        if init is not None:
            for layer, grid in init.layers.items():
                for k, out in grid.items():
                    u, s = ui.get(out, -1), slot_index.get((layer, k), -1)
                    if u >= 0 and s >= 0 and s in allowed[u] and u not in self.leader_of:
                        self.init_pos.setdefault(u, s)
            if free is not None:
                kept = {u: s for u, s in self.init_pos.items() if self.units[u] not in free}
                for lead, f in self.follower_of.items():
                    if lead in kept:
                        kept[f] = int(self.partner[kept[lead]])
                taken = set(kept.values())
                for u in allowed:
                    allowed[u] = {kept[u]} if u in kept else allowed[u] - taken

        self.allowed = [sorted(allowed[u]) for u in range(len(self.units))]
        self.allowed_mask = np.zeros((len(self.units), n), dtype=bool)
        for u, ss in enumerate(self.allowed):
            self.allowed_mask[u, ss] = True
        self.movable_units = [
            u for u, ss in enumerate(self.allowed) if len(ss) > 1 and u not in self.leader_of
        ]

    def _occupant(self, pos: np.ndarray) -> np.ndarray:
        """Unit on each slot, -1 if empty; one extra slot at the end that is always empty."""
        occupant = np.full(len(self.slots) + 1, -1)
        occupant[pos] = np.arange(len(pos))
        return occupant

    def pair_omitted(self, pos: np.ndarray, occupant: np.ndarray) -> np.ndarray:
        """For each postfix shadow unit, whether its rule can be typed without the prefix.

        Same conditions as Layout.omitted_postfix(): the base key holds a unit that is not
        an omission unit and has no rule for the trigger (other than an overridable one), and
        no omission unit or earlier rule on the same key in another prefix layer takes that
        base unit first.
        """
        s = pos[self.pair_src]
        b = self.base_of[s]
        occ = occupant[np.where(b >= 0, b, len(self.slots))]
        ok = (b == -2) | (
            (occ >= 0) & ~self.is_omit[occ] & ~self.rule_blocks[occ, self.pair_trigger]
        )
        if self.siblings.shape[1]:
            sib = occupant[self.siblings[s]]
            earlier = self.rule_rank[sib, self.pair_trigger[:, None]] < self.pair_rank[:, None]
            ok &= ~(self.is_omit[sib] | earlier).any(axis=1)
        return ok

    def omission_violations(
        self,
        pos: np.ndarray,
        occupant: np.ndarray | None = None,
        omitted: np.ndarray | None = None,
    ) -> int:
        """Omission units on a prefix slot whose base key is empty, missing or another one,
        plus the postfix rules that the shift omissions override, plus the preferred postfix
        rules whose prefix cannot be omitted."""
        if occupant is None:
            occupant = self._occupant(pos)
        if omitted is None:
            omitted = self.pair_omitted(pos, occupant)
        preferred = int((self.pair_preferred & ~omitted).sum())
        if not len(self.omit_idx):
            return preferred
        base = self.base_of[pos[self.omit_idx]]
        if (base == -2).all():
            return preferred
        on_prefix = base != -2
        b = base[on_prefix]
        occ = occupant[np.maximum(b, 0)]
        bad = (b < 0) | (occ < 0) | self.is_omit[occ]
        overridden = self.omit_rules[occ[~bad]]
        return int(bad.sum() + overridden.sum()) + preferred

    def cost(self, pos: np.ndarray) -> float:
        occupant = self._occupant(pos)
        src = pos[self.shadow_src]
        ps = pos[self.pair_src]
        omitted = self.pair_omitted(pos, occupant)
        first = np.concatenate(
            [
                self.first[pos],
                self.key_only[src],
                np.where(omitted, self.key_only[ps], self.first[ps]),
            ]
        )
        last = np.concatenate(
            [
                self.last[pos],
                self.key_only[src],
                np.where(omitted, self.key_only[ps], self.last[ps]),
            ]
        )
        pair_cost = np.where(omitted, self.key_only_cost[ps], self.slot_cost[ps])
        unit = self.freq @ np.concatenate([self.slot_cost[pos], self.key_only_cost[src], pair_cost])
        boundary = (self.bigram * self.T[last[:, None], first[None, :]]).sum()
        violations = self.omission_violations(pos, occupant, omitted)
        return float(unit + boundary) / self.n_kana + OMISSION_PENALTY * violations

    def _initial(self, rng: random.Random, attempts: int = 200) -> np.ndarray:
        n_units, n_slots = len(self.units), len(self.slots)
        for _ in range(attempts):
            pos = np.full(n_units, -1)
            used: set[int] = set()
            # Leaders first, each taking two slots.
            leaders = list(self.follower_of)
            rng.shuffle(leaders)
            leaders.sort(key=lambda u: (u not in self.init_pos, len(self.allowed[u])))
            ok = True
            for lead in leaders:
                f = self.follower_of[lead]
                cands = [
                    s
                    for s in self.allowed[lead]
                    if s not in used
                    and self.partner[s] not in used
                    and self.allowed_mask[f, self.partner[s]]
                ]
                if not cands:
                    ok = False
                    break
                s = self.init_pos[lead] if self.init_pos.get(lead) in cands else rng.choice(cands)
                pos[lead], pos[f] = s, self.partner[s]
                used |= {s, int(self.partner[s])}
            if not ok:
                continue
            rest = [u for u in range(n_units) if pos[u] < 0]
            options = []
            for u in rest:
                ss = [s for s in self.allowed[u] if s not in used]
                rng.shuffle(ss)
                if self.init_pos.get(u) in ss:
                    ss.remove(self.init_pos[u])
                    ss.insert(0, self.init_pos[u])
                options.append(ss)
            order = sorted(
                range(len(rest)), key=lambda i: (rest[i] not in self.init_pos, len(options[i]))
            )
            try:
                sub = assign(options, n_slots, order)
            except ConstraintError:
                continue
            for i, u in enumerate(rest):
                pos[u] = sub[i]
            return pos
        raise ConstraintError("could not find a placement satisfying all constraints")

    def _try_move(self, pos, occupant, ua: int, b: int) -> dict[int, int] | None:
        """Changes {slot: new occupant} for moving `ua` to slot `b`, or None if invalid.

        The contents of the two slots are swapped. If a leader is involved, the
        contents of their aligned slots are swapped as well.
        """
        a = int(pos[ua])
        ub = int(occupant[b])
        if a == b:
            return None
        changes = {a: ub, b: ua}
        if ua in self.follower_of or ub in self.follower_of:
            pa, pb = int(self.partner[a]), int(self.partner[b])
            if pa < 0 or pb < 0:
                return None
            if pa != pb:
                if pa in changes or pb in changes:
                    return None
                changes[pa], changes[pb] = int(occupant[pb]), int(occupant[pa])

        def new_occ(s: int) -> int:
            return changes.get(s, int(occupant[s]))

        new_pos = {u: s for s, u in changes.items() if u >= 0}
        for s, u in changes.items():
            if u < 0:
                continue
            if not self.allowed_mask[u, s]:
                return None
            if u in self.leader_of:
                lead = self.leader_of[u]
                if s != self.partner[new_pos.get(lead, int(pos[lead]))]:
                    return None
            if u in self.follower_of and new_occ(int(self.partner[s])) != self.follower_of[u]:
                return None
        return changes

    def run(self, log=print, t0: float = 0.5, t1: float = 0.0005) -> tuple[np.ndarray, float]:
        if not all(self.allowed):
            raise ValueError("動かせる文字の置き場所が足りない。--free に文字を追加してください")
        rng = random.Random(self.cfg.seed)
        units = self.movable_units
        best_pos, best = None, math.inf
        for r in range(self.cfg.restarts):
            pos = self._initial(rng)
            occupant = np.full(len(self.slots), -1)
            occupant[pos] = np.arange(len(pos))
            cur = self.cost(pos)
            n = self.cfg.iterations if units else 0
            for it in range(n):
                temp = t0 * (t1 / t0) ** (it / n)
                ua = rng.choice(units)
                changes = self._try_move(pos, occupant, ua, rng.choice(self.allowed[ua]))
                if not changes:
                    continue
                old = {s: int(occupant[s]) for s in changes}
                for s, u in changes.items():
                    if u >= 0:
                        pos[u] = s
                new = self.cost(pos)
                if new <= cur or rng.random() < math.exp((cur - new) / temp):
                    cur = new
                    for s, u in changes.items():
                        occupant[s] = u
                else:
                    for s, u in old.items():
                        if u >= 0:
                            pos[u] = s
            bad = self.omission_violations(pos)
            note = f"（シフト省略の違反 {bad} 件）" if bad else ""
            log(f"restart {r + 1}/{self.cfg.restarts}: cost/kana = {cur:.4f}{note}")
            if cur < best:
                best, best_pos = cur, pos.copy()
        return best_pos, best

    def to_layout(self, pos: np.ndarray, name: str) -> Layout:
        prefix: dict = {"keys": self.cfg.prefix_keys}
        data = {
            "meta": {"name": name, "version": "0.0.0"},
            "prefix": prefix,
            "layers": {},
            "postfix": [{"trigger": t, "rules": r} for t, r in self.cfg.postfix.items()],
            "shift_omission": {
                "units": self.cfg.omit_units,
                "triggers": self.cfg.omit_triggers,
                "postfix": self.cfg.omit_postfix,
                "overridable": self.cfg.omit_overridable,
            },
        }
        grids = {layer: dict.fromkeys(KEYS, "_") for layer in ["base", *self.cfg.prefix_keys]}
        solo = {}
        for u, s in enumerate(pos):
            layer, k = self.slots[s]
            if layer == SOLO:
                solo[k] = self.units[u]
            else:
                grids[layer][k] = self.units[u]
        if solo:
            prefix["solo"] = solo
        for layer, grid in grids.items():
            data["layers"][layer] = {"rows": [" ".join(grid[k] for k in row) for row in ROWS]}
        return parse(data)
