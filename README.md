# loma

This is an educational compiler/programming language for differentiable programming, used for the course [CSE 291](https://cseweb.ucsd.edu/~tzli/cse291/) in UCSD.

See [this PDF](https://cseweb.ucsd.edu/~tzli/cse291/sp2026/homework0.pdf) for a quick introduction to the language and compiler.

## Project additions in this fork

This fork extends the original CSE 291P `loma_public` repository with completed AD functionality and a final-project optimization for reducing reverse-mode stack memory. The main final-project contribution is a dependency-aware reverse-primal liveness analysis that avoids caching overwritten primal values unless they are actually needed during the reverse pass.

### Modified implementation files

| File | Purpose |
|---|---|
| `forward_diff.py` | Implements forward-mode AD support used by the course infrastructure. This includes differentiation of expressions, assignments, returns, calls, arrays, structs, conditionals, and loops. |
| `reverse_diff.py` | Implements reverse-mode AD and the final-project stack optimization. The new analysis tracks reverse-primal liveness, skips unnecessary stack pushes/pops, handles affine constant-scaling cases, tracks symbolic memory locations for array/struct aliases, and supports a conservative baseline mode through `LOMA_REVERSE_STACK_POLICY=conservative`. |
| `codegen_slang.py` | Updates Slang code generation for reverse SIMD kernels. Local adjoint temporaries use normal `+=`, while true output adjoints still use atomic adds. This allows optimized reverse-mode SIMD kernels to compile and run on the Slang/Metal backend. |
| `.gitignore` | Adds local/generated-file ignore rules such as `.DS_Store`, `proposal.tex`, and `scratch.py`. |

### Added tests and evaluation files

| File | Purpose |
|---|---|
| `tests/test_reverse_stack_analysis.py` | Main regression suite for the final project. It checks stack-slot reduction, derivative correctness, alias behavior, branch behavior, affine/nonlinear recurrences, Slang code generation, Slang GPU correctness, and optional GPU benchmark timing. |
| `tests/result.md` | Generated CPU-side stack analysis report. It summarizes before/after float stack slots, integer stack slots, peak stack bytes, and correctness checks. |
| `tests/gpu_result.md` | Generated Slang GPU benchmark report comparing optimized dependency-aware stack allocation against the conservative baseline. |
| `tests/nested_peak_memory_vs_loop_iterations.png` | Plot showing peak stack memory growth for the nested linear loop benchmark under the conservative baseline versus dependency analysis. |

### Reverse-mode stack optimization

The original reverse-mode implementation conservatively cached overwritten primal values before assignment. For example, loop updates such as:

```python
z = z + x
```

would still save the old value of `z`, even though reverse mode does not need it for a linear update. Our optimization analyzes whether the old primal value is actually needed by the reverse pass.

The analysis removes unnecessary caching for linear and affine updates, while preserving stack storage for nonlinear expressions such as:

```python
z = sin(z)
```

where the old value of `z` is required to compute `cos(z)` during reverse execution.

### Alias analysis refinement

The final implementation tracks symbolic memory locations rather than only base variables. This lets the compiler distinguish constant array indices such as:

```python
a[0]
a[1]
```

so they do not falsely alias. Dynamic indices such as `a[i]` and `a[j]` remain conservative because they may refer to the same location at runtime.

### Slang GPU evaluation

The project also includes Slang SIMD tests and an optional GPU benchmark. The benchmark compares the optimized policy against the conservative stack policy on the same source programs.

Current generated results include:

| Benchmark | Optimized Slots | Conservative Slots | Optimized ms | Conservative ms | Speedup |
|---|---:|---:|---:|---:|---:|
| `simd_linear_accum` | 0 | 10 | 0.0615 | 0.0621 | 1.01x |
| `simd_linear_then_sin` | 10 | 30 | 0.0973 | 0.1425 | 1.46x |

These results show that the optimization consistently reduces local reverse-mode stack allocation. Runtime speedup depends on whether stack traffic is a bottleneck for the kernel.

### Running the tests

Run the reverse-stack regression suite:

```bash
python -m unittest tests/test_reverse_stack_analysis.py
```

Run the HW3 regression suite:

```bash
python hw_tests/hw3/test.py
```

Run the optional Slang GPU benchmark:

```bash
LOMA_RUN_GPU_BENCHMARKS=1 LOMA_GPU_BENCH_THREADS=65536 LOMA_GPU_BENCH_REPEATS=50 \
  python -m unittest tests.test_reverse_stack_analysis.ReverseStackSlangGpuTest.test_gpu_reverse_stack_policy_benchmark
```

The GPU benchmark writes:

```text
tests/gpu_result.md
```
