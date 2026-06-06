import contextlib
import ctypes
import io
import math
import os
import re
import sys
import time
from dataclasses import dataclass
import unittest

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

import autodiff
import check
import codegen_c
import codegen_slang
import compiler
import parser
import slang_utils
import slangpy
import numpy as np


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


CONSTANT_SCALE_RECURRENCE = """
def constant_scale_recurrence(x : In[float], n : In[int]) -> float:
    i : int = 0
    z : float = x
    while (i < n, max_iter := 10):
        z = 2.0 * z + x
        i = i + 1
    return z

rev_constant_scale_recurrence = rev_diff(constant_scale_recurrence)
"""


NONCONSTANT_SCALE_RECURRENCE = """
def nonconstant_scale_recurrence(x : In[float], n : In[int]) -> float:
    i : int = 0
    z : float = 1.0
    while (i < n, max_iter := 10):
        z = x * z + 1.0
        i = i + 1
    return z

rev_nonconstant_scale_recurrence = rev_diff(nonconstant_scale_recurrence)
"""


OVERWRITE_AFTER_NONLINEAR_USE = """
def overwrite_after_nonlinear_use(x : In[float]) -> float:
    z : float = x
    y : float = sin(z)
    z = z + 1.0
    return y

rev_overwrite_after_nonlinear_use = rev_diff(overwrite_after_nonlinear_use)
"""


ARRAY_INDEXED_ACCUM = """
def array_indexed_accum(x : In[Array[float]], n : In[int]) -> float:
    i : int = 0
    s : float = 0.0
    while (i < n, max_iter := 10):
        s = s + x[i] * x[i]
        i = i + 1
    return s

rev_array_indexed_accum = rev_diff(array_indexed_accum)
"""


ARRAY_CONSTANT_INDEX_SEPARATION = """
def array_constant_index_separation(x : In[float]) -> float:
    a : Array[float, 2]
    a[0] = x
    a[1] = x + 1.0
    y : float = sin(a[0])
    a[1] = a[1] + 2.0
    return y

rev_array_constant_index_separation = rev_diff(array_constant_index_separation)
"""


ARRAY_SAME_CONSTANT_INDEX_ALIAS = """
def array_same_constant_index_alias(x : In[float]) -> float:
    a : Array[float, 2]
    a[0] = x
    y : float = sin(a[0])
    a[0] = a[0] + 2.0
    return y

rev_array_same_constant_index_alias = rev_diff(array_same_constant_index_alias)
"""


ARRAY_DYNAMIC_INDEX_MAY_ALIAS = """
def array_dynamic_index_may_alias(x : In[float], i : In[int], j : In[int]) -> float:
    a : Array[float, 2]
    a[i] = x
    y : float = sin(a[j])
    a[i] = a[i] + 2.0
    return y

rev_array_dynamic_index_may_alias = rev_diff(array_dynamic_index_may_alias)
"""


BRANCH_LINEAR_OR_NONLINEAR = """
def branch_linear_or_nonlinear(x : In[float], flag : In[int]) -> float:
    z : float = x
    if flag > 0:
        z = z + 1.0
    else:
        z = z * z
    return z

rev_branch_linear_or_nonlinear = rev_diff(branch_linear_or_nonlinear)
"""


SIMD_LINEAR_ACCUM = """
@simd
def simd_linear_accum(x : In[Array[float]], n : In[int], y : Out[Array[float]]):
    tid : int = thread_id()
    i : int = 0
    z : float = 0.0
    while (i < n, max_iter := 10):
        z = z + x[tid]
        i = i + 1
    y[tid] = z

rev_simd_linear_accum = rev_diff(simd_linear_accum)
"""


SIMD_LINEAR_THEN_SIN = """
@simd
def simd_linear_then_sin(x : In[Array[float]], n : In[int], y : Out[Array[float]]):
    tid : int = thread_id()
    i : int = 0
    z : float = 0.0
    out : float = 0.0
    while (i < n, max_iter := 10):
        z = z + x[tid]
        out = sin(z)
        i = i + 1
    y[tid] = out

rev_simd_linear_then_sin = rev_diff(simd_linear_then_sin)
"""


