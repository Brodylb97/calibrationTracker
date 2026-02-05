# tolerance_service.py
"""
Central tolerance evaluation for calibration templates.
Single source of truth for: tolerance types, equation parsing, pass/fail logic.
Used by CalibrationFormDialog and (future) template preview / explain.
See TEMPLATE_SYSTEM_IMPROVEMENT_PLAN.md for full design.

Equations use Excel-like syntax: + - * / ^ (power), < > <= >=, and functions:
  ABS(), MIN(), MAX(), ROUND(), AVERAGE()
  LINEST(ys, xs) - slope of least-squares line
  INTERCEPT(ys, xs) - y-intercept of regression line
  RSQ(ys, xs) - R-squared (coefficient of determination)
  CORREL(ys, xs) - Pearson correlation coefficient
  STDEV([vals]) - sample standard deviation
  STDEVP([vals]) - population standard deviation
  MEDIAN([vals]) - median of values
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any


def _excel_to_python(equation: str) -> str:
    """
    Convert Excel-style equation to Python-parseable form.
    - ^ (caret) → ** (exponentiation)
    - ABS(), MIN(), MAX(), ROUND() accepted in any case (normalized to lowercase for ast).
    """
    s = equation.strip()
    # Excel uses ^ for power
    s = s.replace("^", "**")
    # Allow Excel-style function names (case-insensitive)
    s = re.sub(
        r"\b(ABS|MIN|MAX|ROUND|AVERAGE|LINEST|INTERCEPT|RSQ|CORREL|STDEV|STDEVP|MEDIAN|PLOT)\s*\(",
        lambda m: m.group(1).lower() + "(",
        s,
        flags=re.IGNORECASE,
    )
    return s


def _average(*args: float) -> float:
    """Average of arguments (returns 0 if no args)."""
    if not args:
        return 0.0
    return sum(args) / len(args)


def _linest(known_ys: list[float], known_xs: list[float]) -> float:
    """
    Simple linear regression: fit y = mx + b by least squares.
    Returns the slope m. Uses equal-length lists known_ys and known_xs.
    If lengths differ or variance of x is zero, returns 0.0.
    """
    if not known_ys or not known_xs or len(known_ys) != len(known_xs):
        return 0.0
    n = len(known_ys)
    sum_x = sum(known_xs)
    sum_y = sum(known_ys)
    sum_xx = sum(x * x for x in known_xs)
    sum_xy = sum(x * y for x, y in zip(known_xs, known_ys))
    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return float(slope)


def _intercept(known_ys: list[float], known_xs: list[float]) -> float:
    """Y-intercept b of least-squares line y = mx + b."""
    if not known_ys or not known_xs or len(known_ys) != len(known_xs):
        return 0.0
    n = len(known_ys)
    mean_y = sum(known_ys) / n
    mean_x = sum(known_xs) / n
    slope = _linest(known_ys, known_xs)
    return float(mean_y - slope * mean_x)


def _rsq(known_ys: list[float], known_xs: list[float]) -> float:
    """R-squared (coefficient of determination) for linear regression."""
    if not known_ys or not known_xs or len(known_ys) != len(known_xs):
        return 0.0
    n = len(known_ys)
    mean_y = sum(known_ys) / n
    slope = _linest(known_ys, known_xs)
    intercept = _intercept(known_ys, known_xs)
    ss_tot = sum((y - mean_y) ** 2 for y in known_ys)
    if ss_tot == 0:
        return 1.0
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(known_xs, known_ys))
    return float(1.0 - ss_res / ss_tot)


def _correl(known_ys: list[float], known_xs: list[float]) -> float:
    """Pearson correlation coefficient between two lists."""
    if not known_ys or not known_xs or len(known_ys) != len(known_xs):
        return 0.0
    n = len(known_ys)
    sum_x = sum(known_xs)
    sum_y = sum(known_ys)
    sum_xx = sum(x * x for x in known_xs)
    sum_yy = sum(y * y for y in known_ys)
    sum_xy = sum(x * y for x, y in zip(known_xs, known_ys))
    denom = (n * sum_xx - sum_x * sum_x) * (n * sum_yy - sum_y * sum_y)
    if denom <= 0:
        return 0.0
    return float((n * sum_xy - sum_x * sum_y) / (denom ** 0.5))


def _stdev(values: list[float]) -> float:
    """Sample standard deviation (n-1 denominator)."""
    if not values or len(values) < 2:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return float(variance ** 0.5)


def _stdevp(values: list[float]) -> float:
    """Population standard deviation (n denominator)."""
    if not values:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return float(variance ** 0.5)


def _median(values: list[float]) -> float:
    """Median of values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_vals[mid])
    return float((sorted_vals[mid - 1] + sorted_vals[mid]) / 2)


