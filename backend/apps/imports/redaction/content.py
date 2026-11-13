"""A page's content read as a reader draws it, and written again without what lies under boxes: each
glyph a box covers taken out of its string and the text after it left where it was, the pixels of
images under a box cleared, the parts of drawings inside a box cut away, and forms drawn on the page
gone through the same way. Black boxes are drawn over the boxes last."""

from dataclasses import dataclass, field, replace
from itertools import count

import pikepdf
from pikepdf import Array, Dictionary, Name, Operator, Pdf, Stream, String

from . import images, paths
from .fonts import Font, Unmeasurable, number
from .paths import (
    IDENTITY,
    Box,
    Matrix,
    Point,
    Subpath,
    apply,
    clipped,
    corners,
    covered,
    enclosing,
    multiply,
    overlap,
)

# A glyph is taken out when the boxes cover this much of what it draws, as pdfium reads it; a
# glyph pdfium does not read, when a box covers this much of its width and of its line's height:
# a box drawn over a word reaches into the letters beside it and the lines above and below a little.
INKED = 0.5
WIDE, TALL = 0.1, 0.3
# How far text in a font that cannot be measured may run, in its size, and how high it may stand.
FAR, LOW, HIGH = 1e5, -0.6, 1.6
ALTERNATES = ("/ActualText", "/Alt", "/E")
FILLS = {"f", "F", "f*", "B", "B*", "b", "b*"}
STROKES = {"S", "s", "B", "B*", "b", "b*"}
PAINTS = FILLS | STROKES | {"n"}
SEGMENTS = {"m", "l", "c", "v", "y", "h", "re"}


class Unredactable(Exception):
    """Content under a box that cannot be taken out of the file."""


@dataclass
class Removed:
    glyphs: int = 0
    images: int = 0
    drawings: int = 0
    # A structure parent key and the marked content id under it, or None for an XObject's own key.
    marked: set[tuple[int, int | None]] = field(default_factory=set)

    def total(self) -> int:
        return self.glyphs + self.images + self.drawings


@dataclass
class _Graphics:
    ctm: Matrix = IDENTITY
    font: Font | None = None
    broken: str | None = "no font is set"
    size: float = 0.0
    spacing: float = 0.0
    words: float = 0.0
    scale: float = 1.0
    leading: float = 0.0
    rise: float = 0.0
    fill: Name | None = None
    stroke: Name | None = None


def _copied(given: Dictionary) -> Dictionary:
    return Dictionary({key: value for key, value in given.items()})


class _Resources:
    """A content stream's resources, copied the first time something new is added to them."""

    def __init__(self, given: object):
        self.given = given if isinstance(given, Dictionary) else Dictionary()
        self.made: Dictionary | None = None
        self._kinds: set[str] = set()

    def current(self) -> Dictionary:
        return self.given if self.made is None else self.made

    def find(self, kind: str, name: object) -> object | None:
        category = self.current().get(kind)
        if isinstance(category, Dictionary) and isinstance(name, Name) and name in category:
            return category[name]
        return None

    def add(self, kind: str, value: object, hint: str) -> Name:
        if self.made is None:
            self.made = _copied(self.given)
        if kind not in self._kinds:
            category = self.made.get(kind)
            self.made[kind] = (
                _copied(category) if isinstance(category, Dictionary) else Dictionary()
            )
            self._kinds.add(kind)
        category = self.made[kind]
        name = next(f"/{hint}{index}" for index in count() if f"/{hint}{index}" not in category)
        category[name] = value
        return Name(name)


def _name(item: object) -> str:
    if isinstance(item, pikepdf.ContentStreamInlineImage):
        return "INLINE IMAGE"
    if isinstance(item, pikepdf.ContentStreamInstruction):
        return str(item.operator)
    return str(item[1])


def _numbers(operands: list, size: int) -> list[float] | None:
    values = [number(each) for each in operands]
    return values if len(values) == size else None