def differentiated_c_code(source):
    with contextlib.redirect_stdout(io.StringIO()):
        structs, funcs = parser.parse(source)
        structs, diff_structs, funcs = autodiff.resolve_diff_types(structs, funcs)
        check.check_ir(structs, diff_structs, funcs, check_diff=False)
        funcs = autodiff.differentiate(structs, diff_structs, funcs)
        check.check_ir(structs, diff_structs, funcs, check_diff=True)
        return codegen_c.codegen_c(structs, funcs)


STACK_POLICY_ENV = "LOMA_REVERSE_STACK_POLICY"


@contextlib.contextmanager
def reverse_stack_policy(policy):
    old_policy = os.environ.get(STACK_POLICY_ENV)
    os.environ[STACK_POLICY_ENV] = policy
    try:
        yield
    finally:
        if old_policy is None:
            os.environ.pop(STACK_POLICY_ENV, None)
        else:
            os.environ[STACK_POLICY_ENV] = old_policy


def differentiated_slang_code(source, policy="analysis"):
    with reverse_stack_policy(policy), contextlib.redirect_stdout(io.StringIO()):
        structs, funcs = parser.parse(source)
        structs, diff_structs, funcs = autodiff.resolve_diff_types(structs, funcs)
        check.check_ir(structs, diff_structs, funcs, check_diff=False)
        funcs = autodiff.differentiate(structs, diff_structs, funcs)
        check.check_ir(structs, diff_structs, funcs, check_diff=True)
        return codegen_slang.codegen_slang(structs, funcs, use_cas_atomic=False)


def float_stack_slots(c_code):
    return sum(int(size) for size in re.findall(r"float _t_float_[A-Za-z0-9]+\[(\d+)\];", c_code))


def slang_float_stack_slots(slang_code):
    return sum(int(size) for size in re.findall(r"\bfloat _t_float_[A-Za-z0-9]+\[(\d+)\];", slang_code))


def stack_slots_by_type(c_code):
    # Reverse-mode primal stacks are emitted as fixed-size C arrays. Counting
    # those declarations gives a stable compiler metric for the report.
    slots_by_type = {"float": 0, "int": 0}
    for c_type, size in re.findall(r"\b(float|int) _t_(?:float|int)_[A-Za-z0-9]+\[(\d+)\];", c_code):
        slots_by_type[c_type] += int(size)
    return slots_by_type


def total_stack_bytes(float_slots, int_slots):
    return float_slots * 4 + int_slots * 4


def compile_quiet(source, output_filename):
    with contextlib.redirect_stdout(io.StringIO()):
        return compiler.compile(source, target="c", output_filename=output_filename)


def compile_slang_quiet(source, policy="analysis"):
    try:
        slang_device = slang_utils.create_slang_device()
    except RuntimeError as exc:
        raise unittest.SkipTest(f"Slang/Metal device unavailable: {exc}") from exc
    with reverse_stack_policy(policy), contextlib.redirect_stdout(io.StringIO()):
        module, kernels = compiler.compile(
            source,
            target="slang",
            slang_device=slang_device,
        )
    return slang_device, module, kernels


