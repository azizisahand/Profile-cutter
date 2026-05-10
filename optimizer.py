"""
1D cutting-stock optimizer using Google OR-Tools CP-SAT.

Public API
----------
pack_pieces(piece_lengths, stock_length, kerf, time_limit_s) -> (bars, status)
optimize(pieces, max_stock_length, kerf, max_distinct_lengths, time_limit_s) -> Solution
recommend(pieces, max_stock_length, kerf, distinct_penalty_pct, time_limit_s) -> list[Solution]
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Optional

from ortools.sat.python import cp_model


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Solution:
    stock_lengths: list[int]
    bar_counts: list[int]
    cutting_plan: list[tuple[int, list[int]]]  # (stock_length, [piece, ...])
    total_ordered_mm: int
    total_used_mm: int
    total_waste_mm: int
    utilization_pct: float
    distinct_count: int
    solver_status: str = "OPTIMAL"


# ---------------------------------------------------------------------------
# Core bin-packing subroutine (single stock length)
# ---------------------------------------------------------------------------

def pack_pieces(
    piece_lengths: list[int],
    stock_length: int,
    kerf: int,
    time_limit_s: float = 5.0,
) -> tuple[list[list[int]], str]:
    """
    Assign piece_lengths to the minimum number of bars of stock_length.

    Capacity constraint per bar:
        sum(pieces in bar) + (count_in_bar - 1) * kerf <= stock_length

    Returns (bars, status_string).
    bars is a list of lists; each inner list contains the piece lengths assigned
    to one bar.
    """
    n = len(piece_lengths)
    if n == 0:
        return [], "OPTIMAL"

    # Upper bound on bins needed: one piece per bar
    max_bins = n

    model = cp_model.CpModel()

    # x[i][j] = 1  piece i goes into bin j
    x = [[model.new_bool_var(f"x_{i}_{j}") for j in range(max_bins)] for i in range(n)]
    # y[j] = 1  bin j is used
    y = [model.new_bool_var(f"y_{j}") for j in range(max_bins)]

    # Each piece is assigned to exactly one bin
    for i in range(n):
        model.add(sum(x[i][j] for j in range(max_bins)) == 1)

    # Capacity + kerf constraint per bin
    for j in range(max_bins):
        pieces_in_bin = [x[i][j] * piece_lengths[i] for i in range(n)]
        count_in_bin = sum(x[i][j] for i in range(n))
        # sum(lengths) + (count - 1)*kerf <= stock_length
        # sum(lengths) + count*kerf - kerf <= stock_length
        # sum(lengths) + count*kerf <= stock_length + kerf
        model.add(
            sum(pieces_in_bin) + count_in_bin * kerf <= stock_length + kerf
        )

    # If any piece is in bin j, y[j] must be 1
    for i in range(n):
        for j in range(max_bins):
            model.add(x[i][j] <= y[j])

    # Symmetry-breaking: bin j can only be used if bin j-1 is used
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
                piece_lengths[i]
                for i in range(n)
                if solver.value(x[i][j]) == 1
            ]
            if bar_pieces:
                bars.append(bar_pieces)

    return bars, status_name


# ---------------------------------------------------------------------------
# Helper: flatten piece list and check feasibility
# ---------------------------------------------------------------------------

def _expand_pieces(pieces: list[tuple[int, int]]) -> list[int]:
    """Expand (length, qty) pairs into a flat list."""
    result = []
    for length, qty in pieces:
        result.extend([length] * qty)
    return result


def _make_solution(
    stock_lengths: list[int],
    cutting_plan: list[tuple[int, list[int]]],
    solver_status: str,
) -> Solution:
    bar_counts: list[int] = []
    for sl in stock_lengths:
        count = sum(1 for sl2, _ in cutting_plan if sl2 == sl)
        bar_counts.append(count)

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


# ---------------------------------------------------------------------------
# Single-length optimizer (k=1)
# ---------------------------------------------------------------------------

def _optimize_k1(
    flat_pieces: list[int],
    max_stock_length: int,
    kerf: int,
    time_limit_s: float,
) -> Solution:
    min_length = max(flat_pieces)
    candidates = list(range(min_length, max_stock_length + 1, 10))
    if not candidates or candidates[-1] != max_stock_length:
        candidates.append(max_stock_length)
    # Keep only candidates >= longest piece (already ensured by range start)

    best: Optional[Solution] = None
    deadline = time.monotonic() + time_limit_s

    for L in candidates:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        bars, status = pack_pieces(flat_pieces, L, kerf, time_limit_s=min(remaining, 5.0))
        if not bars:
            continue
        plan = [(L, b) for b in bars]
        sol = _make_solution([L], plan, status)
        if best is None or sol.utilization_pct > best.utilization_pct:
            best = sol
        elif sol.utilization_pct == best.utilization_pct and L < best.stock_lengths[0]:
            best = sol

    if best is None:
        # Fallback: single large bar
        bars, status = pack_pieces(flat_pieces, max_stock_length, kerf, time_limit_s=5.0)
        plan = [(max_stock_length, b) for b in bars]
        best = _make_solution([max_stock_length], plan, status)

    return best


# ---------------------------------------------------------------------------
# Multi-length optimizer (k=2 or k=3)
# ---------------------------------------------------------------------------

def _pack_multi(
    flat_pieces: list[int],
    stock_lengths: list[int],
    kerf: int,
    time_limit_s: float,
) -> tuple[list[tuple[int, list[int]]], str]:
    """
    Assign each piece to one of the given stock lengths, then bin-pack within
    each class. Uses CP-SAT to minimize total ordered material.
    """
    k = len(stock_lengths)
    n = len(flat_pieces)
    max_bins_per_class = n  # pessimistic upper bound

    model = cp_model.CpModel()

    # assign[i][c] = 1  piece i uses stock class c
    assign = [
        [model.new_bool_var(f"a_{i}_{c}") for c in range(k)]
        for i in range(n)
    ]
    for i in range(n):
        model.add(sum(assign[i][c] for c in range(k)) == 1)
        # A piece cannot be assigned to a class shorter than itself
        for c, L in enumerate(stock_lengths):
            if flat_pieces[i] > L:
                model.add(assign[i][c] == 0)

    # Bin variables per class: x[c][i][j], y[c][j]
    x: list[list[list]] = []
    y: list[list] = []
    for c in range(k):
        xc = [
            [model.new_bool_var(f"x_{c}_{i}_{j}") for j in range(max_bins_per_class)]
            for i in range(n)
        ]
        yc = [model.new_bool_var(f"y_{c}_{j}") for j in range(max_bins_per_class)]
        x.append(xc)
        y.append(yc)

    for c in range(k):
        L = stock_lengths[c]
        for i in range(n):
            # x[c][i][j] <= assign[i][c]  (can only use bins of class c if assigned there)
            for j in range(max_bins_per_class):
                model.add(x[c][i][j] <= assign[i][c])
            # piece i is in exactly one bin of class c if assigned to c, else 0 bins
            model.add(
                sum(x[c][i][j] for j in range(max_bins_per_class)) == assign[i][c]
            )

        for j in range(max_bins_per_class):
            # Capacity
            pieces_in_bin = [x[c][i][j] * flat_pieces[i] for i in range(n)]
            count_in_bin = sum(x[c][i][j] for i in range(n))
            model.add(
                sum(pieces_in_bin) + count_in_bin * kerf <= L + kerf
            )
            # y[c][j] = 1 iff bin j of class c has at least one piece
            for i in range(n):
                model.add(x[c][i][j] <= y[c][j])
        # Symmetry
        for j in range(1, max_bins_per_class):
            model.add(y[c][j] <= y[c][j - 1])

    # Objective: minimize total ordered material
    total_ordered = sum(
        y[c][j] * stock_lengths[c]
        for c in range(k)
        for j in range(max_bins_per_class)
    )
    model.minimize(total_ordered)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], status_name

    plan: list[tuple[int, list[int]]] = []
    for c in range(k):
        L = stock_lengths[c]
        for j in range(max_bins_per_class):
            if solver.value(y[c][j]) == 1:
                bar_pieces = [
                    flat_pieces[i]
                    for i in range(n)
                    if solver.value(x[c][i][j]) == 1
                ]
                if bar_pieces:
                    plan.append((L, bar_pieces))

    return plan, status_name


def _optimize_k_multi(
    flat_pieces: list[int],
    max_stock_length: int,
    kerf: int,
    k: int,
    time_limit_s: float,
) -> Solution:
    min_length = max(flat_pieces)
    step = 50 if k == 2 else 100
    candidates = list(range(
        _round_up(min_length, step),
        max_stock_length + 1,
        step,
    ))
    if not candidates or candidates[-1] != max_stock_length:
        candidates.append(max_stock_length)

    combos = list(itertools.combinations_with_replacement(candidates, k))
    deadline = time.monotonic() + time_limit_s

    best: Optional[Solution] = None

    for combo in combos:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        tl = min(remaining / max(1, len(combos) - combos.index(combo)), 8.0)
        plan, status = _pack_multi(flat_pieces, list(combo), kerf, tl)
        if not plan:
            continue
        used_lengths = sorted(set(sl for sl, _ in plan))
        sol = _make_solution(used_lengths, plan, status)
        if best is None or sol.total_ordered_mm < best.total_ordered_mm:
            best = sol

    if best is None:
        # Fallback to k=1
        return _optimize_k1(flat_pieces, max_stock_length, kerf, time_limit_s)

    return best


def _round_up(value: int, step: int) -> int:
    return ((value + step - 1) // step) * step


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
    Find optimal cutting plan for the given pieces.

    pieces: list of (length_mm, quantity)
    max_distinct_lengths: 1, 2, or 3
    """
    flat = _expand_pieces(pieces)
    if not flat:
        raise ValueError("No pieces provided")
    if max(flat) > max_stock_length:
        raise ValueError(
            f"Piece length {max(flat)} mm exceeds max stock length {max_stock_length} mm"
        )

    if max_distinct_lengths == 1:
        return _optimize_k1(flat, max_stock_length, kerf, time_limit_s)
    else:
        return _optimize_k_multi(flat, max_stock_length, kerf, max_distinct_lengths, time_limit_s)


def recommend(
    pieces: list[tuple[int, int]],
    max_stock_length: int,
    kerf: int,
    distinct_penalty_pct: float = 1.5,
    time_limit_s: float = 30.0,
) -> list[Solution]:
    """
    Run optimize for k=1, 2, 3 and return solutions sorted by score.

    score = utilization_pct - distinct_penalty_pct * (k - 1)
    Higher score = better recommendation (first element is recommended).
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
