import math
from collections.abc import Callable

from ..grid import Area, Union, cells
from ..values import DIV0, NUM, Error, Matrix, power
from . import form

STEPS = 20
TOLERANCE = 1e-7


def _grown(rate: float, periods: float) -> float | Error:
    """1 + rate to the power of the periods as PV and FV take it, whose rounding reaches their
    last digits: a whole number of periods by squaring, as Excel compounds it, a negative one
    squaring the discount 1 / (1 + rate)."""
    if periods != int(periods):
        return power(1 + rate, periods)
    base, left, grown = 1 + rate if periods >= 0 else 1 / (1 + rate), abs(int(periods)), 1.0
    while left:
        if left & 1:
            grown *= base
        base *= base
        left >>= 1
    return grown


@form("PMT")
def pmt(context, rate, periods, present, future=0.0, kind=0.0):
    if rate == 0:
        return NUM if periods == 0 else -(present + future) / periods
    if rate <= -1:
        return NUM
    try:
        grown = math.exp(periods * math.log1p(rate))
    except OverflowError:
        return NUM
    if grown == 1:
        return NUM
    return -(rate * (future + present * grown)) / ((1 + rate * (kind != 0)) * (grown - 1))


@form("PV")
def pv(context, rate, periods, payment, future=0.0, kind=0.0):
    if rate == 0:
        return -(future + payment * periods)
    grown = _grown(rate, periods)
    if isinstance(grown, Error):
        return grown
    return -(future + payment * (1 + rate * (kind != 0)) * (grown - 1) / rate) / grown


@form("FV")
def fv(context, rate, periods, payment, present=0.0, kind=0.0):
    if rate == 0:
        return -(present + payment * periods)
    grown = _grown(rate, periods)
    if isinstance(grown, Error):
        return grown
    return -(present * grown + payment * (1 + rate * (kind != 0)) * (grown - 1) / rate)


@form("NPER")
def nper(context, rate, payment, present, future=0.0, kind=0.0):
    if rate == 0:
        return NUM if payment == 0 else -(present + future) / payment
    paid = payment * (1 + rate * (kind != 0))
    owed = paid + present * rate
    if owed == 0 or rate <= -1:
        return NUM
    ratio = (paid - future * rate) / owed
    return NUM if ratio <= 0 else math.log(ratio) / math.log(1 + rate)


@form("NPV")
def npv(context, rate, values):
    if rate == -1:
        return DIV0
    return sum(value / (1 + rate) ** (at + 1) for at, value in enumerate(values))


def _root(slope: Callable[[float], tuple[float, float]], guess: float) -> float | Error:
    """Newton's method from the guess: #NUM! unless a step falls within Excel's tolerance in its
    twenty, then one step more, which takes the rate as close as a float holds it."""
    rate = guess
    try:
        for _ in range(STEPS):
            value, derivative = slope(rate)
            if derivative == 0:
                return NUM
            step = value / derivative
            rate -= step
            if abs(step) < TOLERANCE:
                value, derivative = slope(rate)
                return rate - value / derivative if derivative else rate
    except OverflowError, ZeroDivisionError:
        pass
    return NUM


@form("RATE")
def rate(context, periods, payment, present, future=0.0, kind=0.0, guess=0.1):
    kind = kind != 0
    if periods <= 0:
        return NUM

    def slope(rate: float) -> tuple[float, float]:
        if rate == 0:
            value = present + payment * periods + future
            return value, present * periods + payment * (
                periods * (periods - 1) / 2 + kind * periods
            )
        grown = (1 + rate) ** periods
        growing = periods * (1 + rate) ** (periods - 1)
        annuity = (grown - 1) / rate
        changing = (growing * rate - (grown - 1)) / rate**2
        value = present * grown + payment * (1 + rate * kind) * annuity + future
        return value, present * growing + payment * (kind * annuity + (1 + rate * kind) * changing)

    return _root(slope, guess)


@form("IRR")
def irr(context, values, guess=0.1):
    flows = []
    for each in cells(context, values) if isinstance(values, Area | Union | Matrix) else (values,):
        if isinstance(each, Error):
            return each
        if isinstance(each, float):
            flows.append(each)
    if not any(each > 0 for each in flows) or not any(each < 0 for each in flows):
        return NUM

    def slope(rate: float) -> tuple[float, float]:
        value = sum(flow / (1 + rate) ** at for at, flow in enumerate(flows))
        return value, sum(-at * flow / (1 + rate) ** (at + 1) for at, flow in enumerate(flows))

    return _root(slope, guess)