def write_gpu_result_report(rows, output_path="gpu_result.md"):
    lines = [
        "# Slang GPU Reverse-Stack Benchmark",
        "",
        "These timings compare the same source program under two reverse-stack policies:",
        "`analysis` is the optimized dependency-aware policy, and `conservative` caches every non-output float write.",
        "Runtime is reported as average Python-dispatch wall time per kernel launch, so use it as a local trend check rather than a hardware-independent number.",
        "",
        "| Benchmark | Threads | n | Optimized float slots | Conservative float slots | Optimized ms | Conservative ms | Speedup |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        speedup = row["conservative_ms"] / row["optimized_ms"] if row["optimized_ms"] > 0 else 0.0
        lines.append(
            "| {benchmark} | {threads} | {n} | {optimized_slots} | {conservative_slots} | "
            "{optimized_ms:.4f} | {conservative_ms:.4f} | {speedup:.2f}x |".format(
                **row,
                speedup=speedup,
            )
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


@dataclass(frozen=True)
class StackBenchmark:
    name: str
    source: str
    conservative_float_slots_per_iter: int
    notes: str
    # loop_depth controls the expected conservative growth: one loop is O(N),
    # two equally bounded nested loops are O(N^2), and so on.
    loop_depth: int = 1
    has_loop_bound: bool = True


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
    StackBenchmark(
        "constant_scale_recurrence",
        CONSTANT_SCALE_RECURRENCE,
        conservative_float_slots_per_iter=1,
        notes="Constant scaling is affine, so old z values are not needed.",
    ),
    StackBenchmark(
        "nonconstant_scale_recurrence",
        NONCONSTANT_SCALE_RECURRENCE,
        conservative_float_slots_per_iter=1,
        notes="x receives an adjoint, so z = x*z + 1 needs old z values.",
    ),
    StackBenchmark(
        "array_indexed_accumulation",
        ARRAY_INDEXED_ACCUM,
        conservative_float_slots_per_iter=1,
        notes="Float primal values are unnecessary; integer indices are still restored.",
    ),
    StackBenchmark(
        "array_constant_index_separation",
        ARRAY_CONSTANT_INDEX_SEPARATION,
        conservative_float_slots_per_iter=1,
        notes="Disjoint constant indices avoid the old base-array false alias.",
        loop_depth=0,
        has_loop_bound=False,
    ),
    StackBenchmark(
        "branch_linear_or_nonlinear",
        BRANCH_LINEAR_OR_NONLINEAR,
        conservative_float_slots_per_iter=2,
        notes="The linear branch is stack-free, but the nonlinear branch keeps one restore.",
        loop_depth=0,
        has_loop_bound=False,
    ),
]


def source_with_max_iter(source, max_iter):
    # The stack arrays are sized from max_iter, so the report varies the static
    # loop bound rather than the runtime n/m values.
    return re.sub(r"max_iter\s*:=\s*\d+", f"max_iter := {max_iter}", source)


def stack_report_rows(max_iters):
    rows = []
    max_iter_values = list(max_iters)
    for bench in STACK_BENCHMARKS:
        for max_iter in max_iter_values:
            if not bench.has_loop_bound and max_iter != max_iter_values[-1]:
                continue
            code = differentiated_c_code(source_with_max_iter(bench.source, max_iter))
            after_slots = stack_slots_by_type(code)
            # "Before" models the old conservative policy: every overwritten
            # float inside the loop body is pushed once per possible iteration.
            if bench.has_loop_bound:
                before_float_slots = bench.conservative_float_slots_per_iter * (max_iter ** bench.loop_depth)
                bound_label = str(max_iter)
            else:
                before_float_slots = bench.conservative_float_slots_per_iter
                bound_label = "n/a"
            before_bytes = total_stack_bytes(before_float_slots, after_slots["int"])
            after_bytes = total_stack_bytes(after_slots["float"], after_slots["int"])
            rows.append({
                "benchmark": bench.name,
                "max_iter": max_iter,
                "bound_label": bound_label,
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
    # Keep the report generation attached to the regression test so the numbers
    # stay in sync with the compiler implementation.
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
            "| {benchmark} | {bound_label} | {before_float_slots} | {after_float_slots} | "
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
        "| constant_scale_recurrence | affine recurrence derivative `d' = 2*d + 1` |",
        "| nonconstant_scale_recurrence | recurrence derivative `d' = z + x*d` |",
        "| array_indexed_accumulation | `d/dx[i] sum_i x[i]*x[i] = 2*x[i]` |",
        "| branch_linear_or_nonlinear | `1` on the linear branch, `2*x` on the nonlinear branch |",
        "",
        "## Optional Slang GPU Benchmark",
        "",
        "Run `LOMA_RUN_GPU_BENCHMARKS=1 python -m unittest tests/test_reverse_stack_analysis.py` to time the optimized Slang reverse kernels against the conservative stack policy.",
        "The benchmark writes `gpu_result.md` and is skipped by default because GPU timing depends on local hardware and driver state.",
        "",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


class ReverseStackAliasCodegenTest(unittest.TestCase):
    def test_constant_array_indices_are_disambiguated(self):
        code = differentiated_c_code(ARRAY_CONSTANT_INDEX_SEPARATION)

        self.assertEqual(float_stack_slots(code), 0)

    def test_same_constant_array_index_still_aliases(self):
        code = differentiated_c_code(ARRAY_SAME_CONSTANT_INDEX_ALIAS)

        self.assertEqual(float_stack_slots(code), 1)

    def test_dynamic_array_indices_remain_conservative(self):
        code = differentiated_c_code(ARRAY_DYNAMIC_INDEX_MAY_ALIAS)

        self.assertEqual(float_stack_slots(code), 2)

    def test_slang_linear_accumulation_omits_local_float_stack(self):
        optimized_code = differentiated_slang_code(SIMD_LINEAR_ACCUM)
        conservative_code = differentiated_slang_code(SIMD_LINEAR_ACCUM, policy="conservative")

        self.assertEqual(slang_float_stack_slots(optimized_code), 0)
        self.assertGreater(slang_float_stack_slots(conservative_code), 0)

    def test_slang_linear_then_sin_keeps_required_local_float_stack(self):
        optimized_code = differentiated_slang_code(SIMD_LINEAR_THEN_SIN)
        conservative_code = differentiated_slang_code(SIMD_LINEAR_THEN_SIN, policy="conservative")

        self.assertEqual(slang_float_stack_slots(optimized_code), 10)
        self.assertEqual(slang_float_stack_slots(conservative_code), 30)


class ReverseStackSlangGpuTest(unittest.TestCase):
    def setUp(self):
        os.chdir(os.path.dirname(os.path.realpath(__file__)))

    def prepare_reverse_kernel(self, source, kernel_name, x_values, dy_values, n, policy="analysis"):
        slang_device, _, kernels = compile_slang_quiet(source, policy=policy)
        x_values = np.array(x_values, dtype=np.float32)
        dy_values = np.array(dy_values, dtype=np.float32)
        dx_values = np.zeros_like(x_values)

        buffer_x = slangpy.Tensor.from_numpy(device=slang_device, ndarray=x_values)
        buffer_dx = slangpy.Tensor.from_numpy(device=slang_device, ndarray=dx_values)
        buffer_dy = slangpy.Tensor.from_numpy(device=slang_device, ndarray=dy_values)
        buffer_dn = slangpy.Tensor.from_numpy(
            device=slang_device,
            ndarray=np.zeros([1], dtype=np.int32),
        )

        layout = kernels[kernel_name].program.layout
        func = layout.find_function_by_name(kernel_name)
        dispatch_args = {
            "thread_count": [len(x_values), 1, 1],
            func.parameters[1].name: len(x_values),
            func.parameters[2].name: buffer_x.storage,
            func.parameters[3].name: buffer_dx.storage,
            func.parameters[4].name: n,
            func.parameters[5].name: buffer_dn.storage,
            func.parameters[6].name: buffer_dy.storage,
        }
        return kernels[kernel_name], dispatch_args, buffer_dx

    def dispatch_reverse_kernel(self, source, kernel_name, x_values, dy_values, n, policy="analysis"):
        kernel, dispatch_args, buffer_dx = self.prepare_reverse_kernel(
            source,
            kernel_name,
            x_values,
            dy_values,
            n,
            policy=policy,
        )
        kernel.dispatch(**dispatch_args)
        return buffer_dx.to_numpy()

    def time_reverse_kernel(self, source, kernel_name, x_values, dy_values, n, policy, repeats):
        kernel, dispatch_args, buffer_dx = self.prepare_reverse_kernel(
            source,
            kernel_name,
            x_values,
            dy_values,
            n,
            policy=policy,
        )
        for _ in range(3):
            kernel.dispatch(**dispatch_args)
        start = time.perf_counter()
        for _ in range(repeats):
            kernel.dispatch(**dispatch_args)
        buffer_dx.to_numpy()
        return (time.perf_counter() - start) * 1000.0 / repeats

    def test_gpu_linear_accumulation_eliminates_local_float_stack(self):
        dx = self.dispatch_reverse_kernel(
            SIMD_LINEAR_ACCUM,
            "rev_simd_linear_accum",
            x_values=[0.25, 0.5, 0.75, 1.0],
            dy_values=[1.0, 0.5, 2.0, 1.5],
            n=6,
        )
        np.testing.assert_allclose(dx, np.array([6.0, 3.0, 12.0, 9.0], dtype=np.float32), rtol=1e-5)

    def test_gpu_linear_then_sin_keeps_required_local_stack(self):
        x = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        dy = np.array([1.0, 0.5, 2.0, 1.5], dtype=np.float32)
        n = 6
        dx = self.dispatch_reverse_kernel(
            SIMD_LINEAR_THEN_SIN,
            "rev_simd_linear_then_sin",
            x_values=x,
            dy_values=dy,
            n=n,
        )
        expected = dy * n * np.cos(n * x)
        np.testing.assert_allclose(dx, expected, rtol=1e-5, atol=1e-5)

    @unittest.skipUnless(
        os.environ.get("LOMA_RUN_GPU_BENCHMARKS") == "1",
        "set LOMA_RUN_GPU_BENCHMARKS=1 to run local Slang timing benchmarks",
    )
    def test_gpu_reverse_stack_policy_benchmark(self):
        threads = int(os.environ.get("LOMA_GPU_BENCH_THREADS", "4096"))
        repeats = int(os.environ.get("LOMA_GPU_BENCH_REPEATS", "30"))
        x_values = np.linspace(0.05, 0.95, threads, dtype=np.float32)
        dy_values = np.ones(threads, dtype=np.float32)
        benchmarks = [
            ("simd_linear_accum", SIMD_LINEAR_ACCUM, "rev_simd_linear_accum", 10),
            ("simd_linear_then_sin", SIMD_LINEAR_THEN_SIN, "rev_simd_linear_then_sin", 10),
        ]
        rows = []

        for name, source, kernel_name, n in benchmarks:
            optimized_code = differentiated_slang_code(source)
            conservative_code = differentiated_slang_code(source, policy="conservative")
            optimized_slots = slang_float_stack_slots(optimized_code)
            conservative_slots = slang_float_stack_slots(conservative_code)
            self.assertLess(optimized_slots, conservative_slots)

            optimized_ms = self.time_reverse_kernel(
                source,
                kernel_name,
                x_values,
                dy_values,
                n,
                policy="analysis",
                repeats=repeats,
            )
            conservative_ms = self.time_reverse_kernel(
                source,
                kernel_name,
                x_values,
                dy_values,
                n,
                policy="conservative",
                repeats=repeats,
            )
            self.assertGreater(optimized_ms, 0.0)
            self.assertGreater(conservative_ms, 0.0)
            rows.append({
                "benchmark": name,
                "threads": threads,
                "n": n,
                "optimized_slots": optimized_slots,
                "conservative_slots": conservative_slots,
                "optimized_ms": optimized_ms,
                "conservative_ms": conservative_ms,
            })

        write_gpu_result_report(rows)


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

    def test_constant_scale_recurrence_eliminates_float_stack(self):
        code = differentiated_c_code(CONSTANT_SCALE_RECURRENCE)

        conservative_stack_slots_before_analysis = 10
        self.assertEqual(float_stack_slots(code), 0)
        self.assertLess(float_stack_slots(code), conservative_stack_slots_before_analysis)

        _, lib = compile_quiet(CONSTANT_SCALE_RECURRENCE, "_code/rev_stack_constant_scale")
        dx = ctypes.c_float(0.0)
        dn = ctypes.c_int(0)
        x = 0.6
        n = 5
        lib.rev_constant_scale_recurrence(x, ctypes.byref(dx), n, ctypes.byref(dn), 1.0)

        expected = 1.0
        for _ in range(n):
            expected = 2.0 * expected + 1.0
        self.assertAlmostEqual(dx.value, expected, places=5)

    def test_nonconstant_scale_recurrence_keeps_required_float_stack(self):
        code = differentiated_c_code(NONCONSTANT_SCALE_RECURRENCE)

        conservative_stack_slots_before_analysis = 10
        self.assertEqual(float_stack_slots(code), conservative_stack_slots_before_analysis)

        _, lib = compile_quiet(NONCONSTANT_SCALE_RECURRENCE, "_code/rev_stack_nonconstant_scale")
        dx = ctypes.c_float(0.0)
        dn = ctypes.c_int(0)
        x = 0.6
        n = 5
        lib.rev_nonconstant_scale_recurrence(x, ctypes.byref(dx), n, ctypes.byref(dn), 1.0)

        z = 1.0
        expected = 0.0
        for _ in range(n):
            expected = z + x * expected
            z = x * z + 1.0
        self.assertAlmostEqual(dx.value, expected, places=5)

    def test_overwrite_after_nonlinear_use_keeps_one_restore(self):
        code = differentiated_c_code(OVERWRITE_AFTER_NONLINEAR_USE)

        self.assertEqual(float_stack_slots(code), 1)

        _, lib = compile_quiet(OVERWRITE_AFTER_NONLINEAR_USE, "_code/rev_stack_overwrite_after_use")
        dx = ctypes.c_float(0.0)
        x = 0.7
        lib.rev_overwrite_after_nonlinear_use(x, ctypes.byref(dx), 1.0)
        self.assertAlmostEqual(dx.value, math.cos(x), places=5)

    def test_array_indexed_accumulation_restores_indices_not_floats(self):
        code = differentiated_c_code(ARRAY_INDEXED_ACCUM)
        slots = stack_slots_by_type(code)

        self.assertEqual(slots["float"], 0)
        self.assertEqual(slots["int"], 10)

        _, lib = compile_quiet(ARRAY_INDEXED_ACCUM, "_code/rev_stack_array_indexed_accum")
        x_values = [1.0, 2.0, 3.0, 4.0]
        x = (ctypes.c_float * len(x_values))(*x_values)
        dx = (ctypes.c_float * len(x_values))(*([0.0] * len(x_values)))
        dn = ctypes.c_int(0)
        n = 3
        lib.rev_array_indexed_accum(x, dx, n, ctypes.byref(dn), 1.0)

        expected = [2.0, 4.0, 6.0, 0.0]
        for actual, expected_value in zip(dx, expected):
            self.assertAlmostEqual(actual, expected_value, places=5)

    def test_constant_array_indices_do_not_alias_for_stack_liveness(self):
        code = differentiated_c_code(ARRAY_CONSTANT_INDEX_SEPARATION)

        self.assertEqual(float_stack_slots(code), 0)

        _, lib = compile_quiet(
            ARRAY_CONSTANT_INDEX_SEPARATION,
            "_code/rev_stack_array_constant_index_separation",
        )
        dx = ctypes.c_float(0.0)
        x = 0.7
        lib.rev_array_constant_index_separation(x, ctypes.byref(dx), 1.0)
        self.assertAlmostEqual(dx.value, math.cos(x), places=5)

    def test_if_else_branch_keeps_only_nonlinear_restore(self):
        code = differentiated_c_code(BRANCH_LINEAR_OR_NONLINEAR)

        self.assertEqual(float_stack_slots(code), 1)

        _, lib = compile_quiet(BRANCH_LINEAR_OR_NONLINEAR, "_code/rev_stack_branch_linear_or_nonlinear")

        dx = ctypes.c_float(0.0)
        dflag = ctypes.c_int(0)
        x = 0.75
        lib.rev_branch_linear_or_nonlinear(x, ctypes.byref(dx), 1, ctypes.byref(dflag), 1.0)
        self.assertAlmostEqual(dx.value, 1.0, places=5)

        dx = ctypes.c_float(0.0)
        dflag = ctypes.c_int(0)
        lib.rev_branch_linear_or_nonlinear(x, ctypes.byref(dx), 0, ctypes.byref(dflag), 1.0)
        self.assertAlmostEqual(dx.value, 2.0 * x, places=5)


if __name__ == "__main__":
    unittest.main()
