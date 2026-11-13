"""A path cut where it runs through boxes: the parts inside are taken out, exactly at the boxes'
edges, and what is left outside is drawn as it was."""

from dataclasses import dataclass, field
from itertools import pairwise

Point = tuple[float, float]
Box = tuple[float, float, float, float]
Matrix = tuple[float, float, float, float, float, float]
# A segment is its end point, or a cubic curve's two control points and its end point.
Segment = tuple[Point] | tuple[Point, Point, Point]

EPSILON = 1e-9


@dataclass
class Subpath:
    start: Point
    segments: list[Segment] = field(default_factory=list)
    closed: bool = False

    def end(self) -> Point:
        return self.segments[-1][-1] if self.segments else self.start


IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def multiply(first: Matrix, then: Matrix) -> Matrix:
    """The matrix that applies first and then then, as PDF writes first × then."""
    a, b, c, d, e, f = first
    a2, b2, c2, d2, e2, f2 = then
    return (
        a * a2 + b * c2,
        a * b2 + b * d2,
        c * a2 + d * c2,
        c * b2 + d * d2,
        e * a2 + f * c2 + e2,
        e * b2 + f * d2 + f2,
    )


def inverse(matrix: Matrix) -> Matrix | None:
    a, b, c, d, e, f = matrix
    determinant = a * d - b * c
    if abs(determinant) < 1e-12:
        return None
    return (
        d / determinant,
        -b / determinant,
        -c / determinant,
        a / determinant,
        (c * f - d * e) / determinant,
        (b * e - a * f) / determinant,
    )


def apply(matrix: Matrix, point: Point) -> Point:
    a, b, c, d, e, f = matrix
    x, y = point
    return a * x + c * y + e, b * x + d * y + f


def corners(box: Box, matrix: Matrix = IDENTITY) -> list[Point]:
    left, bottom, right, top = box
    return [
        apply(matrix, point)
        for point in ((left, bottom), (right, bottom), (right, top), (left, top))
    ]


def enclosing(points: list[Point]) -> Box:
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def overlap(first: Box, second: Box) -> bool:
    return (
        first[0] < second[2]
        and second[0] < first[2]
        and first[1] < second[3]
        and second[1] < first[3]
    )


def covered(box: Box, boxes: list[Box]) -> float:
    """How much of the box lies under the boxes; for a box of no area, whether its middle does."""
    left, bottom, right, top = box
    area = (right - left) * (top - bottom)
    if area <= 1e-9:
        x, y = (left + right) / 2, (bottom + top) / 2
        return 1.0 if any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes) else 0.0
    under = sum(
        max(0.0, min(right, b[2]) - max(left, b[0])) * max(0.0, min(top, b[3]) - max(bottom, b[1]))
        for b in boxes
    )
    return min(1.0, under / area)


def clipped(polygon: list[Point], box: Box) -> list[Point]:
    """The part of a convex polygon inside the box."""
    left, bottom, right, top = box
    for axis, level, keep_above in (
        (0, left, True),
        (0, right, False),
        (1, bottom, True),
        (1, top, False),
    ):
        if not polygon:
            break
        kept: list[Point] = []
        for index, point in enumerate(polygon):
            before = polygon[index - 1]
            inside = point[axis] >= level if keep_above else point[axis] <= level
            was = before[axis] >= level if keep_above else before[axis] <= level
            if inside != was:
                t = (level - before[axis]) / (point[axis] - before[axis])
                kept.append(
                    (before[0] + (point[0] - before[0]) * t, before[1] + (point[1] - before[1]) * t)
                )
            if inside:
                kept.append(point)
        polygon = kept
    return polygon


def transformed(subpaths: list[Subpath], matrix: Matrix) -> list[Subpath]:
    return [
        Subpath(
            apply(matrix, each.start),
            [tuple(apply(matrix, point) for point in segment) for segment in each.segments],
            each.closed,
        )
        for each in subpaths
    ]


def drawn(subpaths: list[Subpath]) -> list[tuple[list[float], str]]:
    """The subpaths as the operators that construct them."""
    made: list[tuple[list[float], str]] = []
    for each in subpaths:
        made.append(([*each.start], "m"))
        for segment in each.segments:
            made.append(
                ([value for point in segment for value in point], "l" if len(segment) == 1 else "c")
            )
        if each.closed:
            made.append(([], "h"))
    return made


def bounds(subpaths: list[Subpath]) -> Box | None:
    points = [
        point for each in subpaths for point in (each.start, *(p for s in each.segments for p in s))
    ]
    return enclosing(points) if points else None


def _bezier(points: tuple[Point, Point, Point, Point], t: float) -> Point:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    u = 1 - t
    return (
        u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
        u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3,
    )


def _split(points: tuple[Point, ...], t: float) -> tuple[tuple[Point, ...], tuple[Point, ...]]:
    """A cubic curve's two parts on either side of t, by de Casteljau."""

    def between(p: Point, q: Point) -> Point:
        return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t

    p0, p1, p2, p3 = points
    a, b, c = between(p0, p1), between(p1, p2), between(p2, p3)
    d, e = between(a, b), between(b, c)
    m = between(d, e)
    return (p0, a, d, m), (m, e, c, p3)


