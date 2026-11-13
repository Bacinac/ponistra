"""Formulas compiled into SQL (D22): a formula's tree, as `relative` gives it, into the SQL of the
value of a cell holding it, read off the cells the places it refers to give. Each function's SQL
form is taken from the registry, its arguments read by their kinds as the Python evaluator reads
them; a formula holding anything without a SQL form is Unsupported, and a part SQL cannot compute
exactly for a cell makes that cell NULL, both computed by the Python forms instead."""

import inspect
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from .evaluate import LISTS, SCALARS, specs_of
from .formats import Language
from .functions import FORMS, SQL_FORMS
from .parse import (
    Binary,
    Call,
    Group,
    Held,
    Logical,
    Missing,
    Number,
    Postfix,
    Prefix,
    Ref,
    Text,
)
from .registry import FUNCTIONS, Arg, Kind
from .sql import (
    BLANK,
    VALUE,
    Range,
    Scope,
    Typed,
    Unsupported,
    arithmetic,
    compared,
    constant,
    joined,
    logical,
    negated,
    number,
    percent,
    text,
    value,
)
from .values import BLANK as EMPTY

COMPARISONS = {"=", "<>", "<", ">", "<=", ">="}


class Places(Protocol):
    """The cells a compiled formula reads."""

    def cell(self, node: Ref | Held, scope: Scope) -> Typed | None:
        """The value of the one cell a reference gives where a formula takes one value: its only
        cell, or the one it meets in the formula's own row or column (grid.intersected); None
        where there is none."""

    def area(self, node: Ref | Held, scope: Scope) -> Range | None:
        """The cells of a reference; None for one to nothing (#REF!)."""

    def each(self, given: str) -> str:
        """A SELECT of the value of a part's SQL (v) in each cell compiled."""


def compiled(tree, places: Places, language: Language) -> str:
    """The SQL of the jsonb value of a cell holding the formula, NULL where Python is to compute
    it: an empty value as 0, as evaluate.formula gives it."""
    scope = Scope(language, places.each)
    compiler = _Compiler(places, scope)
    if isinstance(tree, Binary) and tree.op in "+-":
        result = arithmetic(
            tree.op, compiler.scalar(tree.left), compiler.scalar(tree.right), scope, settling=True
        )
    else:
        result = compiler.scalar(tree)
    if result.kind == BLANK:
        return "'0'::jsonb"
    if result.kind != VALUE:
        return value(result).sql
    return scope.bound(
        [result],
        lambda v: Typed(
            f"CASE WHEN {v[0].sql} = 'null'::jsonb THEN '0'::jsonb ELSE {v[0].sql} END", VALUE
        ),
    ).sql


def _unwrapped(node):
    while isinstance(node, Group):
        node = node.inner
    return node


class _Compiler:
    def __init__(self, places: Places, scope: Scope):
        self.places = places
        self.scope = scope

    def scalar(self, node) -> Typed:
        scope = self.scope
        match node:
            case Number(number_):
                return constant(float(number_))
            case Text(given) | Logical(given):
                return constant(given)
            case Missing():
                return constant(EMPTY)
            case Ref() | Held():
                found = self.places.cell(node, scope)
                if found is None:
                    raise Unsupported("#VALUE!")
                return found
            case Group(inner):
                return self.scalar(inner)
            case Prefix("+", operand):
                return self.scalar(operand)
            case Prefix("-", operand):
                return negated(self.scalar(operand), scope)
            case Postfix("%", operand):
                return percent(self.scalar(operand), scope)
            case Binary(op, left, right) if op in "+-*/^":
                return arithmetic(op, self.scalar(left), self.scalar(right), scope)
            case Binary(op, left, right) if op in COMPARISONS:
                return compared(op, self.scalar(left), self.scalar(right), scope)
            case Binary("&", left, right):
                return joined(self.scalar(left), self.scalar(right), scope)
            case Call():
                return self.call(node)
        raise Unsupported(type(node).__name__)

    def area(self, node) -> Range:
        node = _unwrapped(node)
        if not isinstance(node, Ref | Held):
            raise Unsupported("an array computed")
        found = self.places.area(node, self.scope)
        if found is None:
            raise Unsupported("#REF!")
        return found

    def listed(self, node) -> Range | Typed:
        """An argument of a function taking a list: a reference's area, else a value given."""
        bare = _unwrapped(node)
        if isinstance(bare, Ref | Held):
            return self.area(bare)
        given = self.scalar(node)
        if given.cell is None:
            raise Unsupported("a reference or a value")
        return given

    def lazy(self, spec: Arg, node) -> Callable[[], Typed]:
        if isinstance(node, Missing):
            return lambda: constant(0.0)

        def computed() -> Typed:
            given = self.scalar(node)
            return given if spec.kind is Kind.ANY else _read(spec, given, self.scope)

        return computed

    def call(self, node: Call) -> Typed:
        function = FUNCTIONS.get(node.name)
        python = FORMS.get(node.name)
        if function is None or python is None:
            raise Unsupported("#NAME?")
        form = SQL_FORMS.get(node.name)
        if form is None:
            raise Unsupported(node.name)
        specs = specs_of(node.name, function.args, len(node.args))
        defaults = list(inspect.signature(python).parameters.values())[1:]
        parts: list = []
        guarded: list[tuple[int, Arg]] = []
        for at, (spec, arg) in enumerate(zip(specs, node.args, strict=True)):
            if function.defaults and spec.optional and isinstance(arg, Missing):
                default = defaults[at].default
                parts.append(None if default is None else constant(default))
            elif spec.lazy:
                parts.append(self.lazy(spec, arg))
            elif spec.kind in (Kind.RANGE, Kind.ARRAY):
                parts.append(self.area(arg))
            elif spec.kind in LISTS:
                item = self.listed(arg)
                merged = spec.repeat == 1 and at and specs[at - 1] is spec
                if merged and isinstance(parts[-1], list):
                    parts[-1].append(item)
                    continue
                parts.append([item] if spec.repeat == 1 else item)
            elif spec.kind in SCALARS:
                parts.append(_read(spec, self.scalar(arg), self.scope))
                guarded.append((len(parts) - 1, spec))
            else:
                raise Unsupported(spec.kind.name)
        return self._guarded(form, parts, guarded)

    def _guarded(self, form: Callable, parts: list, guarded: list[tuple[int, Arg]]) -> Typed:
        """The form over the parts, NULL where a value it reads is NULL, or an error that ends
        the call as evaluate._run ends it."""
        given = [parts[at] for at, _ in guarded]

        def body(names: list[Typed]) -> Typed:
            ready = list(parts)
            tests = []
            for (at, spec), name in zip(guarded, names, strict=True):
                ready[at] = name
                if name.kind == VALUE and not spec.errors:
                    tests.append(f"jsonb_typeof({name.sql}) IS DISTINCT FROM 'object'")
                if not name.sure:
                    tests.append(f"{name.sql} IS NOT NULL")
            result = form(self.scope, *ready)
            if not tests:
                return result
            return replace(
                result,
                sql=f"CASE WHEN {' AND '.join(tests)} THEN {result.sql} END",
                simple=False,
                sure=False,
            )

        return self.scope.bound(given, body)


def _read(spec: Arg, given: Typed, scope: Scope) -> Typed:
    """A value read as the kind of the argument it is given for (evaluate._read)."""
    match spec.kind:
        case Kind.NUMBER:
            return number(given, scope, spec.logicals)
        case Kind.LOGICAL:
            return logical(given, scope)
        case Kind.TEXT:
            return text(given, scope)
    return given
