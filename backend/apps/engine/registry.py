"""Excel's functions (D22), each defined here once: its name, the prefix xlsx stores a newer one
under, its category, its arguments and the kind of each. The kind of an argument carries Excel's
rules for what it takes, so a form gets its arguments as it needs them and each of Excel's
quirks is written once. A function's Python form is in `functions/` under its name, and its
arguments are written with it; a function without one is one Excel has and we do not compute
yet: it gives #NAME?, as Excel does for a name it does not know. The functions are Excel's
predefined ones (ECMA-376 Part 1 §18.17.7) and those [MS-XLSX] 2.2.3 extends them by, which
xlsx stores under _xlfn., by Microsoft's categories."""

from dataclasses import dataclass, replace
from enum import Enum

from .formats import HALVES, MOMENT, PERCENT, SHORT_DATE


class Carried(Enum):
    """What a function gives the cell of a formula over it as its number format, beyond a code
    of its own: the format its arguments carry, or the language's currency as Windows formats
    it."""

    ARGUMENTS = "arguments"
    MONEY = "money"


class Kind(Enum):
    """What an argument takes and how a value given to it is read."""

    NUMBER = "number"
    """One number: a logical is 1 or 0, a blank 0, text that reads as a number or a date that
    number, other text #VALUE!."""
    NUMBERS = "numbers"
    """Numbers to aggregate: one given as a value is read as NUMBER; in a reference only numbers
    count, and text, logicals and blanks are passed over."""
    VALUES = "values"
    """Every value given or in a reference, errors among them, as they are."""
    LOGICAL = "logical"
    """One logical: a number is TRUE unless 0, a blank FALSE, the text TRUE or FALSE that
    logical, other text #VALUE!."""
    LOGICALS = "logicals"
    """Logicals to combine: one given as a value is read as LOGICAL; in a reference text and
    blanks are passed over."""
    TEXT = "text"
    """One text: a number as Excel writes it in General, a logical as TRUE or FALSE, a blank
    empty."""
    TEXTS = "texts"
    """Texts to join: each value given or in a reference read as TEXT."""
    ANY = "any"
    """A value as it is, a blank kept apart from empty text."""
    ARRAY = "array"
    """A reference or an array of values, a reference kept as one."""
    RANGE = "range"
    """A reference, and nothing else."""
    CRITERION = "criterion"
    """A value read as a condition on cells: a comparison (">5", "<>a"), text with wildcards
    (* ? and ~), or a value matched as it is."""


@dataclass(frozen=True)
class Arg:
    """An argument by Excel's name for it. `repeat` starts a group of that many arguments, this
    one and those after it, which may be given again, each time whole, and the arguments after
    the group are those a call may end with; `lazy` is computed only when the form asks
    for it; `errors` takes an error as a value instead of giving it as the result; `logicals`
    False refuses a logical where a number is read, with #VALUE!, as the functions that came
    from Excel's Analysis ToolPak do."""

    name: str
    kind: Kind
    optional: bool = False
    repeat: int = 0
    lazy: bool = False
    errors: bool = False
    logicals: bool = True


@dataclass(frozen=True)
class Function:
    """A function of Excel's, by the name Excel writes it in English, its arguments None until
    its form is written. `defaults` takes an
    optional argument left empty, as in TEXTBEFORE(A1;"-";;1), as one not given, as Excel's
    newer functions do; the others read it as a blank (IF(TRUE;;2) is 0). `tolerance` is the
    precision Excel documents for a function it computes by iteration: its digits past that are
    the path its unpublished iteration took, so ours is held to Excel's only that far. `format`
    is the number format Excel gives the cell of a formula over it (carried.py): none, a code,
    or Carried's."""

    name: str
    category: str
    args: tuple[Arg, ...] | None
    prefix: str = ""
    volatile: bool = False
    defaults: bool = False
    tolerance: float = 0.0
    format: str | Carried = ""

    @property
    def stored(self) -> str:
        """The name as xlsx stores it."""
        return self.prefix + self.name


N, NS, V, L, LS, T, TS, A, AR, R, C = (
    Kind.NUMBER,
    Kind.NUMBERS,
    Kind.VALUES,
    Kind.LOGICAL,
    Kind.LOGICALS,
    Kind.TEXT,
    Kind.TEXTS,
    Kind.ANY,
    Kind.ARRAY,
    Kind.RANGE,
    Kind.CRITERION,
)
FUTURE = "_xlfn."
WORKSHEET = "_xlfn._xlws."


