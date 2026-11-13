"""Formulas computed in Python (D22): a tree compiled once into a function of the cell it is
computed for. What every function shares is done here once, by the kind of each argument: how a
value given is read, where an error ends the call, how a call runs over each value of an array,
and where a reference meets the formula's own row or column. A formula xlsx stores without the
dynamic-array flag is computed as Excel computes it, by that meeting (implicit intersection)
wherever one value is taken; an argument that takes an array computes its operands as arrays."""

import inspect
import operator
from collections.abc import Callable

from . import values
from .formats import Language
from .functions import FORMS
from .grid import Area, Context, Union, Value, cells, intersected, matrix, numbers, scalar
from .parse import (
    LAST_COL,
    LAST_ROW,
    Array,
    Binary,
    Call,
    Error,
    Group,
    Held,
    Logical,
    Missing,
    Name,
    Number,
    Postfix,
    Prefix,
    Ref,
    Structured,
    Text,
    Unreadable,
)
from .registry import FUNCTIONS, Arg, Kind
from .values import (
    BLANK,
    DIV0,
    NAME,
    NULL,
    REF,
    VALUE,
    Matrix,
    Scalar,
    cancelled,
    finite,
    lifted,
    power,
)

Compiled = Callable[[Context], Value]
SCALARS = (Kind.NUMBER, Kind.LOGICAL, Kind.TEXT, Kind.ANY, Kind.CRITERION)
LISTS = (Kind.NUMBERS, Kind.VALUES, Kind.LOGICALS, Kind.TEXTS)


def formula(tree) -> Callable[[Context], Scalar]:
    """The function giving the value of a cell that holds the formula, its tree as `relative`
    gives it, so that one function serves every cell holding the same formula relative to its
    own: an area read where it meets the cell, an array by its first value, an empty cell as
    0."""
    run = (
        _settling(tree) if isinstance(tree, Binary) and tree.op in "+-" else _compiled(tree, False)
    )

    def computed(context: Context) -> Scalar:
        result = scalar(context, run(context))
        return 0.0 if isinstance(result, values.Blank) else result

    return computed


def spilled(tree) -> Callable[[Context], Value]:
    """The function giving the whole value of a formula, as the cells an array formula spills
    over hold it: an array or an area's values by rows, a single value alone, an empty cell as
    0."""
    run = _compiled(tree, True)

    def computed(context: Context) -> Value:
        result = run(context)
        if isinstance(result, Area):
            result = matrix(context, result)
        if isinstance(result, Matrix):
            return Matrix(
                tuple(
                    tuple(0.0 if isinstance(each, values.Blank) else each for each in row)
                    for row in result.rows
                )
            )
        return 0.0 if isinstance(result, values.Blank) else result

    return computed


def _settling(tree: Binary) -> Compiled:
    """The sum or difference a formula ends with, 0 where its operands cancel to within what
    their binary form holds, as Excel corrects the last operation of a formula."""
    left, right = _compiled(tree.left, False), _compiled(tree.right, False)

    def computed(context: Context) -> Value:
        first = _operand(context, left(context), False)
        second = _operand(context, right(context), False)
        result = lifted(_scalar_operation(tree.op, context.language), first, second)
        if not isinstance(result, float):
            return result
        first = values.number(first, context.language)
        second = values.number(second, context.language)
        if not isinstance(first, float) or not isinstance(second, float):
            return result
        return cancelled(first, second if tree.op == "+" else -second, result)

    return computed


def _compiled(node, array: bool) -> Compiled:
    match node:
        case Number(value):
            return _constant(float(value))
        case Text(value) | Logical(value):
            return _constant(value)
        case Error():
            return _constant(node)
        case Missing():
            return _constant(BLANK)
        case Array(rows):
            return _constant(Matrix(tuple(tuple(_element(each) for each in row) for row in rows)))
        case Ref():
            return _reference(node)
        case Held():
            return lambda context: context.book.held(node, context)
        case Name() | Structured():
            return _constant(NAME)
        case Group(inner):
            return _compiled(inner, array)
        case Prefix("+", operand):
            return _compiled(operand, array)
        case Prefix("-", operand):
            return _unary(operand, array, operator.neg)
        case Postfix("%", operand):
            return _unary(operand, array, lambda number: number / 100)
        case Binary(":" | " " | ",", _, _):
            return _reference_operator(node)
        case Binary(op, left, right):
            return _binary(op, _compiled(left, array), _compiled(right, array), array)
        case Call():
            return _call(node, array)
    raise Unreadable(repr(node))


def _constant(value: Value) -> Compiled:
    return lambda context: value


def _element(node) -> Scalar:
    match node:
        case Number(value):
            return float(value)
        case Text(value) | Logical(value):
            return value
    return node


