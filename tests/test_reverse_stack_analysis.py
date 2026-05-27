import contextlib
import ctypes
import io
import math
import os
import re
import sys
from dataclasses import dataclass
import unittest

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

import autodiff
import check
import codegen_c
import compiler
import parser


LINEAR_ACCUM = """
def linear_accum(x : In[float], n : In[int]) -> float:
    i : int = 0
    z : float = 0.0
    while (i < n, max_iter := 10):
        z = z + x * x
        i = i + 1
    return z

rev_linear_accum = rev_diff(linear_accum)
"""


NONLINEAR_RECURRENCE = """
def nonlinear_recurrence(x : In[float], n : In[int]) -> float:
    i : int = 0
    z : float = x
    while (i < n, max_iter := 10):
        z = sin(z)
        i = i + 1
    return z

rev_nonlinear_recurrence = rev_diff(nonlinear_recurrence)
"""


LINEAR_THEN_NONLINEAR = """
def linear_then_nonlinear(x : In[float], n : In[int]) -> float:
    i : int = 0
    z : float = 0.0
    y : float = 0.0
    while (i < n, max_iter := 10):
        z = z + x
        y = sin(z)
        i = i + 1
    return y

rev_linear_then_nonlinear = rev_diff(linear_then_nonlinear)
"""


NESTED_LINEAR_ACCUM = """
def nested_linear_accum(x : In[float], n : In[int], m : In[int]) -> float:
    i : int = 0
    j : int = 0
    z : float = 0.0
    while (i < n, max_iter := 10):
        j = 0
        while (j < m, max_iter := 10):
            z = z + x
            j = j + 1
        i = i + 1
    return z

rev_nested_linear_accum = rev_diff(nested_linear_accum)
"""


def differentiated_c_code(source):
    with contextlib.redirect_stdout(io.StringIO()):
        structs, funcs = parser.parse(source)
        structs, diff_structs, funcs = autodiff.resolve_diff_types(structs, funcs)
        check.check_ir(structs, diff_structs, funcs, check_diff=False)
        funcs = autodiff.differentiate(structs, diff_structs, funcs)
        check.check_ir(structs, diff_structs, funcs, check_diff=True)
        return codegen_c.codegen_c(structs, funcs)


def float_stack_slots(c_code):
    return sum(int(size) for size in re.findall(r"float _t_float_[A-Za-z0-9]+\[(\d+)\];", c_code))


def stack_slots_by_type(c_code):
    slots_by_type = {"float": 0, "int": 0}
    for c_type, size in re.findall(r"\b(float|int) _t_(?:float|int)_[A-Za-z0-9]+\[(\d+)\];", c_code):
        slots_by_type[c_type] += int(size)
    return slots_by_type


def total_stack_bytes(float_slots, int_slots):
    return float_slots * 4 + int_slots * 4


def compile_quiet(source, output_filename):
    with contextlib.redirect_stdout(io.StringIO()):
        return compiler.compile(source, target="c", output_filename=output_filename)


@dataclass(frozen=True)
class StackBenchmark:
    name: str
    source: str
    conservative_float_slots_per_iter: int
    notes: str
    loop_depth: int = 1


STACK_BENCHMARKS = [
    StackBenchmark(
        "linear_accumulation",
        LINEAR_ACCUM,
        conservative_float_slots_per_iter=1,
        notes="Old z values are not needed by reverse AD.",
    ),
    StackBenchmark(
        "nonlinear_recurrence",
        NONLINEAR_RECURRENCE,
        conservative_float_slots_per_iter=1,
        notes="sin(z) needs the old z value.",
    ),
    StackBenchmark(
        "linear_then_sin",
        LINEAR_THEN_NONLINEAR,
        conservative_float_slots_per_iter=2,
        notes="z = z + x is linear, but the later sin(z) needs z.",
    ),
    StackBenchmark(
        "nested_linear_accumulation",
        NESTED_LINEAR_ACCUM,
        conservative_float_slots_per_iter=1,
        notes="Nested linear recurrence; old z values scale with max_iter squared before analysis.",
        loop_depth=2,
    ),
]


def source_with_max_iter(source, max_iter):
    return re.sub(r"max_iter\s*:=\s*\d+", f"max_iter := {max_iter}", source)


def stack_report_rows(max_iters):
    rows = []
    for bench in STACK_BENCHMARKS:
        for max_iter in max_iters:
            code = differentiated_c_code(source_with_max_iter(bench.source, max_iter))
            after_slots = stack_slots_by_type(code)
            before_float_slots = bench.conservative_float_slots_per_iter * (max_iter ** bench.loop_depth)
            before_bytes = total_stack_bytes(before_float_slots, after_slots["int"])
            after_bytes = total_stack_bytes(after_slots["float"], after_slots["int"])
            rows.append({
                "benchmark": bench.name,
                "max_iter": max_iter,
                "before_float_slots": before_float_slots,
                "after_float_slots": after_slots["float"],
                "int_slots": after_slots["int"],
                "before_bytes": before_bytes,
                "after_bytes": after_bytes,
                "float_reduction": before_float_slots - after_slots["float"],
                "byte_reduction": before_bytes - after_bytes,
                "notes": bench.notes,
            })
    return rows


def percent_reduction(before, after):
    if before == 0:
        return "0.0%"
    return f"{100.0 * (before - after) / before:.1f}%"


