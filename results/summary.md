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
| Startup to first healthy response (ms) | 790 | 29 | 33 | 188 |
| CPU-seconds per 100k orders, flat out | 12.8 | 5.8 | 2.9 | 22.4 |
| CPU-seconds per 100k orders at 2,000 a second | 21.3 | 11.5 | 6.0 | 30.0 |
| Peak memory under load (MB) | 501 | 82 | 46 | 286 |
| Throughput, flat out (requests per second) | 77,509 | 133,939 | 120,247 | 4,448 |
| p99 latency, flat out (ms) | 3.2 | 1.1 | 0.6 | 53.2 |
| p99 latency at 2,000 a second (ms) | 0.9 | 0.5 | 0.4 | 35.0 |
| Compute cost per million orders, flat out (Fargate) | $0.0014 | $0.0006 | $0.0003 | $0.0025 |
| Requests until it beats Python, flat out | 1,248,531,841 | 76,100,851 | n/a | baseline |
| Requests until it beats Python at 2,000 a second | 1,367,528,495 | 68,007,722 | n/a | baseline |

Python's load numbers come from one uvicorn worker, the command its stack contract gives and the acceptance test ran (`bench/single_worker.py`). With one worker per core it split its in-memory store (`results/python-workers.json`) and used 53.2 CPU-seconds per 100k orders, 1,276 MB at peak, and 23,919 requests per second.
