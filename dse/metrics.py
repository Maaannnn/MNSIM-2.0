#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSE metrics: Pareto dominance, hypervolume, scalarization.

All functions operate on plain tuples of floats (minimize-all convention).
No external dependencies beyond the standard library and numpy.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Pareto dominance
# ---------------------------------------------------------------------------

def dominates(a: Tuple[float, ...], b: Tuple[float, ...]) -> bool:
    """Return True if a dominates b (a ≤ b in all objectives, a < b in at least one)."""
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def pareto_indices(vectors: List[Tuple[float, ...]]) -> List[int]:
    """Return indices of non-dominated points in the given objective vectors.

    Complexity: O(n^2 * m) where n = len(vectors), m = number of objectives.
    Adequate for n < 1000 as encountered in MNSIM DSE.
    """
    nd: List[int] = []
    for i, vi in enumerate(vectors):
        dominated = any(j != i and dominates(vectors[j], vi) for j in range(len(vectors)))
        if not dominated:
            nd.append(i)
    return nd


def pareto_front(vectors: List[Tuple[float, ...]]) -> List[Tuple[float, ...]]:
    """Return the Pareto-optimal subset of vectors."""
    idx = pareto_indices(vectors)
    return [vectors[i] for i in idx]


# ---------------------------------------------------------------------------
# Hypervolume indicator (exact, no external dependencies)
# ---------------------------------------------------------------------------

def hypervolume_2d(
    points: List[Tuple[float, float]],
    ref: Tuple[float, float],
) -> float:
    """
    Exact 2D hypervolume (minimization) via sorted sweep line.

    Complexity: O(n log n).
    Reference point must be strictly worse than at least one point on each axis.
    """
    ref_y, ref_z = ref
    # Filter out points outside the reference boundary
    pts = [(y, z) for (y, z) in points if y < ref_y and z < ref_z]
    if not pts:
        return 0.0
    # Build 2D Pareto front: sort by first obj ascending, keep only improving second obj
    pts.sort(key=lambda p: p[0])
    front: List[Tuple[float, float]] = []
    min_z = float("inf")
    for y, z in pts:
        if z < min_z:
            front.append((y, z))
            min_z = z
    # Sweep: each step i covers y-interval [front[i].y, front[i+1].y) and z-height [front[i].z, ref_z)
    hv = 0.0
    for i, (y, z) in enumerate(front):
        next_y = front[i + 1][0] if i + 1 < len(front) else ref_y
        hv += (next_y - y) * (ref_z - z)
    return hv


def hypervolume_3d(
    points: List[Tuple[float, float, float]],
    ref: Tuple[float, float, float],
) -> float:
    """
    Exact 3D hypervolume (minimization) via x-axis sweep + 2D hypervolume.

    Complexity: O(n^2 log n). Fine for n < 500.
    Reference point must dominate all points (ref[i] > point[i] for all i).
    """
    ref_x, ref_y, ref_z = ref
    pts = [p for p in points if p[0] < ref_x and p[1] < ref_y and p[2] < ref_z]
    if not pts:
        return 0.0

    # Get unique x-breakpoints (sorted ascending)
    xs = sorted(set(p[0] for p in pts))

    hv = 0.0
    for j, x_j in enumerate(xs):
        x_next = xs[j + 1] if j + 1 < len(xs) else ref_x
        # Active set: all points whose x ≤ x_j dominate this x-slice [x_j, x_next)
        active_yz = [(p[1], p[2]) for p in pts if p[0] <= x_j]
        slice_hv = hypervolume_2d(active_yz, (ref_y, ref_z))
        hv += slice_hv * (x_next - x_j)
    return hv


def compute_reference_point(
    obj_vectors: List[Tuple[float, float, float]],
    inflate: float = 1.1,
) -> Tuple[float, float, float]:
    """
    Compute a hypervolume reference point from a set of objective vectors.

    Uses coordinate-wise maximum inflated by `inflate` factor.
    The reference point is guaranteed to be dominated by all given points.
    """
    if not obj_vectors:
        raise ValueError("Cannot compute reference point from empty list.")
    max_lat = max(v[0] for v in obj_vectors)
    max_en = max(v[1] for v in obj_vectors)
    max_area = max(v[2] for v in obj_vectors)
    return (max_lat * inflate, max_en * inflate, max_area * inflate)


# ---------------------------------------------------------------------------
# Scalarization functions
# ---------------------------------------------------------------------------