class _Pass:
    """One content stream gone through: the page's or a form's."""

    def __init__(
        self,
        pdf: Pdf,
        boxes: list[Box],
        removed: Removed,
        graphics: _Graphics,
        resources: _Resources,
        parents: int | None,
        seen: frozenset,
        fonts: dict,
        inks: dict[tuple[int, int], list[tuple[Point, Box]]],
    ):
        self.pdf, self.boxes, self.removed, self.inks = pdf, boxes, removed, inks
        self.graphics, self.stack = graphics, []
        self.resources, self.parents, self.seen, self.fonts = resources, parents, seen, fonts
        self.out: list = []
        self.changed = False
        self.marks: list[list] = []
        self.tm: Matrix | None = IDENTITY
        self.tlm: Matrix = IDENTITY
        self._reset_path()

    def _reset_path(self) -> None:
        self.subpaths: list[Subpath] = []
        self.pending: list = []
        self.clip: str | None = None
        self.open = False
        self.point = (0.0, 0.0)

    def run(self, instructions: list) -> list | None:
        for instruction in instructions:
            self._one(instruction)
        self.out += self.pending
        return self.out if self.changed else None

    def _emit(self, operands: list, operator: str) -> None:
        self.out.append((operands, Operator(operator)))

    def _one(self, instruction) -> None:
        if isinstance(instruction, pikepdf.ContentStreamInlineImage):
            self._inline(instruction)
            return
        operands, op = list(instruction.operands), str(instruction.operator)
        if op in SEGMENTS or op in ("W", "W*"):
            self.pending.append(instruction)
            self._segment(op, operands)
            return
        if op in PAINTS:
            self._paint(op, instruction)
            return
        if self.pending:
            self.out += self.pending
            self._reset_path()
        handler = _HANDLERS.get(op)
        if handler is None or handler(self, operands, instruction) is not False:
            self.out.append(instruction)

    # Marked content

    def _begin(self, operands: list, instruction) -> None:
        tag = operands[0] if operands else Name("/Unknown")
        properties = operands[1] if len(operands) > 1 else None
        if isinstance(properties, Name):
            properties = self.resources.find("/Properties", properties)
        self.marks.append([len(self.out), tag, properties, False])

    def _end(self, operands: list, instruction) -> None:
        if self.marks:
            self.marks.pop()

    def _touched(self) -> None:
        for mark in self.marks:
            index, tag, properties, rewritten = mark
            if not isinstance(properties, Dictionary):
                continue
            mcid = properties.get("/MCID")
            if mcid is not None and self.parents is not None:
                self.removed.marked.add((self.parents, int(number(mcid))))
            if rewritten or tag == Name.OC or not any(key in properties for key in ALTERNATES):
                continue
            kept = Dictionary(
                {key: value for key, value in properties.items() if key not in ALTERNATES}
            )
            given = self.out[index].operands[1]
            if isinstance(given, Name):
                kept = self.resources.add("/Properties", self.pdf.make_indirect(kept), "Redacted")
            self.out[index] = ([tag, kept], Operator("BDC"))
            mark[3] = True
            self.changed = True

    # Graphics state

    def _save(self, operands: list, instruction) -> None:
        self.stack.append(replace(self.graphics))

    def _restore(self, operands: list, instruction) -> None:
        if self.stack:
            self.graphics = self.stack.pop()

    def _transform(self, operands: list, instruction) -> None:
        matrix = _numbers(operands, 6)
        if matrix:
            self.graphics.ctm = multiply(tuple(matrix), self.graphics.ctm)

    def _state(self, operands: list, instruction) -> None:
        state = self.resources.find("/ExtGState", operands[0] if operands else None)
        if isinstance(state, Dictionary) and isinstance(state.get("/Font"), Array):
            given = state["/Font"]
            if len(given) == 2:
                self._set_font(given[0], number(given[1]))

    def _colour(self, operands: list, instruction) -> None:
        op = str(instruction.operator)
        pattern = (
            operands[-1]
            if op in ("scn", "SCN") and operands and isinstance(operands[-1], Name)
            else None
        )
        if op.islower():
            self.graphics.fill = pattern
        else:
            self.graphics.stroke = pattern

    # Text

    def _set_font(self, font: object, size: float) -> None:
        graphics = self.graphics
        graphics.size = size
        if not isinstance(font, Dictionary):
            graphics.font, graphics.broken = None, "is missing"
            return
        key = font.objgen if font.is_indirect else None
        found = self.fonts.get(key) if key else None
        if found is None:
            try:
                found = Font(font)
            except Unmeasurable as error:
                found = str(error)
            if key:
                self.fonts[key] = found
        graphics.font, graphics.broken = (found, None) if isinstance(found, Font) else (None, found)

    def _text_state(self, operands: list, instruction) -> None:
        op = str(instruction.operator)
        graphics = self.graphics
        if op == "Tf":
            if len(operands) == 2:
                self._set_font(self.resources.find("/Font", operands[0]), number(operands[1]))
            return
        value = number(operands[0]) if operands else 0.0
        if op == "Tc":
            graphics.spacing = value
        elif op == "Tw":
            graphics.words = value
        elif op == "Tz":
            graphics.scale = value / 100
        elif op == "TL":
            graphics.leading = value
        elif op == "Ts":
            graphics.rise = value

    def _line(self, operands: list, instruction) -> None:
        op = str(instruction.operator)
        if op == "BT":
            self.tm = self.tlm = IDENTITY
        elif op == "Tm":
            matrix = _numbers(operands, 6)
            if matrix:
                self.tm = self.tlm = tuple(matrix)
        elif op == "T*":
            self._next_line(0.0, -self.graphics.leading)
        else:
            moved = _numbers(operands, 2)
            if moved:
                if op == "TD":
                    self.graphics.leading = -moved[1]
                self._next_line(*moved)

    def _next_line(self, x: float, y: float) -> None:
        self.tlm = multiply((1.0, 0.0, 0.0, 1.0, x, y), self.tlm)
        self.tm = self.tlm

    def _show(self, operands: list, instruction) -> bool | None:
        op = str(instruction.operator)
        if op == "'":
            self._next_line(0.0, -self.graphics.leading)
        elif op == '"' and len(operands) == 3:
            self.graphics.words, self.graphics.spacing = number(operands[0]), number(operands[1])
            self._next_line(0.0, -self.graphics.leading)
        given = operands[-1] if operands else Array()
        items = list(given) if op == "TJ" and isinstance(given, Array) else [given]
        made = self._glyphs(items)
        if made is None:
            return None
        if op == "'":
            self._emit([], "T*")
        elif op == '"':
            self._emit([operands[0]], "Tw")
            self._emit([operands[1]], "Tc")
            self._emit([], "T*")
        self._emit([Array(made)], "TJ")
        self.changed = True
        return False

    def _matrix(self) -> Matrix:
        graphics = self.graphics
        return multiply(
            (graphics.size * graphics.scale, 0.0, 0.0, graphics.size, 0.0, graphics.rise),
            multiply(self.tm, graphics.ctm),
        )

    def _glyphs(self, items: list) -> list | None:
        """The shown items without the glyphs under a box, or None where none is."""
        font = self.graphics.font
        if font is None or self.tm is None:
            self._blind(self.graphics.broken or "cannot be placed")
            return None
        graphics = self.graphics
        made: list = []
        held = bytearray()
        moved = 0.0
        changed = False

        def flush() -> None:
            nonlocal held, moved
            if held:
                made.append(String(bytes(held)))
                held = bytearray()
            if moved:
                made.append(moved)
                moved = 0.0

        for position, item in enumerate(items):
            if not isinstance(item, String | bytes):
                adjust = number(item)
                if held:
                    flush()
                moved += adjust
                self._advance(-adjust / 1000 * graphics.size, font.vertical)
                continue
            codes = font.codes(bytes(item))
            for index, code in enumerate(codes):
                try:
                    width = font.advance(code)
                except Unmeasurable as error:
                    self._blind(str(error))
                    flush()
                    made.append(String(b"".join(codes[index:])))
                    made += items[position + 1 :]
                    self.tm = None
                    return made if changed else None
                spacing = graphics.spacing + (graphics.words if font.spaces(code) else 0.0)
                if font.vertical:
                    step = font.drop(code) * graphics.size + spacing
                else:
                    step = width * graphics.size + spacing
                if self._covered(font, code):
                    changed = True
                    self.removed.glyphs += 1
                    self._touched()
                    if held:
                        flush()
                    moved += self._undo(step, font.vertical)
                else:
                    if moved:
                        flush()
                    held += code
                self._advance(step, font.vertical)
        flush()
        return made if changed else None

    def _advance(self, step: float, vertical: bool) -> None:
        offset = (0.0, step) if vertical else (step * self.graphics.scale, 0.0)
        self.tm = multiply((1.0, 0.0, 0.0, 1.0, *offset), self.tm)

    def _undo(self, step: float, vertical: bool) -> float:
        """The adjustment in a text array that moves on as far as a glyph taken out did."""
        size = self.graphics.size
        if abs(size) < 1e-12:
            if abs(step if vertical else step * self.graphics.scale) > 1e-9:
                raise Unredactable("text of no size moves on under a box")
            return 0.0
        return -step * 1000 / size

    def _inked(self, matrix: Matrix) -> float | None:
        """How much of what pdfium reads drawn from the glyph's origin the boxes cover, or None
        where it reads nothing there."""
        x, y = apply(matrix, (0.0, 0.0))
        near = max(0.05, 0.1 * abs(matrix[0] * matrix[3] - matrix[1] * matrix[2]) ** 0.5)
        found = [
            covered(ink, self.boxes)
            for column in range(int(x) - 1, int(x) + 2)
            for row in range(int(y) - 1, int(y) + 2)
            for (at_x, at_y), ink in self.inks.get((column, row), [])
            if abs(at_x - x) <= near
            and abs(at_y - y) <= near
            and ink[2] > ink[0]
            and ink[3] > ink[1]
        ]
        return max(found) if found else None

    def _covered(self, font: Font, code: bytes) -> bool:
        matrix = self._matrix()
        glyph = font.box(code)
        bounds = enclosing(corners(glyph, matrix))
        near = [box for box in self.boxes if overlap(bounds, box)]
        if not near:
            return False
        inked = self._inked(matrix)
        if inked is not None:
            return inked >= INKED
        inverse = paths.inverse(matrix)
        if inverse is None:
            x, y = apply(matrix, (0.0, 0.0))
            return any(box[0] <= x <= box[2] and box[1] <= y <= box[3] for box in near)
        left, bottom, right, top = glyph
        for box in near:
            part = clipped(corners(box, inverse), glyph)
            if len(part) < 3:
                continue
            xs, ys = [x for x, _ in part], [y for _, y in part]
            if max(xs) - min(xs) >= WIDE * (right - left) and max(ys) - min(ys) >= TALL * (
                top - bottom
            ):
                return True
        return False

    def _blind(self, why: str) -> None:
        """Text that cannot be measured: wherever along its line it may run must be clear of every
        box."""
        start = self.tm if self.tm is not None else self.tlm
        graphics = self.graphics
        matrix = multiply(
            (graphics.size * graphics.scale, 0.0, 0.0, graphics.size, 0.0, graphics.rise),
            multiply(start, graphics.ctm),
        )
        back = 0.0 if self.tm is not None else -FAR
        strips = [(back, LOW, FAR, HIGH), (LOW, -FAR, HIGH, -back)]
        inverse = paths.inverse(matrix)
        for box in self.boxes:
            if inverse is None:
                x, y = apply(matrix, (0.0, 0.0))
                hit = box[0] <= x <= box[2] and box[1] <= y <= box[3]
            else:
                hit = any(len(clipped(corners(box, inverse), strip)) >= 3 for strip in strips)
            if hit:
                raise Unredactable(f"text under a box is in a font that {why}")
        self.tm = None

    # Paths

    def _segment(self, op: str, operands: list) -> None:
        values = [number(each) for each in operands]
        if op in ("W", "W*"):
            self.clip = op
            return
        if op == "re" and len(values) == 4:
            x, y, w, h = values
            self.subpaths.append(
                Subpath((x, y), [((x + w, y),), ((x + w, y + h),), ((x, y + h),)], closed=True)
            )
            self.open, self.point = False, (x, y)
            return
        if op == "m" and len(values) == 2:
            self.subpaths.append(Subpath((values[0], values[1])))
            self.open, self.point = True, (values[0], values[1])
            return
        if op == "h":
            if self.open:
                self.subpaths[-1].closed = True
                self.point, self.open = self.subpaths[-1].start, False
            return
        if not self.open:
            self.subpaths.append(Subpath(self.point))
            self.open = True
        points = [(values[index], values[index + 1]) for index in range(0, len(values) - 1, 2)]
        if op == "l" and len(points) == 1:
            segment = (points[0],)
        elif op == "c" and len(points) == 3:
            segment = tuple(points)
        elif op == "v" and len(points) == 2:
            segment = (self.point, points[0], points[1])
        elif op == "y" and len(points) == 2:
            segment = (points[0], points[1], points[1])
        else:
            return
        self.subpaths[-1].segments.append(segment)
        self.point = segment[-1]

    def _paint(self, op: str, instruction) -> None:
        pending = [*self.pending, instruction]
        subpaths, clip = self.subpaths, self.clip
        self._reset_path()
        ctm = self.graphics.ctm
        page = paths.transformed(subpaths, ctm)
        bounds = paths.bounds(page)
        inverse = paths.inverse(ctm)
        if bounds is None or inverse is None or not any(overlap(bounds, box) for box in self.boxes):
            self.out += pending
            return
        filling, stroking = op in FILLS, op in STROKES
        stroked = page
        if op in ("s", "b", "b*") and page:
            stroked = [*page[:-1], replace(page[-1], closed=True)]
        joined = paths.cut(page, self.boxes, joined=True) if filling or clip else None
        broken = paths.cut(stroked, self.boxes, joined=False) if stroking else None
        if joined is None and broken is None:
            self.out += pending
            return
        if filling and joined is not None:
            self._pattern(self.graphics.fill)
        if stroking and broken is not None:
            self._pattern(self.graphics.stroke)
        self.changed = True
        self.removed.drawings += 1
        self._touched()
        outline = page if joined is None else joined
        if filling and outline:
            self._draw(outline, inverse)
            self._emit([], "f*" if op.endswith("*") else "f")
        if stroking:
            line = stroked if broken is None else broken
            if line:
                self._draw(line, inverse)
                self._emit([], "S")
        if clip:
            if outline:
                self._draw(outline, inverse)
            else:
                self._emit([0, 0, 0, 0], "re")
            self._emit([], clip)
            self._emit([], "n")

    def _draw(self, subpaths: list[Subpath], inverse: Matrix) -> None:
        for operands, operator in paths.drawn(paths.transformed(subpaths, inverse)):
            self._emit(operands, operator)

    def _pattern(self, name: Name | None) -> None:
        """A tiling pattern repeats its own content, which a cut path no longer shows but which the
        file still holds: under a box, that may only be drawing."""
        pattern = self.resources.find("/Pattern", name) if name is not None else None
        if not isinstance(pattern, Stream) or number(pattern.get("/PatternType")) != 1:
            return
        for instruction in pikepdf.parse_content_stream(pattern):
            if _name(instruction) in ("BT", "Do", "INLINE IMAGE"):
                raise Unredactable("a pattern of text or images fills a drawing under a box")

    # Images and forms

    def _inline(self, instruction) -> None:
        if self.pending:
            self.out += self.pending
            self._reset_path()
        bounds = enclosing(corners((0.0, 0.0, 1.0, 1.0), self.graphics.ctm))
        if any(overlap(bounds, box) for box in self.boxes):
            raise Unredactable("an inline image lies under a box")
        self.out.append(instruction)

    def _do(self, operands: list, instruction) -> bool | None:
        name = operands[0] if operands else None
        drawn = self.resources.find("/XObject", name)
        if not isinstance(drawn, Stream):
            return None
        if drawn.get("/Subtype") == Name.Image:
            made = self._image(drawn)
        elif drawn.get("/Subtype") == Name.Form:
            made = self._form(drawn)
        else:
            return None
        if made is None:
            return None
        if "/StructParent" in drawn:
            self.removed.marked.add((int(number(drawn["/StructParent"])), None))
        self._emit([self.resources.add("/XObject", made, "Redacted")], "Do")
        self.changed = True
        return False

    def _image(self, image: Stream) -> Stream | None:
        ctm = self.graphics.ctm
        bounds = enclosing(corners((0.0, 0.0, 1.0, 1.0), ctm))
        near = [box for box in self.boxes if overlap(bounds, box)]
        inverse = paths.inverse(ctm)
        if not near or inverse is None:
            return None
        spaces = self.resources.current().get("/ColorSpace")
        try:
            made = images.painted(
                self.pdf,
                image,
                [corners(box, inverse) for box in near],
                spaces if isinstance(spaces, Dictionary) else None,
            )
        except images.Undecodable as error:
            raise Unredactable(f"an image under a box cannot be read: {error}") from error
        if made is not None:
            self.removed.images += 1
            self._touched()
        return made

    def _form(self, form: Stream) -> Stream | None:
        box = _numbers(list(form.get("/BBox", Array())), 4)
        matrix = _numbers(list(form.get("/Matrix", Array())), 6) or IDENTITY
        ctm = multiply(tuple(matrix), self.graphics.ctm)
        if box is None or form.objgen in self.seen:
            return None
        drawn = (min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3]))
        bounds = enclosing(corners(drawn, ctm))
        if not any(overlap(bounds, each) for each in self.boxes):
            return None
        resources = _Resources(form.get("/Resources", self.resources.current()))
        before = self.removed.total()
        inner = _Pass(
            self.pdf,
            self.boxes,
            self.removed,
            replace(self.graphics, ctm=ctm),
            resources,
            int(number(form["/StructParents"])) if "/StructParents" in form else None,
            self.seen | {form.objgen},
            self.fonts,
            self.inks,
        )
        made = inner.run(pikepdf.parse_content_stream(form))
        if made is None and resources.made is None:
            return None
        if self.removed.total() > before:
            self._touched()
        copy = self.pdf.make_stream(
            pikepdf.unparse_content_stream(made) if made is not None else form.read_bytes(),
            Dictionary(
                {
                    key: value
                    for key, value in form.items()
                    if key not in ("/Length", "/Filter", "/DecodeParms", "/Metadata", "/PieceInfo")
                }
            ),
        )
        if resources.made is not None:
            copy.Resources = resources.made
        return copy


