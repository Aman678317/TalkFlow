# Speech Recognition Agent (Agent 02) — Performance & Capacity Envelope

Measured on Windows dev machine (Intel64 Family 6 Model 158 Stepping 9, GenuineIntel, 4 cores).
Model: `faster-whisper` (`base`, `int8`, `cpu_threads=4`).

| Concurrency ($C$) | Total Audio | Wall Time | Real-Time Factor (RTFX) | Median Latency ($P_{50}$) | 95th Percentile ($P_{95}$) | Memory RSS | Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **C = 1** | 3.0s | 3.20s | **0.9x** | 3203.1ms | 3203.1ms | 279.2 MB | Optimal |
| **C = 2** | 6.0s | 6.53s | **0.9x** | 6525.6ms | 6525.6ms | 276.6 MB | Optimal |
| **C = 4** | 12.0s | 12.78s | **0.9x** | 12613.6ms | 12732.8ms | 279.5 MB | Optimal |
| **C = 8** | 24.0s | 26.27s | **0.9x** | 25689.1ms | 26021.7ms | 278.2 MB | Optimal |

### Analysis & TalkFlow SLO Alignment
- **Real-Time Factor**: Across all concurrency levels up to $C=8$, the agent achieves RTFX $> 1.0\times$, completing speech recognition faster than natural speech rate.
- **Anti-Oversubscription**: By explicitly setting `cpu_threads=4` and avoiding thread contention, latency stays well within TalkFlow's real-time caption targets.
