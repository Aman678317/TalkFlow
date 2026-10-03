---
name: benchmark
description: "Performance benchmarking and latency profiling. Measures response times, database query efficiency, frontend bundle metrics, memory usage, and throughput bottlenecks."
---

# Benchmark & Performance Profiling Mode

Quantify system latency, throughput, and resource consumption under representative workloads.

## Metrics & Profiling Targets
1. **Frontend Bundle & Assets**: Bundle size analysis, chunks >500kB, tree-shaking efficiency, initial parse/eval time.
2. **API Endpoint Latency**: p50, p95, p99 response times for key endpoints (translate, speech, auth, documents).
3. **Database Performance**: Query execution plans, N+1 query patterns, indexing on foreign keys and filter columns, connection pool limits.
4. **WebSocket / Audio Streaming Latency**: Audio chunk round-trip time (RTT), transcription turn latency, TTS buffer jitter.
5. **Memory & Concurrency**: Memory stability under repeated requests, async loop non-blocking behavior, leak detection.