def _(name: str, kind: Kind, **given) -> Arg:
    return Arg(name, kind, **given)


def _o(name: str, kind: Kind, **given) -> Arg:
    return Arg(name, kind, optional=True, **given)


def _tp(name: str, optional: bool = False) -> Arg:
    return Arg(name, Kind.NUMBER, optional=optional, logicals=False)


def _ifs(first: str) -> tuple[Arg, ...]:
    return (_(first, R), _("criteria_range", R, repeat=2), _("criteria", C))


def _numbers(name: str = "number") -> tuple[Arg, ...]:
    return (_(name, NS, repeat=1),)


FUNCTIONS = {
    function.name: function
    for function in [
        # Logical
        Function(
            "IF",
            "logical",
            (
                _("logical_test", L),
                _("value_if_true", A, lazy=True),
                _o("value_if_false", A, lazy=True),
            ),
        ),
        Function(
            "IFS",
            "logical",
            (_("logical_test", L, repeat=2, lazy=True), _("value_if_true", A, lazy=True)),
            prefix=FUTURE,
        ),
        Function(
            "IFERROR", "logical", (_("value", A, errors=True), _("value_if_error", A, lazy=True))
        ),
        Function(
            "IFNA",
            "logical",
            (_("value", A, errors=True), _("value_if_na", A, lazy=True)),
            prefix=FUTURE,
        ),
        Function("AND", "logical", (_("logical", LS, repeat=1),)),
        Function("OR", "logical", (_("logical", LS, repeat=1),)),
        Function("XOR", "logical", (_("logical", LS, repeat=1),), prefix=FUTURE),
        Function("NOT", "logical", (_("logical", L),)),
        Function("TRUE", "logical", ()),
        Function("FALSE", "logical", ()),
        Function(
            "SWITCH",
            "logical",
            (
                _("expression", A),
                _("value", A, repeat=2, lazy=True),
                _("result", A, lazy=True),
                _o("default", A, lazy=True),
            ),
            prefix=FUTURE,
        ),
        # Information
        *(
            Function(name, "information", (_("value", A, errors=True),))
            for name in (
                "ISBLANK",
                "ISERROR",
                "ISERR",
                "ISNA",
                "ISNUMBER",
                "ISTEXT",
                "ISNONTEXT",
                "ISLOGICAL",
                "ERROR.TYPE",
            )
        ),
        Function("TYPE", "information", (_("value", AR),)),
        Function("ISEVEN", "information", (_tp("number"),)),
        Function("ISODD", "information", (_tp("number"),)),
        Function("NA", "information", ()),
        Function("N", "information", (_("value", A),)),
        # Lookup and reference
        Function(
            "VLOOKUP",
            "lookup",
            (
                _("lookup_value", A),
                _("table_array", AR),
                _("col_index_num", N),
                _o("range_lookup", L),
            ),
        ),
        Function(
            "HLOOKUP",
            "lookup",
            (
                _("lookup_value", A),
                _("table_array", AR),
                _("row_index_num", N),
                _o("range_lookup", L),
            ),
        ),
        Function(
            "XLOOKUP",
            "lookup",
            (
                _("lookup_value", A),
                _("lookup_array", AR),
                _("return_array", AR),
                _o("if_not_found", A),
                _o("match_mode", N),
                _o("search_mode", N),
            ),
            prefix=FUTURE,
            defaults=True,
        ),
        Function(
            "MATCH", "lookup", (_("lookup_value", A), _("lookup_array", AR), _o("match_type", N))
        ),
        Function(
            "XMATCH",
            "lookup",
            (
                _("lookup_value", A),
                _("lookup_array", AR),
                _o("match_mode", N),
                _o("search_mode", N),
            ),
            prefix=FUTURE,
            defaults=True,
        ),
        Function(
            "SORT",
            "lookup",
            (_("array", AR), _o("sort_index", N), _o("sort_order", N), _o("by_col", L)),
            prefix=WORKSHEET,
            defaults=True,
        ),
        Function(
            "LOOKUP",
            "lookup",
            (_("lookup_value", A), _("lookup_vector", AR), _o("result_vector", AR)),
        ),
        Function(
            "INDEX",
            "lookup",
            (_("array", AR), _("row_num", N), _o("column_num", N), _o("area_num", N)),
        ),
        Function("CHOOSE", "lookup", (_("index_num", N), _("value", A, repeat=1, lazy=True))),
        Function("ROW", "lookup", (_o("reference", R),)),
        Function("ROWS", "lookup", (_("array", AR),)),
        Function("COLUMN", "lookup", (_o("reference", R),)),
        Function("COLUMNS", "lookup", (_("array", AR),)),
        Function(
            "OFFSET",
            "lookup",
            (_("reference", R), _("rows", N), _("cols", N), _o("height", N), _o("width", N)),
            volatile=True,
        ),
        Function("INDIRECT", "lookup", (_("ref_text", T), _o("a1", L)), volatile=True),
        Function("HYPERLINK", "lookup", (_("link_location", T), _o("friendly_name", A))),
        Function(
            "ADDRESS",
            "lookup",
            (
                _("row_num", N),
                _("column_num", N),
                _o("abs_num", N),
                _o("a1", L),
                _o("sheet_text", T),
            ),
        ),
        # Math and trigonometry
        Function("SUM", "math", _numbers()),
        Function("SUMIF", "math", (_("range", R), _("criteria", C), _o("sum_range", R))),
        Function("SUMIFS", "math", _ifs("sum_range")),
        Function("SUMPRODUCT", "math", (_("array", AR, repeat=1),)),
        Function("SUBTOTAL", "math", (_("function_num", N), _("ref", R, repeat=1))),
        Function("PRODUCT", "math", _numbers()),
        Function("ROUND", "math", (_("number", N), _("num_digits", N))),
        Function("ROUNDUP", "math", (_("number", N), _("num_digits", N))),
        Function("ROUNDDOWN", "math", (_("number", N), _("num_digits", N))),
        Function("MROUND", "math", (_tp("number"), _tp("multiple"))),
        Function("INT", "math", (_("number", N),)),
        Function("TRUNC", "math", (_("number", N), _o("num_digits", N))),
        Function("ABS", "math", (_("number", N),)),
        Function("SIGN", "math", (_("number", N),)),
        Function("MOD", "math", (_("number", N), _("divisor", N))),
        Function("QUOTIENT", "math", (_tp("numerator"), _tp("denominator"))),
        Function("POWER", "math", (_("number", N), _("power", N))),
        Function("SQRT", "math", (_("number", N),)),
        Function("EXP", "math", (_("number", N),)),
        Function("LN", "math", (_("number", N),)),
        Function("LOG", "math", (_("number", N), _o("base", N))),
        Function("LOG10", "math", (_("number", N),)),
        Function("PI", "math", ()),
        Function("FACT", "math", (_("number", N),)),
        Function("EVEN", "math", (_("number", N),)),
        Function("ODD", "math", (_("number", N),)),
        Function("CEILING", "math", (_("number", N), _("significance", N))),
        Function(
            "CEILING.MATH",
            "math",
            (_("number", N), _o("significance", N), _o("mode", N)),
            prefix=FUTURE,
        ),
        Function("FLOOR", "math", (_("number", N), _("significance", N))),
        Function(
            "FLOOR.MATH",
            "math",
            (_("number", N), _o("significance", N), _o("mode", N)),
            prefix=FUTURE,
        ),
        Function("RAND", "math", (), volatile=True),
        Function("RANDBETWEEN", "math", (_("bottom", N), _("top", N)), volatile=True),
        # Statistical
        Function("AVERAGE", "statistical", _numbers()),
        Function(
            "AVERAGEIF", "statistical", (_("range", R), _("criteria", C), _o("average_range", R))
        ),
        Function("AVERAGEIFS", "statistical", _ifs("average_range")),
        Function("COUNT", "statistical", (_("value", V, repeat=1),)),
        Function("COUNTA", "statistical", (_("value", V, repeat=1),)),
        Function("COUNTBLANK", "statistical", (_("range", R),)),
        Function("COUNTIF", "statistical", (_("range", R), _("criteria", C))),
        Function("COUNTIFS", "statistical", (_("criteria_range", R, repeat=2), _("criteria", C))),
        Function("MAX", "statistical", _numbers()),
        Function("MIN", "statistical", _numbers()),
        Function("MAXIFS", "statistical", _ifs("max_range"), prefix=FUTURE),
        Function("MINIFS", "statistical", _ifs("min_range"), prefix=FUTURE),
        Function("MEDIAN", "statistical", _numbers()),
        Function("MODE", "statistical", _numbers()),
        Function("MODE.SNGL", "statistical", _numbers(), prefix=FUTURE),
        Function("LARGE", "statistical", (_("array", AR), _("k", N))),
        Function("SMALL", "statistical", (_("array", AR), _("k", N))),
        Function("RANK", "statistical", (_("number", N), _("ref", R), _o("order", N))),
        Function(
            "RANK.EQ", "statistical", (_("number", N), _("ref", R), _o("order", N)), prefix=FUTURE
        ),
        Function("STDEV", "statistical", _numbers()),
        Function("STDEV.S", "statistical", _numbers(), prefix=FUTURE),
        Function("STDEV.P", "statistical", _numbers(), prefix=FUTURE),
        Function("VAR", "statistical", _numbers()),
        Function("VAR.S", "statistical", _numbers(), prefix=FUTURE),
        Function("VAR.P", "statistical", _numbers(), prefix=FUTURE),
        Function("CORREL", "statistical", (_("array1", AR), _("array2", AR))),
        Function("PEARSON", "statistical", (_("array1", AR), _("array2", AR))),
        Function("RSQ", "statistical", (_("known_ys", AR), _("known_xs", AR))),
        Function("SLOPE", "statistical", (_("known_ys", AR), _("known_xs", AR))),
        Function("INTERCEPT", "statistical", (_("known_ys", AR), _("known_xs", AR))),
        # Text
        Function("CONCATENATE", "text", (_("text", T, repeat=1),)),
        Function("CONCAT", "text", (_("text", TS, repeat=1),), prefix=FUTURE),
        Function(
            "TEXTJOIN",
            "text",
            (_("delimiter", T), _("ignore_empty", L), _("text", TS, repeat=1)),
            prefix=FUTURE,
        ),
        Function("LEFT", "text", (_("text", T), _o("num_chars", N))),
        Function("RIGHT", "text", (_("text", T), _o("num_chars", N))),
        Function("MID", "text", (_("text", T), _("start_num", N), _("num_chars", N))),
        Function("LEN", "text", (_("text", T),)),
        Function("FIND", "text", (_("find_text", T), _("within_text", T), _o("start_num", N))),
        Function("SEARCH", "text", (_("find_text", T), _("within_text", T), _o("start_num", N))),
        Function(
            "SUBSTITUTE",
            "text",
            (_("text", T), _("old_text", T), _("new_text", T), _o("instance_num", N)),
        ),
        Function(
            "REPLACE",
            "text",
            (_("old_text", T), _("start_num", N), _("num_chars", N), _("new_text", T)),
        ),
        Function("TRIM", "text", (_("text", T),)),
        Function("UPPER", "text", (_("text", T),)),
        Function("LOWER", "text", (_("text", T),)),
        Function("PROPER", "text", (_("text", T),)),
        Function("TEXT", "text", (_("value", A), _("format_text", T))),
        Function("EXACT", "text", (_("text1", T), _("text2", T))),
        Function("REPT", "text", (_("text", T), _("number_times", N))),
        Function("CHAR", "text", (_("number", N),)),
        Function("CODE", "text", (_("text", T),)),
        Function("CLEAN", "text", (_("text", T),)),
        Function("VALUE", "text", (_("text", A),)),
        Function(
            "NUMBERVALUE",
            "text",
            (_("text", T), _o("decimal_separator", T), _o("group_separator", T)),
            prefix=FUTURE,
        ),
        Function(
            "TEXTBEFORE",
            "text",
            (
                _("text", T),
                _("delimiter", T),
                _o("instance_num", N),
                _o("match_mode", N),
                _o("match_end", N),
                _o("if_not_found", A),
            ),
            prefix=FUTURE,
            defaults=True,
        ),
        Function(
            "TEXTAFTER",
            "text",
            (
                _("text", T),
                _("delimiter", T),
                _o("instance_num", N),
                _o("match_mode", N),
                _o("match_end", N),
                _o("if_not_found", A),
            ),
            prefix=FUTURE,
            defaults=True,
        ),
        Function(
            "FIXED",
            "text",
            (_("number", N), _o("decimals", N), _o("no_commas", L)),
            defaults=True,
        ),
        Function("T", "text", (_("value", A),)),
        # Date and time
        Function("DATE", "date", (_("year", N), _("month", N), _("day", N))),
        Function("TIME", "date", (_("hour", N), _("minute", N), _("second", N))),
        Function("TODAY", "date", (), volatile=True),
        Function("NOW", "date", (), volatile=True),
        *(
            Function(name, "date", (_("serial_number", N),))
            for name in ("YEAR", "MONTH", "DAY", "HOUR", "MINUTE", "SECOND")
        ),
        Function("WEEKDAY", "date", (_("serial_number", N), _o("return_type", N))),
        Function("WEEKNUM", "date", (_tp("serial_number"), _tp("return_type", True))),
        Function("ISOWEEKNUM", "date", (_("date", N),), prefix=FUTURE),
        Function("EDATE", "date", (_tp("start_date"), _tp("months"))),
        Function("EOMONTH", "date", (_tp("start_date"), _tp("months"))),
        Function("DATEDIF", "date", (_("start_date", N), _("end_date", N), _("unit", T))),
        Function("DAYS", "date", (_("end_date", N), _("start_date", N)), prefix=FUTURE),
        Function("NETWORKDAYS", "date", (_tp("start_date"), _tp("end_date"), _o("holidays", AR))),
        Function("WORKDAY", "date", (_tp("start_date"), _tp("days"), _o("holidays", AR))),
        Function("DATEVALUE", "date", (_("date_text", T),)),
        Function("TIMEVALUE", "date", (_("time_text", T),)),
        Function("YEARFRAC", "date", (_tp("start_date"), _tp("end_date"), _tp("basis", True))),
        # Financial
        Function(
            "PMT", "financial", (_("rate", N), _("nper", N), _("pv", N), _o("fv", N), _o("type", N))
        ),
        Function(
            "PV", "financial", (_("rate", N), _("nper", N), _("pmt", N), _o("fv", N), _o("type", N))
        ),
        Function(
            "FV", "financial", (_("rate", N), _("nper", N), _("pmt", N), _o("pv", N), _o("type", N))
        ),
        Function(
            "NPER", "financial", (_("rate", N), _("pmt", N), _("pv", N), _o("fv", N), _o("type", N))
        ),
        Function(
            "RATE",
            "financial",
            (_("nper", N), _("pmt", N), _("pv", N), _o("fv", N), _o("type", N), _o("guess", N)),
            tolerance=1e-7,
        ),
        Function("NPV", "financial", (_("rate", N), _("value", NS, repeat=1))),
        Function("IRR", "financial", (_("values", AR), _o("guess", N)), tolerance=1e-7),
    ]
}

