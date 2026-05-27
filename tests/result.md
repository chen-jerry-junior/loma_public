# Reverse-Mode Stack Analysis Results

These numbers are generated from the differentiated C emitted by `tests/test_reverse_stack_analysis.py`.
`Before` is the old conservative policy: cache every overwritten float value in a loop.
`After` is the current dependency-aware reverse-mode stack allocation.
Peak bytes include both float primal stacks and unchanged integer loop-index stacks.

## Summary at max_iter = 10

| Benchmark | Before float slots | After float slots | Int slots | Float reduction | Before peak bytes | After peak bytes | Byte reduction | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| linear_accumulation | 10 | 0 | 10 | 100.0% | 80 | 40 | 50.0% | Old z values are not needed by reverse AD. |
| nonlinear_recurrence | 10 | 10 | 10 | 0.0% | 80 | 80 | 0.0% | sin(z) needs the old z value. |
| linear_then_sin | 20 | 10 | 10 | 50.0% | 120 | 80 | 33.3% | z = z + x is linear, but the later sin(z) needs z. |
| nested_linear_accumulation | 100 | 0 | 120 | 100.0% | 880 | 480 | 45.5% | Nested linear recurrence; old z values scale with max_iter squared before analysis. |

## Stack Growth vs Static Loop Bound

| Benchmark | max_iter | Before float slots | After float slots | Int slots | Before peak bytes | After peak bytes |
|---|---:|---:|---:|---:|---:|---:|
| linear_accumulation | 1 | 1 | 0 | 1 | 8 | 4 |
| linear_accumulation | 2 | 2 | 0 | 2 | 16 | 8 |
| linear_accumulation | 3 | 3 | 0 | 3 | 24 | 12 |
| linear_accumulation | 4 | 4 | 0 | 4 | 32 | 16 |
| linear_accumulation | 5 | 5 | 0 | 5 | 40 | 20 |
| linear_accumulation | 6 | 6 | 0 | 6 | 48 | 24 |
| linear_accumulation | 7 | 7 | 0 | 7 | 56 | 28 |
| linear_accumulation | 8 | 8 | 0 | 8 | 64 | 32 |
| linear_accumulation | 9 | 9 | 0 | 9 | 72 | 36 |
| linear_accumulation | 10 | 10 | 0 | 10 | 80 | 40 |
| nonlinear_recurrence | 1 | 1 | 1 | 1 | 8 | 8 |
| nonlinear_recurrence | 2 | 2 | 2 | 2 | 16 | 16 |
| nonlinear_recurrence | 3 | 3 | 3 | 3 | 24 | 24 |
| nonlinear_recurrence | 4 | 4 | 4 | 4 | 32 | 32 |
| nonlinear_recurrence | 5 | 5 | 5 | 5 | 40 | 40 |
| nonlinear_recurrence | 6 | 6 | 6 | 6 | 48 | 48 |
| nonlinear_recurrence | 7 | 7 | 7 | 7 | 56 | 56 |
| nonlinear_recurrence | 8 | 8 | 8 | 8 | 64 | 64 |
| nonlinear_recurrence | 9 | 9 | 9 | 9 | 72 | 72 |
| nonlinear_recurrence | 10 | 10 | 10 | 10 | 80 | 80 |
| linear_then_sin | 1 | 2 | 1 | 1 | 12 | 8 |
| linear_then_sin | 2 | 4 | 2 | 2 | 24 | 16 |
| linear_then_sin | 3 | 6 | 3 | 3 | 36 | 24 |
| linear_then_sin | 4 | 8 | 4 | 4 | 48 | 32 |
| linear_then_sin | 5 | 10 | 5 | 5 | 60 | 40 |
| linear_then_sin | 6 | 12 | 6 | 6 | 72 | 48 |
| linear_then_sin | 7 | 14 | 7 | 7 | 84 | 56 |
| linear_then_sin | 8 | 16 | 8 | 8 | 96 | 64 |
| linear_then_sin | 9 | 18 | 9 | 9 | 108 | 72 |
| linear_then_sin | 10 | 20 | 10 | 10 | 120 | 80 |
| nested_linear_accumulation | 1 | 1 | 0 | 3 | 16 | 12 |
| nested_linear_accumulation | 2 | 4 | 0 | 8 | 48 | 32 |
| nested_linear_accumulation | 3 | 9 | 0 | 15 | 96 | 60 |
| nested_linear_accumulation | 4 | 16 | 0 | 24 | 160 | 96 |
| nested_linear_accumulation | 5 | 25 | 0 | 35 | 240 | 140 |
| nested_linear_accumulation | 6 | 36 | 0 | 48 | 336 | 192 |
| nested_linear_accumulation | 7 | 49 | 0 | 63 | 448 | 252 |
| nested_linear_accumulation | 8 | 64 | 0 | 80 | 576 | 320 |
| nested_linear_accumulation | 9 | 81 | 0 | 99 | 720 | 396 |
| nested_linear_accumulation | 10 | 100 | 0 | 120 | 880 | 480 |

## Correctness Checks

| Benchmark | Checked derivative |
|---|---|
| linear_accumulation | `d/dx sum_i x*x = 2*x*n` |
| nonlinear_recurrence | product of `cos(z_i)` terms |
| linear_then_sin | `d/dx sin(n*x) = n*cos(n*x)` |
| nested_linear_accumulation | `d/dx sum_i sum_j x = n*m` |
