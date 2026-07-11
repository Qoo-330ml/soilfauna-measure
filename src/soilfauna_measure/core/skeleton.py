"""Skeleton-based body-length path suggestion (pure numpy/skimage)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from skimage.morphology import skeletonize

from soilfauna_measure.core.mask_operations import ensure_binary_mask
from soilfauna_measure.core.measurement import polyline_length_px


@dataclass
class PathSuggestion:
    """Suggested length path in image coordinates."""

    points: list[list[float]]
    length_px: float
    n_skeleton_pixels: int
    message: str = ""


class PathSuggestionError(Exception):
    """Could not suggest a reliable path."""


def _neighbors8(y: int, x: int, h: int, w: int) -> list[tuple[int, int]]:
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                out.append((ny, nx))
    return out


def _build_graph(skel: np.ndarray) -> dict[tuple[int, int], list[tuple[int, int]]]:
    ys, xs = np.nonzero(skel)
    pixels = set(zip(ys.tolist(), xs.tolist()))
    graph: dict[tuple[int, int], list[tuple[int, int]]] = {}
    h, w = skel.shape
    for y, x in pixels:
        nbrs = []
        for ny, nx in _neighbors8(y, x, h, w):
            if (ny, nx) in pixels:
                nbrs.append((ny, nx))
        graph[(y, x)] = nbrs
    return graph


def _degree(graph: dict, node: tuple[int, int]) -> int:
    return len(graph.get(node, []))


def _endpoints_and_junctions(
    graph: dict[tuple[int, int], list[tuple[int, int]]],
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    ends, juncs = [], []
    for n, nbrs in graph.items():
        d = len(nbrs)
        if d == 1:
            ends.append(n)
        elif d >= 3:
            juncs.append(n)
    return ends, juncs


def _branch_length(
    graph: dict[tuple[int, int], list[tuple[int, int]]],
    start: tuple[int, int],
    prev: tuple[int, int] | None,
) -> tuple[float, list[tuple[int, int]]]:
    """Walk from start toward non-junction until end/junction; return path length in steps."""
    path = [start]
    cur = start
    p = prev
    length = 0.0
    while True:
        nbrs = [n for n in graph.get(cur, []) if n != p]
        if not nbrs:
            break
        # at junction (degree>=3) stop if not start
        if cur != start and len(graph.get(cur, [])) >= 3:
            break
        if cur != start and len(graph.get(cur, [])) == 1:
            break
        # prefer continuing along unique chain
        nxt = nbrs[0]
        if len(nbrs) > 1 and cur != start:
            # reached branch
            break
        dy = nxt[0] - cur[0]
        dx = nxt[1] - cur[1]
        length += float(np.hypot(dx, dy))
        p, cur = cur, nxt
        path.append(cur)
        if len(graph.get(cur, [])) == 1:
            break
        if len(graph.get(cur, [])) >= 3:
            break
        if len(path) > len(graph) + 2:
            break
    return length, path


def prune_short_branches(
    graph: dict[tuple[int, int], list[tuple[int, int]]],
    *,
    min_branch_length: float = 8.0,
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Remove short spurs from endpoints to first junction."""
    g = {k: list(v) for k, v in graph.items()}
    changed = True
    guard = 0
    while changed and guard < 1000:
        guard += 1
        changed = False
        ends, _ = _endpoints_and_junctions(g)
        for end in ends:
            if end not in g:
                continue
            nbrs = g[end]
            if len(nbrs) != 1:
                continue
            length, path = _branch_length(g, end, None)
            # path goes end -> ... -> junction or other end
            if length < min_branch_length and len(path) >= 2:
                # remove nodes on path except the far endpoint if it's a junction
                far = path[-1]
                keep_far = len(g.get(far, [])) >= 3
                for node in path:
                    if node == far and keep_far:
                        continue
                    if node not in g:
                        continue
                    for nb in list(g[node]):
                        if node in g.get(nb, []):
                            g[nb] = [x for x in g[nb] if x != node]
                            if not g[nb] and nb != far:
                                g.pop(nb, None)
                    g.pop(node, None)
                changed = True
                break
    # clean empty
    g = {k: [n for n in v if n in g] for k, v in g.items() if v}
    return g


def _bfs_path(
    graph: dict[tuple[int, int], list[tuple[int, int]]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]] | None:
    if start not in graph or goal not in graph:
        return None
    q = deque([start])
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for nb in graph.get(cur, []):
            if nb not in parent:
                parent[nb] = cur
                q.append(nb)
    if goal not in parent:
        return None
    path = []
    cur: tuple[int, int] | None = goal
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