def _roots(values: tuple[float, float, float, float], level: float) -> list[float]:
    """Where in (0, 1) a cubic curve's coordinate, given by its four control values, meets level."""
    p0, p1, p2, p3 = (value - level for value in values)
    a = -p0 + 3 * p1 - 3 * p2 + p3
    b = 3 * p0 - 6 * p1 + 3 * p2
    c = -3 * p0 + 3 * p1
    d = p0

    def at(t: float) -> float:
        return ((a * t + b) * t + c) * t + d

    turns = [0.0, 1.0]
    # The derivative's zeros cut (0, 1) into stretches where the coordinate only rises or falls.
    qa, qb, qc = 3 * a, 2 * b, c
    if abs(qa) > EPSILON:
        disc = qb * qb - 4 * qa * qc
        if disc >= 0:
            root = disc**0.5
            turns += [(-qb - root) / (2 * qa), (-qb + root) / (2 * qa)]
    elif abs(qb) > EPSILON:
        turns.append(-qc / qb)
    turns = sorted(t for t in turns if 0 <= t <= 1)
    found = []
    for low, high in pairwise(turns):
        f_low, f_high = at(low), at(high)
        if f_low == 0 and 0 < low < 1:
            found.append(low)
        if f_low * f_high >= 0:
            continue
        for _ in range(60):
            middle = (low + high) / 2
            if (at(middle) < 0) == (f_low < 0):
                low, f_low = middle, at(middle)
            else:
                high = middle
        found.append((low + high) / 2)
    return [t for t in found if EPSILON < t < 1 - EPSILON]


def _inside(point: Point, box: Box) -> bool:
    x, y = point
    left, bottom, right, top = box
    return left + EPSILON < x < right - EPSILON and bottom + EPSILON < y < top - EPSILON


def _pieces(start: Point, segment: Segment, box: Box) -> list[tuple[Point, Segment, bool]]:
    """The segment cut at the box's edges: each piece's start, the piece, and whether it lies in
    the box."""
    left, bottom, right, top = box
    if len(segment) == 1:
        (end,) = segment
        cuts = []
        for axis, levels in ((0, (left, right)), (1, (bottom, top))):
            span = end[axis] - start[axis]
            if abs(span) > EPSILON:
                cuts += [(level - start[axis]) / span for level in levels]
        cuts = sorted({t for t in cuts if EPSILON < t < 1 - EPSILON})
        marks = [0.0, *cuts, 1.0]
        points = [
            (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t) for t in marks
        ]
        return [
            (p, (q,), _inside(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), box))
            for p, q in pairwise(points)
        ]
    curve = (start, *segment)
    cuts = sorted(
        {
            t
            for axis, levels in ((0, (left, right)), (1, (bottom, top)))
            for level in levels
            for t in _roots(tuple(point[axis] for point in curve), level)
        }
    )
    found, rest, done = [], curve, 0.0
    for t in [*cuts, 1.0]:
        if t < 1.0:
            piece, rest = _split(rest, (t - done) / (1 - done))
            done = t
        else:
            piece = rest
        found.append((piece[0], piece[1:], _inside(_bezier(piece, 0.5), box)))
    return found


def _cut(subpath: Subpath, box: Box, joined: bool) -> list[Subpath] | None:
    """The subpath without what lies in the box, or None where none of it does. A path that is
    filled or clips keeps its outline closed by a straight line across the box; a stroke breaks."""
    segments = list(subpath.segments)
    closed = subpath.closed or joined
    if closed and subpath.end() != subpath.start:
        segments.append((subpath.start,))
    pieces, at = [], subpath.start
    for segment in segments:
        pieces += _pieces(at, segment, box)
        at = segment[-1]
    if not any(inside for *_, inside in pieces):
        return None
    if all(inside for *_, inside in pieces):
        return []
    if closed:
        # Begun where it leaves a box, the closed outline ends where it enters one.
        first = next(
            index
            for index, (*_, inside) in enumerate(pieces)
            if not inside and pieces[index - 1][2]
        )
        pieces = pieces[first:] + pieces[:first]
    made: list[Subpath] = []
    current: Subpath | None = None
    entered = False
    for start, piece, inside in pieces:
        if inside:
            entered = True
            continue
        if current is None:
            current = Subpath(start)
        elif entered:
            if joined:
                current.segments.append((start,))
            else:
                made.append(current)
                current = Subpath(start)
        entered = False
        current.segments.append(piece)
    if current is not None:
        if joined:
            current.segments.append((current.start,))
            current.closed = True
        made.append(current)
    return made


def cut(subpaths: list[Subpath], boxes: list[Box], joined: bool) -> list[Subpath] | None:
    """The subpaths without what lies in the boxes, or None where nothing does."""
    changed = False
    for box in boxes:
        kept = []
        for subpath in subpaths:
            parts = _cut(subpath, box, joined)
            if parts is None:
                kept.append(subpath)
            else:
                changed = True
                kept += parts
        subpaths = kept
    return subpaths if changed else None