def write_result_report(output_path="result.md"):
    rows = stack_report_rows(range(1, 11))
    summary_rows = [row for row in rows if row["max_iter"] == 10]

    lines = [
        "# Reverse-Mode Stack Analysis Results",
        "",
        "These numbers are generated from the differentiated C emitted by `tests/test_reverse_stack_analysis.py`.",
        "`Before` is the old conservative policy: cache every overwritten float value in a loop.",
        "`After` is the current dependency-aware reverse-mode stack allocation.",
        "Peak bytes include both float primal stacks and unchanged integer loop-index stacks.",
        "",
        "## Summary at max_iter = 10",
        "",
        "| Benchmark | Before float slots | After float slots | Int slots | Float reduction | Before peak bytes | After peak bytes | Byte reduction | Notes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for row in summary_rows:
        lines.append(
            "| {benchmark} | {before_float_slots} | {after_float_slots} | {int_slots} | {float_pct} | "
            "{before_bytes} | {after_bytes} | {byte_pct} | {notes} |".format(
                **row,
                float_pct=percent_reduction(row["before_float_slots"], row["after_float_slots"]),
                byte_pct=percent_reduction(row["before_bytes"], row["after_bytes"]),
            )
        )

    lines += [
        "",
        "## Stack Growth vs Static Loop Bound",
        "",
        "| Benchmark | max_iter | Before float slots | After float slots | Int slots | Before peak bytes | After peak bytes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        lines.append(
            "| {benchmark} | {max_iter} | {before_float_slots} | {after_float_slots} | "
            "{int_slots} | {before_bytes} | {after_bytes} |".format(**row)
        )

    lines += [
        "",
        "## Correctness Checks",
        "",
        "| Benchmark | Checked derivative |",
        "|---|---|",
        "| linear_accumulation | `d/dx sum_i x*x = 2*x*n` |",
        "| nonlinear_recurrence | product of `cos(z_i)` terms |",
        "| linear_then_sin | `d/dx sin(n*x) = n*cos(n*x)` |",
        "| nested_linear_accumulation | `d/dx sum_i sum_j x = n*m` |",
        "",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


class ReverseStackAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(os.path.dirname(os.path.realpath(__file__)))
        write_result_report()

    def setUp(self):
        os.chdir(os.path.dirname(os.path.realpath(__file__)))

    def test_linear_loop_accumulation_eliminates_float_stack(self):
        code = differentiated_c_code(LINEAR_ACCUM)

        conservative_stack_slots_before_analysis = 10
        self.assertEqual(float_stack_slots(code), 0)
        self.assertLess(float_stack_slots(code), conservative_stack_slots_before_analysis)

        _, lib = compile_quiet(LINEAR_ACCUM, "_code/rev_stack_linear_accum")
        dx = ctypes.c_float(0.0)
        dn = ctypes.c_int(0)
        x = 1.75
        n = 6
        lib.rev_linear_accum(x, ctypes.byref(dx), n, ctypes.byref(dn), 1.0)
        self.assertAlmostEqual(dx.value, 2.0 * x * n, places=5)

    def test_nonlinear_recurrence_keeps_required_float_stack(self):
        code = differentiated_c_code(NONLINEAR_RECURRENCE)

        conservative_stack_slots_before_analysis = 10
        self.assertEqual(float_stack_slots(code), conservative_stack_slots_before_analysis)

        _, lib = compile_quiet(NONLINEAR_RECURRENCE, "_code/rev_stack_nonlinear_recurrence")
        dx = ctypes.c_float(0.0)
        dn = ctypes.c_int(0)
        x = 0.7
        n = 4
        lib.rev_nonlinear_recurrence(x, ctypes.byref(dx), n, ctypes.byref(dn), 1.0)

        expected = 1.0
        z = x
        for _ in range(n):
            expected *= math.cos(z)
            z = math.sin(z)
        self.assertAlmostEqual(dx.value, expected, places=5)

    def test_linear_recurrence_with_later_nonlinear_use_keeps_stack(self):
        code = differentiated_c_code(LINEAR_THEN_NONLINEAR)

        conservative_stack_slots_before_analysis = 20
        required_stack_slots_after_analysis = 10
        self.assertEqual(float_stack_slots(code), required_stack_slots_after_analysis)
        self.assertLess(float_stack_slots(code), conservative_stack_slots_before_analysis)

        _, lib = compile_quiet(LINEAR_THEN_NONLINEAR, "_code/rev_stack_linear_then_nonlinear")
        dx = ctypes.c_float(0.0)
        dn = ctypes.c_int(0)
        x = 0.25
        n = 6
        lib.rev_linear_then_nonlinear(x, ctypes.byref(dx), n, ctypes.byref(dn), 1.0)
        self.assertAlmostEqual(dx.value, n * math.cos(n * x), places=5)

    def test_nested_linear_loop_accumulation_eliminates_float_stack(self):
        code = differentiated_c_code(NESTED_LINEAR_ACCUM)

        conservative_stack_slots_before_analysis = 100
        self.assertEqual(float_stack_slots(code), 0)
        self.assertLess(float_stack_slots(code), conservative_stack_slots_before_analysis)

        _, lib = compile_quiet(NESTED_LINEAR_ACCUM, "_code/rev_stack_nested_linear_accum")
        dx = ctypes.c_float(0.0)
        dn = ctypes.c_int(0)
        dm = ctypes.c_int(0)
        x = 1.25
        n = 3
        m = 4
        lib.rev_nested_linear_accum(
            x,
            ctypes.byref(dx),
            n,
            ctypes.byref(dn),
            m,
            ctypes.byref(dm),
            1.0,
        )
        self.assertAlmostEqual(dx.value, n * m, places=5)


if __name__ == "__main__":
    unittest.main()
