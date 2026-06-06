# Slang GPU Reverse-Stack Benchmark

These timings compare the same source program under two reverse-stack policies:
`analysis` is the optimized dependency-aware policy, and `conservative` caches every non-output float write.
Runtime is reported as average Python-dispatch wall time per kernel launch, so use it as a local trend check rather than a hardware-independent number.

| Benchmark | Threads | n | Optimized float slots | Conservative float slots | Optimized ms | Conservative ms | Speedup |
|---|---:|---:|---:|---:|---:|---:|---:|
| simd_linear_accum | 65536 | 10 | 0 | 10 | 0.0615 | 0.0621 | 1.01x |
| simd_linear_then_sin | 65536 | 10 | 10 | 30 | 0.0973 | 0.1425 | 1.46x |