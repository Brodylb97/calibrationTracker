# tolerance_service.py
"""
Central tolerance evaluation for calibration templates.
Single source of truth for: tolerance types, equation parsing, pass/fail logic.
Used by CalibrationFormDialog and (future) template preview / explain.
See TEMPLATE_SYSTEM_IMPROVEMENT_PLAN.md for full design.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

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
_ALLOWED_UNARY = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_ALLOWED_FUNCS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
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
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARY.get(type(node.op))
        if op is None:
            raise ValueError(f"Disallowed unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand, vars_map))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls allowed")
        if node.func.id not in _ALLOWED_FUNCS:
            raise ValueError(f"Disallowed function: {node.func.id}")
        args = [_eval_node(a, vars_map) for a in node.args]
        return float(_ALLOWED_FUNCS[node.func.id](*args))
    raise ValueError(f"Unsupported expression: {type(node).__name__}")


def parse_equation(equation: str) -> ast.Expression:
    """
    Parse tolerance equation string. Returns AST body.
    Raises ValueError on syntax error or disallowed construct.
    """
    if not (equation or "").strip():
        raise ValueError("Equation is empty")
    tree = ast.parse(equation.strip(), mode="eval")
    # Reject attribute access, subscripts, etc.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Subscript, ast.Lambda, ast.List, ast.Dict)):
            raise ValueError("Only numeric expressions with + - * / ** and abs/min/max allowed")
    return tree.body


def list_variables(equation: str) -> list[str]:
    """Return ordered list of variable names used in the equation."""
    try:
        tree = ast.parse(equation.strip(), mode="eval")
    except SyntaxError:
        return []
    names = []
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(getattr(node, "ctx", None), ast.Load):
            if node.id not in seen:
                seen.add(node.id)
                names.append(node.id)
    return names


def evaluate_tolerance_equation(equation: str, vars_map: dict[str, float]) -> float:
    """
    Evaluate equation with given variables. Returns tolerance value.
    Raises ValueError on parse error, disallowed op, or missing variable.
    """
    body = parse_equation(equation)
    return _eval_node(body, vars_map)


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
    # Ensure nominal/reading in map for equation
    v = dict(vars_map)
    v.setdefault("nominal", nominal)
    v.setdefault("reading", reading)

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
        except Exception as e:
            return False, 0.0, f"Equation error: {e}"
        diff = abs(reading - nominal)
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


# Allowed variable names for equation validation (extend as needed)
ALLOWED_VARIABLES = {"nominal", "reading", "ref1", "ref2", "ref", "value", "abs_nominal"}


def validate_equation_variables(equation: str) -> tuple[bool, list[str]]:
    """
    Check that all variables in equation are in ALLOWED_VARIABLES.
    Returns (all_ok, list_of_unknown_names).
    """
    names = list_variables(equation)
    unknown = [n for n in names if n not in ALLOWED_VARIABLES]
    return len(unknown) == 0, unknown
