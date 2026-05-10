"""
1D cutting-stock optimizer.

Primary algorithm: First / Best Fit Decreasing (FFD/BFD) heuristic.
  - O(n²), runs in milliseconds for hundreds of pieces.
  - Typically within 2–5% of provably optimal.

CP-SAT (pack_pieces) is kept as an optional polisher for small instances
(≤ CP_SAT_THRESHOLD pieces) where it can verify / tighten the FFD result.

Public API
----------
pack_pieces(piece_lengths, stock_length, kerf, time_limit_s) -> (bars, status)
optimize(pieces, max_stock_length, kerf, max_distinct_lengths, time_limit_s) -> Solution
recommend(pieces, max_stock_length, kerf, distinct_penalty_pct, time_limit_s) -> list[Solution]
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Optional

from ortools.sat.python import cp_model


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Solution:
    stock_lengths: list[int]
    bar_counts: list[int]
    cutting_plan: list[tuple[int, list[int]]]  # (stock_length, pieces_in_bar)
    total_ordered_mm: int
    total_used_mm: int
    total_waste_mm: int
    utilization_pct: float
    distinct_count: int
    solver_status: str = "HEURISTIC"


# Above this piece count, skip CP-SAT polish — it won't finish in time.
CP_SAT_THRESHOLD = 50


# ---------------------------------------------------------------------------
# FFD — single stock length
# ---------------------------------------------------------------------------

def ffd_pack(piece_lengths: list[int], stock_length: int, kerf: int) -> list[list[int]]:
    """
    First Fit Decreasing bin packing for a single stock length.

    Pieces are sorted largest-first and placed into the first bin with enough
    remaining space. Each cut after the first in a bar consumes `kerf` mm.

    Returns a list of bars; each bar is a list of piece lengths.
    """
    sorted_pieces = sorted(piece_lengths, reverse=True)
    bins: list[list[int]] = []
    remaining: list[int] = []

    for piece in sorted_pieces:
        placed = False
        for i in range(len(bins)):
            # Every piece added to an existing bin needs one kerf cut before it
            if remaining[i] >= kerf + piece:
                bins[i].append(piece)
                remaining[i] -= kerf + piece
                placed = True
                break
        if not placed:
            bins.append([piece])
            remaining.append(stock_length - piece)

    return bins


# ---------------------------------------------------------------------------
# BFD — multiple stock lengths
# ---------------------------------------------------------------------------

def bfd_multi_pack(
    piece_lengths: list[int],
    stock_lengths: list[int],
    kerf: int,
) -> list[tuple[int, list[int]]]:
    """
    Best Fit Decreasing across multiple stock lengths.

    Each piece is placed into the existing open bin (of any class) that leaves
    the least remaining space while still fitting.  If no open bin fits, a new
    bin is opened using the smallest stock length that can accommodate the piece.

    This keeps short pieces away from large bars and generally achieves higher
    utilization than single-class FFD on either length alone.
    """
    sorted_pieces = sorted(piece_lengths, reverse=True)
    sorted_stocks = sorted(stock_lengths)
    # state per bin: [stock_length, pieces, remaining_space]
    bins: list[list] = []

    for piece in sorted_pieces:
        best_idx = -1
        best_leftover = float("inf")

        for i, (sl, pieces, rem) in enumerate(bins):
            needed = kerf + piece
            if rem >= needed:
                leftover = rem - needed
                if leftover < best_leftover:
                    best_idx = i
                    best_leftover = leftover

        if best_idx >= 0:
            sl, pieces, rem = bins[best_idx]
            bins[best_idx] = [sl, pieces + [piece], rem - kerf - piece]
        else:
            # Open a new bin with the smallest stock length that fits
            for sl in sorted_stocks:
                if sl >= piece:
                    bins.append([sl, [piece], sl - piece])
                    break
            else:
                raise ValueError(f"No stock length fits piece {piece} mm")

    return [(b[0], b[1]) for b in bins if b[1]]


# ---------------------------------------------------------------------------
# CP-SAT bin packing (optional polisher for small instances)
# ---------------------------------------------------------------------------

def pack_pieces(
    piece_lengths: list[int],
    stock_length: int,
    kerf: int,
    time_limit_s: float = 5.0,
) -> tuple[list[list[int]], str]:
    """
    CP-SAT bin packing — minimizes number of bars used.  Provably optimal for
    small instances; use only when len(piece_lengths) <= CP_SAT_THRESHOLD.

    Capacity constraint per bar:
        sum(pieces) + (count_in_bar - 1) * kerf <= stock_length
    """
    n = len(piece_lengths)
    if n == 0:
        return [], "OPTIMAL"

    max_bins = n
    model = cp_model.CpModel()

    x = [
        [model.new_bool_var(f"x_{i}_{j}") for j in range(max_bins)]
        for i in range(n)
    ]
    y = [model.new_bool_var(f"y_{j}") for j in range(max_bins)]

    for i in range(n):
        model.add(sum(x[i][j] for j in range(max_bins)) == 1)

    for j in range(max_bins):
        pieces_in_bin = [x[i][j] * piece_lengths[i] for i in range(n)]
        count_in_bin = sum(x[i][j] for i in range(n))
        # Equivalent to sum(pieces) + (count-1)*kerf <= stock_length
        model.add(sum(pieces_in_bin) + count_in_bin * kerf <= stock_length + kerf)

    for i in range(n):
        for j in range(max_bins):
            model.add(x[i][j] <= y[j])

    for j in range(1, max_bins):
        model.add(y[j] <= y[j - 1])

    model.minimize(sum(y))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], status_name

    bars: list[list[int]] = []
    for j in range(max_bins):
        if solver.value(y[j]) == 1:
            bar_pieces = [
                piece_lengths[i] for i in range(n) if solver.value(x[i][j]) == 1
            ]
            if bar_pieces:
                bars.append(bar_pieces)

    return bars, status_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expand_pieces(pieces: list[tuple[int, int]]) -> list[int]:
    result: list[int] = []
    for length, qty in pieces:
        result.extend([length] * qty)
    return result


def _make_solution(
    stock_lengths: list[int],
    cutting_plan: list[tuple[int, list[int]]],
    solver_status: str,
) -> Solution:
    bar_counts = [
        sum(1 for sl2, _ in cutting_plan if sl2 == sl)
        for sl in stock_lengths
    ]
    total_ordered = sum(sl for sl, _ in cutting_plan)
    total_used = sum(sum(pieces) for _, pieces in cutting_plan)
    waste = total_ordered - total_used
    util = (total_used / total_ordered * 100) if total_ordered > 0 else 0.0

    return Solution(
        stock_lengths=stock_lengths,
        bar_counts=bar_counts,
        cutting_plan=cutting_plan,
        total_ordered_mm=total_ordered,
        total_used_mm=total_used,
        total_waste_mm=waste,
        utilization_pct=round(util, 2),
        distinct_count=len(stock_lengths),
        solver_status=solver_status,
    )


def _round_up(value: int, step: int) -> int:
    return ((value + step - 1) // step) * step


def _k1_ffd_only(flat_pieces: list[int], max_stock_length: int, kerf: int) -> int:
    """Return the best single stock length found by FFD sweep (no CP-SAT polish)."""
    min_length = max(flat_pieces)
    candidates = list(range(min_length, max_stock_length + 1, 10))
    if not candidates or candidates[-1] != max_stock_length:
        candidates.append(max_stock_length)

    best_util = -1.0
    best_length = max_stock_length

    for L in candidates:
        bars = ffd_pack(flat_pieces, L, kerf)
        total_ordered = L * len(bars)
        total_used = sum(sum(b) for b in bars)
        util = total_used / total_ordered if total_ordered else 0.0
        if util > best_util or (util == best_util and L < best_length):
            best_util = util
            best_length = L

    return best_length


# ---------------------------------------------------------------------------
# k = 1 optimizer
# ---------------------------------------------------------------------------

def _optimize_k1(
    flat_pieces: list[int],
    max_stock_length: int,
    kerf: int,
    time_limit_s: float,
) -> Solution:
    """
    Enumerate every candidate stock length from max(pieces) to max_stock_length
    in 10 mm steps using FFD.  Pick the length with the highest utilization
    (ties broken by shorter length — cheaper to transport).

    For small instances, optionally polish the FFD winner with CP-SAT.
    """
    min_length = max(flat_pieces)
    candidates = list(range(min_length, max_stock_length + 1, 10))
    if not candidates or candidates[-1] != max_stock_length:
        candidates.append(max_stock_length)

    best: Optional[Solution] = None

    for L in candidates:
        bars = ffd_pack(flat_pieces, L, kerf)
        plan = [(L, b) for b in bars]
        sol = _make_solution([L], plan, "HEURISTIC")
        if best is None or sol.utilization_pct > best.utilization_pct:
            best = sol
        elif sol.utilization_pct == best.utilization_pct and L < best.stock_lengths[0]:
            best = sol

    assert best is not None

    # CP-SAT polish: for small instances, verify the FFD bar count can be reduced
    if len(flat_pieces) <= CP_SAT_THRESHOLD and time_limit_s > 2:
        L = best.stock_lengths[0]
        bars_cp, status = pack_pieces(flat_pieces, L, kerf, time_limit_s=time_limit_s * 0.6)
        if bars_cp:
            plan_cp = [(L, b) for b in bars_cp]
            sol_cp = _make_solution([L], plan_cp, status)
            if sol_cp.utilization_pct >= best.utilization_pct:
                best = sol_cp

    return best


# ---------------------------------------------------------------------------
# k = 2 / k = 3 optimizer
# ---------------------------------------------------------------------------

def _optimize_k_multi(
    flat_pieces: list[int],
    max_stock_length: int,
    kerf: int,
    k: int,
    time_limit_s: float,
) -> Solution:
    """
    Enumerate combinations of k stock lengths on a coarse grid (50 mm for k=2,
    100 mm for k=3) and solve each with BFD multi-pack.  Return the combination
    that minimises total ordered material.

    FFD runs in microseconds per combination, so even thousands of combos
    complete in well under a second.
    """
    # Anchor the grid with the k=1 FFD winner so k>1 solutions are never worse
    k1_length = _k1_ffd_only(flat_pieces, max_stock_length, kerf)

    min_length = max(flat_pieces)
    step = 50 if k == 2 else 100
    candidates_set = set(range(_round_up(min_length, step), max_stock_length + 1, step))
    candidates_set.add(max_stock_length)
    candidates_set.add(k1_length)
    candidates = sorted(candidates_set)

    best: Optional[Solution] = None

    for combo in itertools.combinations_with_replacement(candidates, k):
        try:
            plan = bfd_multi_pack(flat_pieces, list(combo), kerf)
        except ValueError:
            continue
        used_lengths = sorted(set(sl for sl, _ in plan))
        sol = _make_solution(used_lengths, plan, "HEURISTIC")
        if best is None or sol.total_ordered_mm < best.total_ordered_mm:
            best = sol

    # Fallback to k=1 if nothing was found (shouldn't happen with valid inputs)
    if best is None:
        return _optimize_k1(flat_pieces, max_stock_length, kerf, time_limit_s)

    return best


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def optimize(
    pieces: list[tuple[int, int]],
    max_stock_length: int,
    kerf: int,
    max_distinct_lengths: int,
    time_limit_s: float = 30.0,
) -> Solution:
    """
    Find an optimal (or near-optimal) cutting plan for the given pieces.

    pieces               — list of (length_mm, quantity)
    max_stock_length     — maximum bar length to consider (mm)
    kerf                 — saw kerf width (mm)
    max_distinct_lengths — 1, 2, or 3
    time_limit_s         — used only for the CP-SAT polish on small instances
    """
    flat = _expand_pieces(pieces)
    if not flat:
        raise ValueError("No pieces provided")
    if max(flat) > max_stock_length:
        raise ValueError(
            f"Piece {max(flat)} mm exceeds max stock length {max_stock_length} mm"
        )

    if max_distinct_lengths == 1:
        return _optimize_k1(flat, max_stock_length, kerf, time_limit_s)
    return _optimize_k_multi(flat, max_stock_length, kerf, max_distinct_lengths, time_limit_s)


def recommend(
    pieces: list[tuple[int, int]],
    max_stock_length: int,
    kerf: int,
    distinct_penalty_pct: float = 1.5,
    time_limit_s: float = 30.0,
) -> list[Solution]:
    """
    Run optimize for k = 1, 2, 3.  Return all three Solutions sorted by:

        score = utilization_pct − distinct_penalty_pct × (k − 1)

    The first element is the recommendation.  Default penalty of 1.5 % means
    adding one more distinct SKU must recover more than 1.5 pp of utilization
    to be recommended over the simpler option.
    """
    flat = _expand_pieces(pieces)
    if not flat:
        raise ValueError("No pieces provided")

    solutions: list[Solution] = []
    time_per_k = time_limit_s / 3

    for k in (1, 2, 3):
        try:
            sol = optimize(pieces, max_stock_length, kerf, k, time_per_k)
            solutions.append(sol)
        except Exception:
            pass

    def score(sol: Solution) -> float:
        return sol.utilization_pct - distinct_penalty_pct * (sol.distinct_count - 1)

    solutions.sort(key=score, reverse=True)
    return solutions