def scalarize_log(
    obj_vec: Tuple[float, float, float],
    weights: Tuple[float, float, float],
) -> float:
    """
    Weighted log scalarization for single-objective BO.

    f = w_lat * log1p(lat) + w_en * log1p(en) + w_area * log1p(area)

    log1p ensures numerical stability for very large values.
    """
    w_l, w_e, w_a = weights
    return w_l * math.log1p(obj_vec[0]) + w_e * math.log1p(obj_vec[1]) + w_a * math.log1p(obj_vec[2])


def tchebycheff_normalized(
    Y_norm: "np.ndarray",
    w: "np.ndarray",
    rho: float = 0.05,
) -> "np.ndarray":
    """
    Tchebycheff (Chebyshev) scalarization for ParEGO MOBO.

    Y_norm: (n_points, n_objectives) array, normalized to [0,1].
    w: weight vector (sums to 1), sampled from Dirichlet each BO iteration.
    rho: augmentation coefficient for diversity (default 0.05).

    Returns scalar value per point to minimize.
    """
    z = np.zeros(Y_norm.shape[1])  # ideal point at origin after normalization
    return np.max(w * np.abs(Y_norm - z), axis=1) + rho * np.sum(w * Y_norm, axis=1)


def normalize_objectives(Y: "np.ndarray") -> "np.ndarray":
    """Normalize objective matrix to [0,1] range per column."""
    y_min = Y.min(axis=0)
    y_max = Y.max(axis=0)
    span = np.maximum(y_max - y_min, 1e-12)
    return (Y - y_min) / span


# ---------------------------------------------------------------------------
# NSGA-II selection utilities
# ---------------------------------------------------------------------------

def non_dominated_sort(
    vectors: List[Tuple[float, ...]],
) -> List[List[int]]:
    """
    Fast non-dominated sort for NSGA-II.

    Returns a list of fronts (each front is a list of indices into vectors).
    Front 0 = Pareto front.
    """
    n = len(vectors)
    dominated_by = [[] for _ in range(n)]   # s[p]: set of solutions p dominates
    domination_count = [0] * n              # n[p]: how many solutions dominate p
    fronts: List[List[int]] = [[]]

    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if dominates(vectors[p], vectors[q]):
                dominated_by[p].append(q)
            elif dominates(vectors[q], vectors[p]):
                domination_count[p] += 1
        if domination_count[p] == 0:
            fronts[0].append(p)

    i = 0
    while fronts[i]:
        nxt: List[int] = []
        for p in fronts[i]:
            for q in dominated_by[p]:
                domination_count[q] -= 1
                if domination_count[q] == 0:
                    nxt.append(q)
        i += 1
        fronts.append(nxt)

    if not fronts[-1]:
        fronts.pop()
    return fronts


def crowding_distance(
    front: List[int],
    vectors: List[Tuple[float, ...]],
) -> dict:
    """Compute crowding distance for a single NSGA-II front."""
    if not front:
        return {}
    m = len(vectors[0])
    dist = {i: 0.0 for i in front}
    for obj_idx in range(m):
        sorted_front = sorted(front, key=lambda i: vectors[i][obj_idx])
        dist[sorted_front[0]] = float("inf")
        dist[sorted_front[-1]] = float("inf")
        v_min = vectors[sorted_front[0]][obj_idx]
        v_max = vectors[sorted_front[-1]][obj_idx]
        if v_max == v_min:
            continue
        for k in range(1, len(sorted_front) - 1):
            prev_v = vectors[sorted_front[k - 1]][obj_idx]
            next_v = vectors[sorted_front[k + 1]][obj_idx]
            dist[sorted_front[k]] += (next_v - prev_v) / (v_max - v_min)
    return dist


def nsga2_select(
    pop: List[int],
    vectors: List[Tuple[float, ...]],
    n_select: int,
) -> List[int]:
    """
    NSGA-II survivor selection.

    Selects n_select indices from pop using non-dominated rank + crowding distance.
    vectors[i] is the objective vector for individual i.
    """
    fronts = non_dominated_sort([vectors[i] for i in pop])
    # fronts contain relative indices within pop — convert to absolute
    abs_fronts = [[pop[i] for i in front] for front in fronts]

    selected: List[int] = []
    for front in abs_fronts:
        if len(selected) + len(front) <= n_select:
            selected.extend(front)
        else:
            remain = n_select - len(selected)
            cd = crowding_distance(front, vectors)
            selected.extend(sorted(front, key=lambda i: cd[i], reverse=True)[:remain])
            break
    return selected