LISTED = {
    "compatibility": """
    BETADIST BETAINV BINOMDIST CHIDIST CHIINV CHITEST CONFIDENCE COVAR CRITBINOM EXPONDIST
    FDIST FINV FTEST GAMMADIST GAMMAINV HYPGEOMDIST LOGINV LOGNORMDIST NEGBINOMDIST NORMDIST
    NORMINV NORMSDIST NORMSINV PERCENTILE PERCENTRANK POISSON QUARTILE STDEVP TDIST TINV
    TTEST VARP WEIBULL ZTEST
    """,
    "cube": """
    CUBEKPIMEMBER CUBEMEMBER CUBEMEMBERPROPERTY CUBERANKEDMEMBER CUBESET CUBESETCOUNT
    CUBEVALUE
    """,
    "database": """
    DAVERAGE DCOUNT DCOUNTA DGET DMAX DMIN DPRODUCT DSTDEV DSTDEVP DSUM DVAR DVARP
    """,
    "date": """
    DAYS360 NETWORKDAYS.INTL WORKDAY.INTL
    """,
    "engineering": """
    BESSELI BESSELJ BESSELK BESSELY BIN2DEC BIN2HEX BIN2OCT _xlfn.BITAND _xlfn.BITLSHIFT
    _xlfn.BITOR _xlfn.BITRSHIFT _xlfn.BITXOR COMPLEX CONVERT DEC2BIN DEC2HEX DEC2OCT DELTA
    ERF _xlfn.ERF.PRECISE ERFC _xlfn.ERFC.PRECISE GESTEP HEX2BIN HEX2DEC HEX2OCT IMABS
    IMAGINARY IMARGUMENT IMCONJUGATE IMCOS _xlfn.IMCOSH _xlfn.IMCOT _xlfn.IMCSC _xlfn.IMCSCH
    IMDIV IMEXP IMLN IMLOG10 IMLOG2 IMPOWER IMPRODUCT IMREAL _xlfn.IMSEC _xlfn.IMSECH IMSIN
    _xlfn.IMSINH IMSQRT IMSUB IMSUM _xlfn.IMTAN OCT2BIN OCT2DEC OCT2HEX
    """,
    "financial": """
    ACCRINT ACCRINTM AMORDEGRC AMORLINC COUPDAYBS COUPDAYS COUPDAYSNC COUPNCD COUPNUM
    COUPPCD CUMIPMT CUMPRINC DB DDB DISC DOLLARDE DOLLARFR DURATION EFFECT FVSCHEDULE
    INTRATE IPMT ISPMT MDURATION MIRR NOMINAL ODDFPRICE ODDFYIELD ODDLPRICE ODDLYIELD
    _xlfn.PDURATION PPMT PRICE PRICEDISC PRICEMAT RECEIVED _xlfn.RRI SLN SYD TBILLEQ
    TBILLPRICE TBILLYIELD VDB XIRR XNPV YIELD YIELDDISC YIELDMAT
    """,
    "information": """
    CELL INFO _xlfn.ISFORMULA _xlfn.ISOMITTED ISREF _xlfn.SHEET _xlfn.SHEETS
    _xlfn.STOCKHISTORY
    """,
    "logical": """
    _xlfn.BYCOL _xlfn.BYROW _xlfn.LAMBDA _xlfn.LET _xlfn.MAKEARRAY _xlfn.MAP _xlfn.REDUCE
    _xlfn.SCAN
    """,
    "lookup": """
    AREAS _xlfn.CHOOSECOLS _xlfn.CHOOSEROWS _xlfn.DROP _xlfn.EXPAND _xlfn.FIELDVALUE
    _xlfn._xlws.FILTER _xlfn.FORMULATEXT GETPIVOTDATA _xlfn.GROUPBY _xlfn.HSTACK _xlfn.IMAGE
    _xlfn.PIVOTBY _xlfn.PQSOURCE _xlfn.QUERYSTRING RTD _xlfn.SORTBY
    _xlfn.TAKE _xlfn.TOCOL _xlfn.TOROW TRANSPOSE _xlfn.TRIMRANGE _xlfn.UNIQUE _xlfn.VSTACK
    _xlfn.WRAPCOLS _xlfn.WRAPROWS
    """,
    "math": """
    ACOS ACOSH _xlfn.ACOT _xlfn.ACOTH _xlfn.AGGREGATE _xlfn.ARABIC ASIN ASINH ATAN ATAN2
    ATANH _xlfn.BASE _xlfn.CEILING.PRECISE COMBIN _xlfn.COMBINA COS COSH _xlfn.COT
    _xlfn.COTH _xlfn.CSC _xlfn.CSCH _xlfn.DECIMAL DEGREES ECMA.CEILING FACTDOUBLE
    _xlfn.FLOOR.PRECISE GCD ISO.CEILING LCM MDETERM MINVERSE MMULT MULTINOMIAL _xlfn.MUNIT
    _xlfn.PERCENTOF RADIANS _xlfn.RANDARRAY ROMAN _xlfn.SEC _xlfn.SECH _xlfn.SEQUENCE
    SERIESSUM SIN SINH SQRTPI SUMSQ SUMX2MY2 SUMX2PY2 SUMXMY2 TAN TANH
    """,
    "python": """
    _xlfn._xlws.PY _xlfn.PYTHON_STR _xlfn.PYTHON_TYPE _xlfn.PYTHON_TYPENAME
    """,
    "statistical": """
    AVEDEV AVERAGEA _xlfn.BETA.DIST _xlfn.BETA.INV _xlfn.BINOM.DIST _xlfn.BINOM.DIST.RANGE
    _xlfn.BINOM.INV _xlfn.CHISQ.DIST _xlfn.CHISQ.DIST.RT _xlfn.CHISQ.INV _xlfn.CHISQ.INV.RT
    _xlfn.CHISQ.TEST _xlfn.CONFIDENCE.NORM _xlfn.CONFIDENCE.T _xlfn.COVARIANCE.P
    _xlfn.COVARIANCE.S DEVSQ _xlfn.EXPON.DIST _xlfn.F.DIST _xlfn.F.DIST.RT _xlfn.F.INV
    _xlfn.F.INV.RT _xlfn.F.TEST FISHER FISHERINV FORECAST _xlfn.FORECAST.ETS
    _xlfn.FORECAST.ETS.CONFINT _xlfn.FORECAST.ETS.SEASONALITY _xlfn.FORECAST.ETS.STAT
    _xlfn.FORECAST.LINEAR FREQUENCY _xlfn.GAMMA _xlfn.GAMMA.DIST _xlfn.GAMMA.INV GAMMALN
    _xlfn.GAMMALN.PRECISE _xlfn.GAUSS GEOMEAN GROWTH HARMEAN _xlfn.HYPGEOM.DIST
    KURT LINEST LOGEST _xlfn.LOGNORM.DIST _xlfn.LOGNORM.INV MAXA MINA _xlfn.MODE.MULT
    _xlfn.NEGBINOM.DIST _xlfn.NORM.DIST _xlfn.NORM.INV _xlfn.NORM.S.DIST _xlfn.NORM.S.INV
    _xlfn.PERCENTILE.EXC _xlfn.PERCENTILE.INC _xlfn.PERCENTRANK.EXC
    _xlfn.PERCENTRANK.INC PERMUT _xlfn.PERMUTATIONA _xlfn.PHI _xlfn.POISSON.DIST PROB
    _xlfn.QUARTILE.EXC _xlfn.QUARTILE.INC _xlfn.RANK.AVG SKEW _xlfn.SKEW.P
    STANDARDIZE STDEVA STDEVPA STEYX _xlfn.T.DIST _xlfn.T.DIST.2T _xlfn.T.DIST.RT
    _xlfn.T.INV _xlfn.T.INV.2T _xlfn.T.TEST TREND TRIMMEAN VARA VARPA _xlfn.WEIBULL.DIST
    _xlfn.Z.TEST
    """,
    "text": """
    _xlfn.ARRAYTOTEXT ASC BAHTTEXT _xlfn.DBCS _xlfn.DETECTLANGUAGE DOLLAR FINDB JIS LEFTB
    LENB MIDB PHONETIC _xlfn.REGEXEXTRACT _xlfn.REGEXREPLACE _xlfn.REGEXTEST REPLACEB RIGHTB
    SEARCHB _xlfn.TEXTSPLIT _xlfn.TRANSLATE _xlfn.UNICHAR _xlfn.UNICODE USDOLLAR
    _xlfn.VALUETOTEXT
    """,
    "web": """
    _xlfn.ENCODEURL _xlfn.FILTERXML _xlfn.WEBSERVICE
    """,
}


for category, names in LISTED.items():
    for stored in names.split():
        name = stored.removeprefix(WORKSHEET).removeprefix(FUTURE)
        FUNCTIONS[name] = Function(name, category, None, prefix=stored[: len(stored) - len(name)])

# The number format Excel gives the cell of a formula over each function that gives one, as
# Excel gave it under either regional format (implied.py's files).
FORMATS = {
    **dict.fromkeys(
        ("AVERAGE", "INT", "MAX", "MEDIAN", "MIN", "MOD", "ROUND", "ROUNDDOWN", "ROUNDUP", "SUM",
         "TRUNC"),
        Carried.ARGUMENTS,
    ),
    **dict.fromkeys(
        ("DB", "DDB", "FV", "IPMT", "NPV", "PMT", "PPMT", "PV", "SLN", "SYD", "VDB"), Carried.MONEY
    ),
    **dict.fromkeys(("IRR", "MIRR", "RATE"), PERCENT),
    "DATE": SHORT_DATE,
    "TODAY": SHORT_DATE,
    "NOW": MOMENT,
    "TIME": HALVES,
}  # fmt: skip
for name, format in FORMATS.items():
    FUNCTIONS[name] = replace(FUNCTIONS[name], format=format)
