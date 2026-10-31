# Speech Recognition Model Selection & Hardware Profiles

## 1. Model Profiles

| Model | Parameters | Disk Cache | RAM/VRAM | Inference Speed (CPU) | Recommended Use Case |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **`tiny`** | 39 M | ~75 MB | ~150 MB | **~150 ms** | Ultra-low latency, low-resource CPUs, fast testing |
| **`base`** *(Default)* | 74 M | ~145 MB | ~250 MB | **~280–350 ms** | **Balanced production CPU profile** (English + Indian languages) |
| **`small`** | 244 M | ~465 MB | ~550 MB | **~750–950 ms** | High accuracy multilingual on modern 8+ core CPUs |
| **`medium`** | 769 M | ~1.5 GB | ~2.0 GB | **~2000 ms (CPU) / ~180 ms (GPU)** | GPU recommended for rich multilingual meetings |

## 2. Multi-Threading & Anti-Oversubscription (`GT_STT_CPU_THREADS`)
In `docs/LOAD_CAPACITY_ENVELOPE.md`, TalkFlow documented that CTranslate2 default settings could fall back to a single thread when `OMP_NUM_THREADS=1`.
Agent 02 explicitly passes `cpu_threads=4` directly to `WhisperModel`:
```python
model = WhisperModel(
    model_size="base",
    device="cpu",
    compute_type="int8",
    cpu_threads=4,  # Prevents single-thread bottleneck
)
```
This guarantees consistent sub-400 ms latency on standard 4-thread CPUs.

