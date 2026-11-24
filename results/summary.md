| Measure | Java | Go | Rust | Python |
|---|---|---|---|---|
| Passed (of runs) | 2 of 10 | 7 of 10 | 0 of 10 | 7 of 10 |
| Passed on the first try | 0 | 0 | 0 | 1 |
| Builds measured | 2 | 7 | 1 (1 hand-fixed) | 7 |
| Token cost of all runs (Opus 5.5 rates) | $3.59 | $4.18 | $5.55 | $3.19 |
| Output tokens per working service | 44,166 | 20,323 | n/a | 13,799 |
| Token cost per working service (Opus 5.5 rates) | $1.79 | $0.60 | n/a | $0.46 |
| Lines of code the model wrote | 539 | 532 | 332 | 271 |
| Runtime dependencies | 34 | 0 | 63 | 14 |
| Known vulnerabilities per build (median) | 84 | 0 | 0 | 0 |
| Startup to first healthy response (ms) | 790 | 29 | 33 | 332 |
| CPU-seconds per 100k orders | 12.8 | 5.8 | 2.9 | 53.2 |
| Peak memory under load (MB) | 501 | 82 | 46 | 1,276 |
| Throughput (requests per second) | 77,509 | 133,939 | 120,247 | 23,919 |
| p99 latency (ms) | 3.2 | 1.1 | 0.6 | 6.6 |
| Compute cost per million orders (Fargate) | $0.0014 | $0.0006 | $0.0003 | $0.0060 |
| Requests until it beats Python | 294,432,111 | 26,580,680 | n/a | baseline |
