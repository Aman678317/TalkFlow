# Troubleshooting Guide (`docs/TROUBLESHOOTING.md`)

Common issues and solutions when using Desi CLI.

---

## 1. Authentication Issues (Exit Code 2)

**Error:** `Authentication failed: Invalid API key`

**Solutions:**
1. Check configured key:
   ```bash
   desi auth show
   ```
2. Store key securely:
   ```bash
   echo "YOUR_API_KEY" | desi auth set-key --from-stdin
   ```
3. Or set via environment variable:
   ```bash
   export DESI_API_KEY="your-api-key"
   ```

---

## 2. Quota & Rate Limits (Exit Codes 3 & 4)

- **Exit Code 3 (Rate limit exceeded):**
  The CLI automatically retries requests using exponential backoff with jitter. If persisting, reduce `--concurrency`.
- **Exit Code 4 (Quota exceeded):**
  Check consumption with `desi usage`.

---

## 3. Real-Time Voice Translation (Exit Code 9)

- Voice translation requires WebSocket connectivity to `wss://api.globaltalk.ai`.
- Verify your audio input matches standard PCM16 mono 16kHz or supported container formats (`.ogg`, `.mp3`, `.wav`).
- When streaming from stdin, always provide `--content-type`:
  ```bash
  cat stream.pcm | desi voice - --to hi --content-type 'audio/pcm;encoding=s16le;rate=16000'
  ```

---

## 4. Cache Clearing

If you need to force re-translation:
```bash
desi cache clear
```
Or pass `--no-cache` on individual commands.