_HANDLERS = {
    "BMC": _Pass._begin,
    "BDC": _Pass._begin,
    "EMC": _Pass._end,
    "q": _Pass._save,
    "Q": _Pass._restore,
    "cm": _Pass._transform,
    "gs": _Pass._state,
    **dict.fromkeys(
        ("cs", "sc", "scn", "g", "rg", "k", "CS", "SC", "SCN", "G", "RG", "K"), _Pass._colour
    ),
    **dict.fromkeys(("Tf", "Tc", "Tw", "Tz", "TL", "Ts"), _Pass._text_state),
    **dict.fromkeys(("BT", "Tm", "Td", "TD", "T*"), _Pass._line),
    **dict.fromkeys(("Tj", "TJ", "'", '"'), _Pass._show),
    "Do": _Pass._do,
}


def _inherited(page: Dictionary, key: str) -> object | None:
    node, hops = page, 0
    while isinstance(node, Dictionary) and hops < 64:
        if key in node:
            return node[key]
        node, hops = node.get("/Parent"), hops + 1
    return None


def _wrapped(instructions: list, boxes: list[Box]) -> list:
    """The page's content kept apart from what follows it, then the black boxes."""
    made: list = [([], Operator("q"))]
    depth = marked = 0
    texting = False
    for item in instructions:
        name = _name(item)
        if name == "q":
            depth += 1
        elif name == "Q":
            if not depth:
                continue
            depth -= 1
        elif name in ("BMC", "BDC"):
            marked += 1
        elif name == "EMC":
            marked = max(0, marked - 1)
        elif name in ("BT", "ET"):
            texting = name == "BT"
        made.append(item)
    if texting:
        made.append(([], Operator("ET")))
    made += [([], Operator("EMC"))] * marked + [([], Operator("Q"))] * (depth + 1)
    made += [([], Operator("q")), ([0], Operator("g"))]
    for left, bottom, right, top in boxes:
        made.append(([left, bottom, right - left, top - bottom], Operator("re")))
    made += [([], Operator("f")), ([], Operator("Q"))]
    return made


def redact_page(
    pdf: Pdf, page: pikepdf.Page, boxes: list[Box], inks: list[tuple[Point, Box]]
) -> Removed:
    """Takes out of the page what lies under the boxes, given in its own coordinates, and draws
    them black over it. The inks are each glyph near a box as pdfium reads the page: its origin and
    the box of what it draws."""
    cells: dict[tuple[int, int], list[tuple[Point, Box]]] = {}
    for origin, ink in inks:
        cells.setdefault((int(origin[0]), int(origin[1])), []).append((origin, ink))
    page.externalize_inline_images()
    resources = _Resources(_inherited(page.obj, "/Resources"))
    removed = Removed()
    given = page.obj.get("/StructParents")
    instructions = pikepdf.parse_content_stream(page)
    made = _Pass(
        pdf,
        boxes,
        removed,
        _Graphics(),
        resources,
        None if given is None else int(number(given)),
        frozenset(),
        {},
        cells,
    ).run(instructions)
    page.obj.Contents = pdf.make_stream(
        pikepdf.unparse_content_stream(_wrapped(instructions if made is None else made, boxes))
    )
    if resources.made is not None:
        page.obj.Resources = resources.made
    return removed