# Allowed AST node types and binary ops (no eval of user input)
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
# Comparison ops return 1.0 (true) or 0.0 (false) for use in arithmetic
_ALLOWED_COMPARE = {
    ast.Lt: lambda a, b: 1.0 if a < b else 0.0,
    ast.Gt: lambda a, b: 1.0 if a > b else 0.0,
    ast.LtE: lambda a, b: 1.0 if a <= b else 0.0,
    ast.GtE: lambda a, b: 1.0 if a >= b else 0.0,
    ast.Eq: lambda a, b: 1.0 if a == b else 0.0,
    ast.NotEq: lambda a, b: 1.0 if a != b else 0.0,
}
# Symbol strings for display (e.g. "calculated op compared, PASS")
_COMPARE_SYMBOLS = {
    ast.Lt: "<",
    ast.Gt: ">",
    ast.LtE: "<=",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
}
_ALLOWED_UNARY = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_ALLOWED_FUNCS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "average": _average,
}


def _eval_node(node: ast.AST, vars_map: dict[str, float]) -> float:
    """Evaluate a single AST node with given variable map. Raises ValueError on disallowed ops."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("Only numeric constants allowed")
    if getattr(ast, "Num", None) and isinstance(node, ast.Num):  # Python < 3.8
        return float(node.n)
    if isinstance(node, ast.Name):
        v = vars_map.get(node.id)
        if v is None:
            raise ValueError(f"Variable '{node.id}' not provided")
        return float(v)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, vars_map)
        right = _eval_node(node.right, vars_map)
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Disallowed operator: {type(node.op).__name__}")
        if isinstance(node.op, ast.Div) and right == 0:
            raise ValueError("Division by zero")
        return op(left, right)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, vars_map)
        for op, comparator_node in zip(node.ops, node.comparators):
            right = _eval_node(comparator_node, vars_map)
            compare_fn = _ALLOWED_COMPARE.get(type(op))
            if compare_fn is None:
                raise ValueError(f"Disallowed comparison: {type(op).__name__}")
            if compare_fn(left, right) == 0.0:
                return 0.0
            left = right
        return 1.0
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARY.get(type(node.op))
        if op is None:
            raise ValueError(f"Disallowed unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand, vars_map))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls allowed")
        # Two-list args: LINEST, INTERCEPT, RSQ, CORREL
        two_list_funcs = {
            "linest": _linest,
            "intercept": _intercept,
            "rsq": _rsq,
            "correl": _correl,
        }
        if node.func.id in two_list_funcs:
            if len(node.args) != 2:
                raise ValueError(
                    f"{node.func.id.upper()} requires two arguments: [known_y's], [known_x's]"
                )
            for arg in node.args:
                if not isinstance(arg, ast.List):
                    raise ValueError(
                        f"{node.func.id.upper()} arguments must be lists, "
                        "e.g. LINEST([val1,val2], [ref1,ref2])"
                    )
            list_y = [_eval_node(elt, vars_map) for elt in node.args[0].elts]
            list_x = [_eval_node(elt, vars_map) for elt in node.args[1].elts]
            return float(two_list_funcs[node.func.id](list_y, list_x))
        # Single-list args: STDEV, STDEVP, MEDIAN
        one_list_funcs = {"stdev": _stdev, "stdevp": _stdevp, "median": _median}
        if node.func.id in one_list_funcs:
            if len(node.args) != 1:
                raise ValueError(
                    f"{node.func.id.upper()} requires one argument: [val1, val2, ...]"
                )
            if not isinstance(node.args[0], ast.List):
                raise ValueError(
                    f"{node.func.id.upper()} argument must be a list, "
                    "e.g. STDEV([val1, val2, val3])"
                )
            vals = [_eval_node(elt, vars_map) for elt in node.args[0].elts]
            return float(one_list_funcs[node.func.id](vals))
        if node.func.id not in _ALLOWED_FUNCS:
            raise ValueError(f"Disallowed function: {node.func.id}")
        args = [_eval_node(a, vars_map) for a in node.args]
        return float(_ALLOWED_FUNCS[node.func.id](*args))
    if isinstance(node, ast.List):
        raise ValueError(
            "List literals are only allowed inside LINEST, INTERCEPT, RSQ, CORREL, STDEV, STDEVP, MEDIAN"
        )
    raise ValueError(f"Unsupported expression: {type(node).__name__}")


def parse_equation(equation: str) -> ast.Expression:
    """
    Parse tolerance equation string (Excel-like: + - * / ^ and ABS, MIN, MAX, ROUND).
    Returns AST body.

    Raises:
        ValueError: On disallowed construct (attribute access, etc.) or empty equation.
        SyntaxError: From ast.parse when input is incomplete (e.g. "val1 + ").
    Callers should catch both ValueError and SyntaxError for incomplete or invalid input.
    """
    if not (equation or "").strip():
        raise ValueError("Equation is empty")
    eq = _excel_to_python(equation.strip())
    tree = ast.parse(eq, mode="eval")
    # Reject attribute access, subscripts, etc. (ast.List allowed only as argument to LINEST)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Subscript, ast.Lambda, ast.Dict)):
            raise ValueError(
                "Only numeric expressions with + - * / ^ < > <= >= and "
                "ABS, MIN, MAX, ROUND, AVERAGE, LINEST, INTERCEPT, RSQ, CORREL, STDEV, STDEVP, MEDIAN allowed"
            )
    return tree.body


def list_variables(equation: str) -> list[str]:
    """Return ordered list of variable names used in the equation (excludes function names)."""
    try:
        eq = _excel_to_python(equation.strip())
        tree = ast.parse(eq, mode="eval")
    except SyntaxError:
        return []
    names = []
    seen = set()
    _func_names = set(_ALLOWED_FUNCS) | {
        "linest", "intercept", "rsq", "correl", "stdev", "stdevp", "median", "plot"
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(getattr(node, "ctx", None), ast.Load):
            if node.id in _func_names:
                continue  # skip function names (abs, min, max, round, average, linest, plot)
            if node.id not in seen:
                seen.add(node.id)
                names.append(node.id)
    return names


def parse_plot_equation(equation: str) -> tuple[list[str], list[str]]:
    """
    Parse PLOT([x1, x2, ...], [y1, y2, ...]) equation.
    Returns (x_var_names, y_var_names). Each list contains variable names (val1, ref1, etc.).
    Total number of variables must be between 1 and 12.

    Raises:
        ValueError: On invalid form (wrong structure, unknown variables, etc.).
        SyntaxError: From ast.parse when input is incomplete (e.g. "PLOT([val1,").
    Callers should catch both ValueError and SyntaxError for incomplete or invalid input.
    """
    if not (equation or "").strip():
        raise ValueError("Plot equation is empty")
    eq = _excel_to_python(equation.strip())
    tree = ast.parse(eq, mode="eval")
    body = tree.body
    if not isinstance(body, ast.Call) or not isinstance(body.func, ast.Name):
        raise ValueError("Plot must be PLOT([x1, x2, ...], [y1, y2, ...])")
    if body.func.id != "plot":
        raise ValueError("Plot must be PLOT([x1, x2, ...], [y1, y2, ...])")
    if len(body.args) != 2:
        raise ValueError("PLOT requires two arguments: [x values], [y values]")
    x_list = body.args[0]
    y_list = body.args[1]
    if not isinstance(x_list, ast.List) or not isinstance(y_list, ast.List):
        raise ValueError("PLOT arguments must be lists, e.g. PLOT([val1, val2], [val3, val4])")

    def names_from_list(node_list: ast.List) -> list[str]:
        out = []
        for elt in node_list.elts:
            if not isinstance(elt, ast.Name):
                raise ValueError("PLOT lists must contain only variable names (val1, val2, ...)")
            out.append(elt.id)
        return out

    x_names = names_from_list(x_list)
    y_names = names_from_list(y_list)
    if len(x_names) != len(y_names):
        raise ValueError("PLOT X and Y lists must have the same length")
    total = len(x_names) + len(y_names)
    if total == 0:
        raise ValueError("PLOT must have at least one point")
    if total > 12:
        raise ValueError("PLOT allows at most 12 variables total (x count + y count)")
    for n in x_names + y_names:
        if n not in ALLOWED_VARIABLES:
            raise ValueError(f"Unknown variable in PLOT: {n}. Use val1..val12 or ref1..ref12.")
    return (x_names, y_names)


def evaluate_plot_equation(equation: str, vars_map: dict[str, float] | None) -> tuple[list[float], list[float]]:
    """
    Evaluate PLOT([x vars], [y vars]) with given vars_map (ref1/val1 etc.).
    Returns (x_values, y_values) as two lists of floats for charting.

    If vars_map is None, treats it as an empty dict (callers will get "Variable not provided" for any ref).
    """
    if vars_map is None:
        vars_map = {}
    v = _ensure_val_aliases(dict(vars_map))
    x_names, y_names = parse_plot_equation(equation)
    xs = []
    ys = []
    for n in x_names:
        val = v.get(n)
        if val is None:
            raise ValueError(f"Variable '{n}' not provided for plot")
        xs.append(float(val))
    for n in y_names:
        val = v.get(n)
        if val is None:
            raise ValueError(f"Variable '{n}' not provided for plot")
        ys.append(float(val))
    return (xs, ys)


def _ensure_val_aliases(vars_map: dict[str, float]) -> dict[str, float]:
    """Ensure val1-val12 are set from ref1-ref12 for backward compatibility."""
    v = dict(vars_map)
    for i in range(1, 13):
        rk, vk = f"ref{i}", f"val{i}"
        if rk in v and vk not in v:
            v[vk] = v[rk]
        elif vk in v and rk not in v:
            v[rk] = v[vk]
    return v


def evaluate_tolerance_equation(equation: str, vars_map: dict[str, float]) -> float:
    """
    Evaluate equation with given variables. Returns tolerance value.
    Raises ValueError on parse error, disallowed op, or missing variable.
    val1-val5 are aliases for ref1-ref5.
    """
    v = _ensure_val_aliases(vars_map)
    body = parse_equation(equation)
    return _eval_node(body, v)


def evaluate_pass_fail(
    tolerance_type: str | None,
    tolerance_fixed: float | None,
    tolerance_equation: str | None,
    nominal: float,
    reading: float,
    vars_map: dict[str, float] | None = None,
    tolerance_lookup_json: str | None = None,
) -> tuple[bool, float, str]:
    """
    Evaluate pass/fail for a single point.
    tolerance_type: 'fixed' | 'percent' | 'equation' | 'lookup' | 'bool' | None (legacy fixed).
    For 'bool', tolerance_equation is 'true' or 'false' (the value that means pass); reading is 0.0/1.0.
    Returns (pass, tolerance_used, explanation_plain).
    """
    vars_map = vars_map or {}
    v = dict(vars_map)
    v.setdefault("nominal", nominal)
    v.setdefault("reading", reading)
    v = _ensure_val_aliases(v)

    if tolerance_type == "bool":
        # Boolean tolerance: pass when value matches configured pass value (true/false)
        pass_when_true = (tolerance_equation or "true").strip().lower() == "true"
        reading_bool = bool(reading) if isinstance(reading, bool) else (float(reading) != 0.0)
        pass_ = (reading_bool == pass_when_true)
        explanation = (
            f"Pass when value is {'True' if pass_when_true else 'False'}; "
            f"value is {reading_bool} → {'PASS' if pass_ else 'FAIL'}"
        )
        return pass_, 0.0, explanation

    if tolerance_type == "percent":
        tol_pct = tolerance_fixed or 0.0
        tol_value = abs(nominal) * (tol_pct / 100.0) if nominal else 0.0
        diff = abs(reading - nominal)
        pass_ = diff <= tol_value
        explanation = (
            f"Tolerance = {tol_pct}% of |nominal| = {tol_value}; "
            f"|reading − nominal| = {diff} → {'PASS' if pass_ else 'FAIL'}"
        )
        return pass_, tol_value, explanation

    if tolerance_type == "equation" and tolerance_equation:
        try:
            tol_value = evaluate_tolerance_equation(tolerance_equation, v)
        except ValueError as e:
            if "Division by zero" in str(e):
                return False, 0.0, f"Division by zero in equation → FAIL"
            return False, 0.0, f"Equation error: {e}"
        except Exception as e:
            return False, 0.0, f"Equation error: {e}"
        diff = abs(reading - nominal)
        # Equation result 0 or 1 (from comparison) = direct pass/fail; otherwise treat as tolerance band
        if abs(tol_value - round(tol_value)) < 1e-9 and 0 <= tol_value <= 1:
            pass_ = tol_value >= 0.5
            explanation = (
                f"Equation (condition) = {int(round(tol_value))} (1=pass, 0=fail) → {'PASS' if pass_ else 'FAIL'}"
            )
        else:
            pass_ = diff <= tol_value
            explanation = (
                f"Tolerance (from equation) = {tol_value}; "
                f"|reading − nominal| = {diff} → {'PASS' if pass_ else 'FAIL'}"
            )
        return pass_, tol_value, explanation

    if tolerance_type == "lookup" and tolerance_lookup_json:
        # L1: Lookup table — tolerance_lookup_json list of {range_low, range_high, tolerance}
        tol_value = evaluate_tolerance_lookup(tolerance_lookup_json, nominal)
        diff = abs(reading - nominal)
        pass_ = diff <= tol_value
        explanation = (
            f"Tolerance (from lookup) = {tol_value}; "
            f"|reading − nominal| = {diff} → {'PASS' if pass_ else 'FAIL'}"
        )
        return pass_, tol_value, explanation

    # fixed or legacy (tolerance_type None and tolerance column used)
    tol_value = tolerance_fixed or 0.0
    diff = abs(reading - nominal)
    pass_ = diff <= tol_value
    explanation = f"Tolerance = {tol_value}; diff = {diff} → {'PASS' if pass_ else 'FAIL'}"
    return pass_, tol_value, explanation


def evaluate_tolerance_lookup(
    lookup_json: str | None,
    nominal: float,
) -> float:
    """
    L1: Resolve tolerance from lookup table by nominal value.
    lookup_json: JSON array of {"range_low", "range_high", "tolerance"}.
    First range where range_low <= nominal < range_high (or <= range_high) wins.
    Returns 0.0 if no match or invalid JSON.
    """
    if not (lookup_json or "").strip():
        return 0.0
    import json
    try:
        rows = json.loads(lookup_json.strip())
    except (json.JSONDecodeError, TypeError):
        return 0.0
    if not isinstance(rows, list):
        return 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            low = float(row.get("range_low", float("-inf")))
            high = float(row.get("range_high", float("inf")))
            tol = float(row.get("tolerance", 0))
        except (TypeError, ValueError):
            continue
        if low <= nominal <= high:
            return abs(tol)
    return 0.0


# Allowed variable names for equation validation (val1-val12 are aliases for ref1-ref12)
ALLOWED_VARIABLES = {"nominal", "reading", "ref", "value", "abs_nominal"} | {
    f"ref{i}" for i in range(1, 13)
} | {f"val{i}" for i in range(1, 13)}


def validate_equation_variables(equation: str) -> tuple[bool, list[str]]:
    """
    Check that all variables in equation are in ALLOWED_VARIABLES.
    Returns (all_ok, list_of_unknown_names).
    """
    names = list_variables(equation)
    unknown = [n for n in names if n not in ALLOWED_VARIABLES]
    return len(unknown) == 0, unknown


def equation_has_pass_fail_condition(equation: str) -> bool:
    """
    Check that equation contains a comparison (<, >, <=, >=, ==).
    Used for tolerance equations that must express pass/fail.
    Stat-type fields use LINEST and do not require this check.
    """
    try:
        body = parse_equation(equation.strip())
    except (ValueError, SyntaxError):
        return False

    for node in ast.walk(body):
        if isinstance(node, ast.Compare):
            return True
    return False


def format_calculation_display(
    value: float, sig_figs: int | None = 3, decimal_places: int | None = None
) -> str:
    """Format a calculated value for display.
    If decimal_places is not None, format with that many decimal places (e.g. 2 -> 50.00).
    Otherwise use sig_figs significant figures (default 3).
    """
    try:
        if decimal_places is not None:
            return f"{value:.{decimal_places}f}"
        if value == 0:
            return "0"
        return f"{value:.{sig_figs or 3}g}"
    except (TypeError, ValueError):
        return str(value)


def equation_tolerance_display(
    equation: str, vars_map: dict[str, float]
) -> tuple[float, str, float, bool] | None:
    """
    For equation-type tolerance with a single comparison (e.g. reading <= 0.02*nominal),
    return (lhs_value, op_str, rhs_value, pass) for display as "lhs op rhs, PASS" or ", FAIL".
    Returns None if equation is not a single comparison (e.g. tolerance band expression).
    """
    if not (equation or "").strip():
        return None
    try:
        body = parse_equation(equation.strip())
    except (ValueError, SyntaxError):
        return None
    if not isinstance(body, ast.Compare) or len(body.ops) != 1 or len(body.comparators) != 1:
        return None
    v = _ensure_val_aliases(dict(vars_map))
    try:
        lhs = _eval_node(body.left, v)
        op = body.ops[0]
        op_str = _COMPARE_SYMBOLS.get(type(op))
        if op_str is None:
            return None
        rhs = _eval_node(body.comparators[0], v)
        compare_fn = _ALLOWED_COMPARE.get(type(op))
        if compare_fn is None:
            return None
        pass_ = compare_fn(lhs, rhs) >= 0.5
        return (lhs, op_str, rhs, pass_)
    except (ValueError, TypeError):
        return None