def _longest_path_between_endpoints(
    graph: dict[tuple[int, int], list[tuple[int, int]]],
) -> list[tuple[int, int]]:
    ends, _ = _endpoints_and_junctions(graph)
    nodes = list(graph.keys())
    if not nodes:
        return []
    if len(nodes) == 1:
        return nodes
    if len(ends) < 2:
        # pick two farthest nodes by BFS diameter heuristic
        # from arbitrary node find farthest, then farthest from that
        start = nodes[0]
        def farthest(src: tuple[int, int]) -> tuple[tuple[int, int], list[tuple[int, int]]]:
            q = deque([src])
            parent: dict = {src: None}
            last = src
            while q:
                cur = q.popleft()
                last = cur
                for nb in graph.get(cur, []):
                    if nb not in parent:
                        parent[nb] = cur
                        q.append(nb)
            path = []
            c = last
            while c is not None:
                path.append(c)
                c = parent[c]
            path.reverse()
            return last, path

        a, _ = farthest(start)
        b, path = farthest(a)
        return path

    best: list[tuple[int, int]] = []
    best_len = -1.0
    # limit pairs if many ends
    ends_use = ends if len(ends) <= 24 else ends[:24]
    for i, e1 in enumerate(ends_use):
        for e2 in ends_use[i + 1 :]:
            path = _bfs_path(graph, e1, e2)
            if not path:
                continue
            # geometric length
            L = 0.0
            for k in range(len(path) - 1):
                dy = path[k + 1][0] - path[k][0]
                dx = path[k + 1][1] - path[k][1]
                L += float(np.hypot(dx, dy))
            if L > best_len:
                best_len = L
                best = path
    return best


def douglas_peucker(
    points: Sequence[tuple[float, float]],
    epsilon: float,
) -> list[tuple[float, float]]:
    """Simplify polyline with Ramer–Douglas–Peucker."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) < 3:
        return pts

    def _perp_dist(p, a, b) -> float:
        (x, y), (x1, y1), (x2, y2) = p, a, b
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return float(np.hypot(x - x1, y - y1))
        t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        px, py = x1 + t * dx, y1 + t * dy
        return float(np.hypot(x - px, y - py))

    def _rdp(segment: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(segment) < 3:
            return segment
        a, b = segment[0], segment[-1]
        idx = max(range(1, len(segment) - 1), key=lambda i: _perp_dist(segment[i], a, b))
        d = _perp_dist(segment[idx], a, b)
        if d > epsilon:
            left = _rdp(segment[: idx + 1])
            right = _rdp(segment[idx:])
            return left[:-1] + right
        return [a, b]

    return _rdp(pts)


def equidistant_sample(
    points: Sequence[tuple[float, float]],
    n: int,
) -> list[tuple[float, float]]:
    """Resample polyline to about n points by arc length."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) <= n or n < 2:
        return pts
    seg = [0.0]
    for i in range(1, len(pts)):
        seg.append(
            seg[-1]
            + float(np.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
        )
    total = seg[-1]
    if total <= 1e-9:
        return pts[:1] * n
    targets = [i * total / (n - 1) for i in range(n)]
    out: list[tuple[float, float]] = []
    j = 0
    for t in targets:
        while j < len(seg) - 2 and seg[j + 1] < t:
            j += 1
        s0, s1 = seg[j], seg[j + 1]
        if s1 - s0 < 1e-12:
            out.append(pts[j])
        else:
            u = (t - s0) / (s1 - s0)
            x = pts[j][0] + u * (pts[j + 1][0] - pts[j][0])
            y = pts[j][1] + u * (pts[j + 1][1] - pts[j][1])
            out.append((x, y))
    return out


def suggest_length_path(
    mask: np.ndarray,
    *,
    min_branch_length: float = 10.0,
    target_nodes: int = 8,
    simplify_epsilon: float = 1.5,
) -> PathSuggestion:
    """Skeletonize mask, prune spurs, take longest path, simplify to editable nodes.

    Coordinates returned as [x, y] image pixels.
    """
    binary = ensure_binary_mask(mask) > 0
    if not np.any(binary):
        raise PathSuggestionError("掩膜为空，无法提取骨架")

    skel = skeletonize(binary)
    if not np.any(skel):
        raise PathSuggestionError("骨架化结果为空")

    graph = _build_graph(skel)
    n_pix = len(graph)
    if n_pix == 0:
        raise PathSuggestionError("骨架无像素")

    graph = prune_short_branches(graph, min_branch_length=min_branch_length)
    if not graph:
        raise PathSuggestionError("剪枝后骨架为空（阈值过大？）")

    path_yx = _longest_path_between_endpoints(graph)
    if len(path_yx) < 2:
        # fallback: any two pixels
        nodes = list(graph.keys())
        if len(nodes) < 2:
            y, x = nodes[0]
            pts = [[float(x), float(y)]]
            return PathSuggestion(
                points=pts,
                length_px=0.0,
                n_skeleton_pixels=n_pix,
                message="骨架过短，仅生成单点",
            )
        path_yx = [nodes[0], nodes[-1]]

    # convert to (x,y)
    path_xy = [(float(x), float(y)) for y, x in path_yx]
    simplified = douglas_peucker(path_xy, simplify_epsilon)
    # then equidistant to target_nodes range 5-10
    n = max(5, min(10, int(target_nodes)))
    if len(simplified) > n:
        simplified = equidistant_sample(simplified, n)
    elif len(simplified) < 3 and len(path_xy) >= 3:
        simplified = equidistant_sample(path_xy, n)

    points = [[p[0], p[1]] for p in simplified]
    length = polyline_length_px(points)
    return PathSuggestion(
        points=points,
        length_px=length,
        n_skeleton_pixels=n_pix,
        message=f"自动建议 {len(points)} 节点（骨架 {n_pix} px，需人工确认）",
    )