def _reference(node: Ref) -> Compiled:
    if node.book is not None:
        return _constant(REF)
    start, end = node.start, node.end or node.start

    def area(context: Context) -> Area | Error:
        sheet = node.sheet or context.sheet
        if context.book.extent(sheet) is None:
            return REF
        top = _line(start.row, start.abs_row, context.row, 1)
        bottom = _line(end.row, end.abs_row, context.row, LAST_ROW)
        left = _line(start.col, start.abs_col, context.col, 1)
        right = _line(end.col, end.abs_col, context.col, LAST_COL)
        if not (1 <= min(top, bottom) and max(top, bottom) <= LAST_ROW):
            return REF
        if not (1 <= min(left, right) and max(left, right) <= LAST_COL):
            return REF
        return Area(sheet, min(top, bottom), min(left, right), max(top, bottom), max(left, right))

    return area


def _line(at: int | None, fixed: bool, here: int, whole: int) -> int:
    """A row or column of a reference `relative` gave: as it is where absolute, counted from
    the formula's own cell where not, `whole` where the reference takes the whole line."""
    if at is None:
        return whole
    return at if fixed else here + at


def _reference_operator(node: Binary) -> Compiled:
    left, right = _compiled(node.left, False), _compiled(node.right, False)

    def run(context: Context) -> Value:
        first, second = left(context), right(context)
        for each in (first, second):
            if isinstance(each, Error):
                return each
        if node.op == ",":
            areas = []
            for each in (first, second):
                match each:
                    case Area():
                        areas.append(each)
                    case Union():
                        areas.extend(each.areas)
                    case _:
                        return VALUE
            return Union(tuple(areas))
        if not isinstance(first, Area) or not isinstance(second, Area):
            return VALUE
        if first.sheet != second.sheet:
            return VALUE
        if node.op == ":":
            return Area(
                first.sheet,
                min(first.top, second.top),
                min(first.left, second.left),
                max(first.bottom, second.bottom),
                max(first.right, second.right),
            )
        top, left_ = max(first.top, second.top), max(first.left, second.left)
        bottom, right_ = min(first.bottom, second.bottom), min(first.right, second.right)
        if top > bottom or left_ > right_:
            return NULL
        return Area(first.sheet, top, left_, bottom, right_)

    return run


def _operand(context: Context, value: Value, array: bool) -> Scalar | Matrix:
    match value:
        case Area():
            return matrix(context, value) if array else intersected(context, value)
        case Union():
            return VALUE
    return value


def _unary(operand, array: bool, apply: Callable[[float], float]) -> Compiled:
    run = _compiled(operand, array)

    def one(value: Scalar, language: Language) -> Scalar:
        number = values.number(value, language)
        return number if isinstance(number, Error) else finite(apply(number))

    def computed(context: Context) -> Value:
        given = _operand(context, run(context), array)
        return lifted(lambda value: one(value, context.language), given)

    return computed


def _divided(left: float, right: float) -> float | Error:
    return DIV0 if right == 0 else left / right


ARITHMETIC = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": _divided,
    "^": power,
}
COMPARISONS = {
    "=": operator.eq,
    "<>": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}


def _scalar_operation(op: str, language: Language) -> Callable[[Scalar, Scalar], Scalar]:
    if op in ARITHMETIC:
        apply = ARITHMETIC[op]

        def arithmetic(left: Scalar, right: Scalar) -> Scalar:
            first = values.number(left, language)
            if isinstance(first, Error):
                return first
            second = values.number(right, language)
            if isinstance(second, Error):
                return second
            result = apply(first, second)
            return result if isinstance(result, Error) else finite(result)

        return arithmetic
    if op in COMPARISONS:
        compare = COMPARISONS[op]

        def comparison(left: Scalar, right: Scalar) -> Scalar:
            for each in (left, right):
                if isinstance(each, Error):
                    return each
            return compare(values.compare(left, right, language), 0)

        return comparison
    if op == "&":

        def joined(left: Scalar, right: Scalar) -> Scalar:
            first = values.text(left, language)
            if isinstance(first, Error):
                return first
            second = values.text(right, language)
            return second if isinstance(second, Error) else first + second

        return joined
    raise Unreadable(op)


def _binary(op: str, left: Compiled, right: Compiled, array: bool) -> Compiled:
    def computed(context: Context) -> Value:
        first = _operand(context, left(context), array)
        second = _operand(context, right(context), array)
        return lifted(_scalar_operation(op, context.language), first, second)

    return computed


def specs_of(name: str, args: tuple[Arg, ...], count: int) -> list[Arg]:
    """The argument each one given stands for, a repeated group taken again as often as it is
    given."""
    start = next((at for at, arg in enumerate(args) if arg.repeat), None)
    if start is None:
        if not sum(not arg.optional for arg in args) <= count <= len(args):
            raise Unreadable(f"{name} takes {len(args)} arguments, given {count}")
        return list(args[:count])
    group = args[start : start + args[start].repeat]
    after = args[start + len(group) :]
    required = start + sum(not arg.optional for arg in group)
    if count < required or count > 255:
        raise Unreadable(f"{name} takes at least {required} arguments, given {count}")
    whole, left = divmod(count - start, len(group))
    if left > len(after):
        raise Unreadable(f"{name} takes its arguments in groups of {len(group)}, given {count}")
    return [*args[:start], *group * whole, *after[:left]]


