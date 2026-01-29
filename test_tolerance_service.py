# test_tolerance_service.py
"""
L5: Unit tests for tolerance_service — equation parsing, evaluation, lookup, pass/fail.
Run with: python -m pytest test_tolerance_service.py -v
Or: python test_tolerance_service.py
"""

import sys
import unittest

# Allow running without pytest
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from tolerance_service import (
    parse_equation,
    list_variables,
    evaluate_tolerance_equation,
    evaluate_pass_fail,
    evaluate_tolerance_lookup,
    validate_equation_variables,
    ALLOWED_VARIABLES,
)


class TestParseEquation(unittest.TestCase):
    def test_valid_expressions(self):
        parse_equation("1 + 2")
        parse_equation("0.02 * abs(nominal)")
        parse_equation("nominal * 0.01")
        parse_equation("abs(nominal) + 0.1")
        parse_equation("min(1, 2)")
        parse_equation("max(ref1, ref2)")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_equation("")
        with self.assertRaises(ValueError):
            parse_equation("   ")

    def test_syntax_error_raises(self):
        with self.assertRaises(SyntaxError):
            parse_equation("1 +")
        with self.assertRaises(SyntaxError):
            parse_equation("nominal **")

    def test_disallowed_construct_raises(self):
        with self.assertRaises(ValueError):
            parse_equation("lambda x: x")
        with self.assertRaises((ValueError, SyntaxError)):
            parse_equation("x[0]")


class TestListVariables(unittest.TestCase):
    def test_nominal_reading(self):
        self.assertEqual(list_variables("nominal + reading"), ["nominal", "reading"])

    def test_ref1_ref2(self):
        self.assertEqual(list_variables("ref1 - ref2"), ["ref1", "ref2"])

    def test_no_vars(self):
        self.assertEqual(list_variables("1 + 2"), [])

    def test_invalid_returns_empty(self):
        self.assertEqual(list_variables("1 +"), [])


class TestEvaluateToleranceEquation(unittest.TestCase):
    def test_constant(self):
        self.assertAlmostEqual(evaluate_tolerance_equation("1.5", {}), 1.5)

    def test_nominal(self):
        self.assertAlmostEqual(
            evaluate_tolerance_equation("0.02 * abs(nominal)", {"nominal": 100}),
            2.0,
        )

    def test_division_by_zero_raises(self):
        with self.assertRaises(ValueError):
            evaluate_tolerance_equation("1 / 0", {})

    def test_missing_variable_raises(self):
        with self.assertRaises(ValueError):
            evaluate_tolerance_equation("nominal + 1", {})


class TestEvaluateToleranceLookup(unittest.TestCase):
    def test_empty_returns_zero(self):
        self.assertEqual(evaluate_tolerance_lookup(None, 10), 0.0)
        self.assertEqual(evaluate_tolerance_lookup("", 10), 0.0)

    def test_single_range(self):
        j = '[{"range_low": 0, "range_high": 10, "tolerance": 0.1}]'
        self.assertAlmostEqual(evaluate_tolerance_lookup(j, 5), 0.1)
        self.assertAlmostEqual(evaluate_tolerance_lookup(j, 0), 0.1)
        self.assertAlmostEqual(evaluate_tolerance_lookup(j, 10), 0.1)

    def test_multiple_ranges(self):
        j = (
            '[{"range_low": 0, "range_high": 10, "tolerance": 0.1}, '
            '{"range_low": 10, "range_high": 100, "tolerance": 0.5}]'
        )
        self.assertAlmostEqual(evaluate_tolerance_lookup(j, 5), 0.1)
        self.assertAlmostEqual(evaluate_tolerance_lookup(j, 50), 0.5)

    def test_no_match_returns_zero(self):
        j = '[{"range_low": 100, "range_high": 200, "tolerance": 1.0}]'
        self.assertEqual(evaluate_tolerance_lookup(j, 50), 0.0)


class TestEvaluatePassFail(unittest.TestCase):
    def test_fixed_pass(self):
        pass_, tol, _ = evaluate_pass_fail("fixed", 0.5, None, 10.0, 10.2)
        self.assertTrue(pass_)
        self.assertAlmostEqual(tol, 0.5)

    def test_fixed_fail(self):
        pass_, tol, _ = evaluate_pass_fail("fixed", 0.5, None, 10.0, 11.0)
        self.assertFalse(pass_)
        self.assertAlmostEqual(tol, 0.5)

    def test_percent(self):
        pass_, tol, _ = evaluate_pass_fail("percent", 2.0, None, 100.0, 101.0)
        self.assertTrue(pass_)  # 2% of 100 = 2, diff = 1
        self.assertAlmostEqual(tol, 2.0)

    def test_equation(self):
        pass_, tol, _ = evaluate_pass_fail(
            "equation", None, "0.02 * abs(nominal)", 100.0, 101.0,
            vars_map={},
            tolerance_lookup_json=None,
        )
        self.assertTrue(pass_, f"expected pass with tol={tol}")  # tol = 2, diff = 1
        self.assertAlmostEqual(tol, 2.0)

    def test_lookup(self):
        j = '[{"range_low": 0, "range_high": 100, "tolerance": 1.0}]'
        pass_, tol, _ = evaluate_pass_fail(
            "lookup", None, None, 50.0, 50.5,
            tolerance_lookup_json=j,
        )
        self.assertTrue(pass_)
        self.assertAlmostEqual(tol, 1.0)

    def test_legacy_fixed(self):
        pass_, tol, _ = evaluate_pass_fail(None, 0.1, None, 0.0, 0.05)
        self.assertTrue(pass_)
        self.assertAlmostEqual(tol, 0.1)

    def test_bool_pass_when_true(self):
        pass_, tol, _ = evaluate_pass_fail("bool", None, "true", 0.0, 1.0)
        self.assertTrue(pass_, "value True should PASS when pass_when=true")
        pass_, tol, _ = evaluate_pass_fail("bool", None, "true", 0.0, 0.0)
        self.assertFalse(pass_, "value False should FAIL when pass_when=true")

    def test_bool_pass_when_false(self):
        pass_, tol, _ = evaluate_pass_fail("bool", None, "false", 0.0, 0.0)
        self.assertTrue(pass_, "value False should PASS when pass_when=false")
        pass_, tol, _ = evaluate_pass_fail("bool", None, "false", 0.0, 1.0)
        self.assertFalse(pass_, "value True should FAIL when pass_when=false")


class TestValidateEquationVariables(unittest.TestCase):
    def test_allowed(self):
        ok, unknown = validate_equation_variables("nominal + reading")
        self.assertTrue(ok)
        self.assertEqual(unknown, [])

    def test_unknown(self):
        ok, unknown = validate_equation_variables("nominal + xyz")
        self.assertFalse(ok)
        self.assertIn("xyz", unknown)


def run_unittest():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    success = run_unittest().wasSuccessful()
    sys.exit(0 if success else 1)