def _call(node: Call, array: bool) -> Compiled:
    function = FUNCTIONS.get(node.name)
    form = FORMS.get(node.name)
    if function is None or form is None:
        return _constant(NAME)
    specs = specs_of(node.name, function.args, len(node.args))
    parts = [_argument(spec, arg, array) for spec, arg in zip(specs, node.args, strict=True)]
    if function.defaults:
        parameters = list(inspect.signature(form).parameters.values())[1:]
        for at, (spec, arg) in enumerate(zip(specs, node.args, strict=True)):
            if spec.optional and isinstance(arg, Missing):
                default = parameters[at].default
                if default is inspect.Parameter.empty:
                    raise TypeError(f"{node.name} has no default for {spec.name}")
                parts[at] = _constant(default)
    merged = [spec.kind in LISTS and spec.repeat == 1 for spec in specs]

    def computed(context: Context) -> Value:
        given: list = []
        lifting = False
        for spec, part, merge in zip(specs, parts, merged, strict=True):
            value = part(context)
            if spec.kind in LISTS:
                if isinstance(value, Error):
                    return value
                if merge and given and isinstance(given[-1], _Merged):
                    given[-1].extend(value)
                    continue
                value = _Merged(value) if merge else value
            elif spec.kind in SCALARS and not spec.lazy:
                lifting = lifting or isinstance(value, Matrix)
            elif isinstance(value, Error) and spec.kind is Kind.RANGE:
                return value
            given.append(value)
        if lifting:
            return lifted(lambda *each: _run(form, context, specs, each), *given)
        return _run(form, context, specs, given)

    return computed


class _Merged(list):
    """The values of a repeated argument, given together to the form as one list."""


def _run(form: Callable, context: Context, specs: list[Arg], given) -> Value:
    arguments = []
    for spec, value in zip(specs, given, strict=False):
        if spec.kind in SCALARS and not spec.lazy:
            value = _read(spec, value, context.language)
            if isinstance(value, Error) and not spec.errors and spec.kind is not Kind.CRITERION:
                return value
        arguments.append(list(value) if isinstance(value, _Merged) else value)
    result = form(context, *arguments)
    if isinstance(result, int) and not isinstance(result, bool):
        return float(result)
    if isinstance(result, float):
        return finite(result)
    return result


def _read(spec: Arg, value: Scalar, language: Language) -> Scalar:
    match spec.kind:
        case Kind.NUMBER:
            if isinstance(value, bool) and not spec.logicals:
                return VALUE
            return values.number(value, language)
        case Kind.LOGICAL:
            return values.logical(value, language)
        case Kind.TEXT:
            return values.text(value, language)
    return value


def _argument(spec: Arg, node, array: bool) -> Compiled:
    takes_array = spec.kind is Kind.ARRAY or array
    run = _compiled(node, takes_array)
    if spec.lazy and isinstance(node, Missing):
        return _constant(lambda: 0.0)
    if spec.lazy:

        def thunk(context: Context) -> Callable[[], Value]:
            def computed() -> Value:
                value = run(context)
                if spec.kind is Kind.ANY:
                    return value
                value = _read(spec, _operand(context, value, False), context.language)
                return value

            return computed

        return thunk
    match spec.kind:
        case Kind.ARRAY:
            return run
        case Kind.RANGE:
            return lambda context: _range(run(context))
        case Kind.NUMBERS:
            return lambda context: _numbers(context, run(context), spec)
        case Kind.VALUES:
            return lambda context: _values(context, run(context))
        case Kind.LOGICALS:
            return lambda context: _logicals(context, run(context))
        case Kind.TEXTS:
            return lambda context: _texts(context, run(context))
    return lambda context: _operand(context, run(context), takes_array)


def _range(value: Value) -> Value:
    if isinstance(value, Area | Union | Error):
        return value
    return VALUE


def _numbers(context: Context, value: Value, spec: Arg) -> list[float] | Error:
    if isinstance(value, bool) and not spec.logicals:
        return VALUE
    return numbers(context, value)


def _values(context: Context, value: Value) -> list[tuple[Scalar, bool]] | Error:
    """Every value, each with whether it was given itself rather than in an area or array."""
    if isinstance(value, Area | Union | Matrix):
        return [(each, False) for each in cells(context, value)]
    return [(value, True)]


def _logicals(context: Context, value: Value) -> list[bool] | Error:
    """Logicals to combine: numbers and logicals in an area or array, an error there ending it,
    and a value given read as one logical."""
    if isinstance(value, Area | Union | Matrix):
        found = []
        for each in cells(context, value):
            if isinstance(each, bool):
                found.append(each)
            elif isinstance(each, float):
                found.append(each != 0)
            elif isinstance(each, Error):
                return each
        return found
    logical = values.logical(value, context.language)
    return logical if isinstance(logical, Error) else [logical]


def _texts(context: Context, value: Value) -> list[str] | Error:
    """Texts to join: every value of an area or array and a value given, each read as text."""
    given = cells(context, value) if isinstance(value, Area | Union | Matrix) else (value,)
    found = []
    for each in given:
        text = values.text(each, context.language)
        if isinstance(text, Error):
            return text
        found.append(text)
    return found
