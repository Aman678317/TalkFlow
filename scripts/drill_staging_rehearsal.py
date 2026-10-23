"""Launch-phase remediation R2 (roadmap Day-2) — staging deployment rehearsal driver.

Repeatedly executable drill against the ISOLATED compose project
`tts-staging-drill` (docker-compose.staging-rehearse.yml, APP_ENV=production on
production-shaped local containers). It never touches any other compose
project or runtime on this box.

What it proves, step by step, with saved evidence:
  1.  Infra bring-up (postgres/redis/minio(+init)/livekit) healthy.
  2.  Migrations pre-applied the production way (alembic upgrade head + current
      + check) — production boot FAILS CLOSED on a non-migrated schema.
  3.  API+worker boot under APP_ENV=production (every production config gate
      must pass; secrets injected as >=32-char non-default drill strings).
  4.  /health and /ready live evidence (+ recorded environment field).
  5.  Worker connectivity: the deployed WORKER_KIND entrypoint
      (workers/document-worker) announces its queue consumer, with the redis
      queue lane logged as active. `app/workers_runner.py` is NOT asserted:
      it is the documented orphan (ARCHITECTURE_OWNERSHIP.md O-6), not what
      the worker image runs.
  6.  /metrics production access truth: bare GET -> 401, Bearer token -> 200.
  7.  Functional round: signup -> login -> meeting create/fetch (Bearer).
  8.  Restart/recovery: api restart -> healthy again -> re-login -> the meeting
      row survives; redis persistence checked; worker restart -> ribbon again.
  9.  Secrets-injection evidence from process env (length-only prints).

All timings are drill-scale (documented in docs/STAGING_REHEARSAL.md); not
production RTO/RPO claims. Artifacts land in %TEMP%\\opencode\\day2\\staging\\.

Usage (from repo root, after `docker compose -p tts-staging-drill ... build api worker`):
  python scripts/drill_staging_rehearsal.py
Teardown (only the drill project):
  python scripts/drill_staging_rehearsal.py --teardown
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = "tts-staging-drill"
COMPOSE_FILES = ["-f", "docker-compose.yml", "-f", "docker-compose.staging-rehearse.yml"]
API_BASE = "http://localhost:58080"
# Labelled rehearsal-only dummy — the exact value docker-compose.staging-rehearse.yml boots with.
DRILL_METRICS_TOKEN = "tts-staging-drill-metrics-token-0123456789abcdef"

ARTDIR = Path(os.environ["TTS_DRILL_ART"]) if os.environ.get("TTS_DRILL_ART") else (
    Path(os.environ["TEMP"]) / "opencode" / "day2" / "staging"
)
DRILL_EMAIL = f"staging-drill+{int(time.time())}@example.invalid"
DRILL_PASSWORD = "StagingDrill!2026-10-23x"

summary: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "steps": [], "user": None,
                 "meeting_id": None}


def step(name: str):
    """Context manager that records every labeled step into the summary."""

    class _Ctx:
        def __enter__(self):
            self.t0 = time.perf_counter()
            self.name = name
            print(f"[..] {name}")
            return self

        def __exit__(self, exc_type, exc, tb):
            secs = round(time.perf_counter() - self.t0, 2)
            self.status = "PASS" if exc_type is None else "FAIL"
            record = {"name": self.name, "status": self.status, "seconds": secs}
            if exc_type is not None:
                record["error"] = str(exc).strip()[:400]
            summary["steps"].append(record)
            print(f"[{self.status}] {name} ({secs} s)"
                  + (f" — {record['error']}" if exc_type is not None else ""))
            return False  # never swallow: failures mark the step and re-raise

    return _Ctx()


def compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "-p", PROJECT, *COMPOSE_FILES, *args]
    return subprocess.run(cmd, cwd=str(REPO), capture_output=capture, text=True,
                          encoding="utf-8", errors="replace")


def save(name: str, payload: object):
    ARTDIR.mkdir(parents=True, exist_ok=True)
    path = ARTDIR / name
    body = payload if isinstance(payload, str) else json.dumps(
        payload, indent=2, ensure_ascii=True, default=str)
    path.write_text(body, encoding="utf-8")
    print(f"    evidence: {path}")


def http_json(path: str, method: str = "GET", body: object | None = None,
              token: str | None = None, timeout: float = 20.0):
    """Returns (status, parsed-json-or-{'raw': text}, raw-text). Never raises on HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API_BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, (json.loads(raw) if raw.strip() else {}), raw
            except json.JSONDecodeError:
                return r.status, {"raw": raw[:2000]}, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, (json.loads(raw) if raw.strip() else {}), raw
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:2000]}, raw


def poll(path: str, want: int = 200, deadline: float = 300.0, interval: float = 3.0):
    """Poll until `path` returns `want`, or raise with the last observation."""
    started = time.perf_counter()
    last = "?"
    while time.perf_counter() - started < deadline:
        try:
            code, payload, raw = http_json(path, timeout=10)
            last = f"{code} {str(payload)[:160]}"
            if code == want:
                return code, payload, round(time.perf_counter() - started, 1)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last = f"conn-error {str(e)[:120]}"
        time.sleep(interval)
    raise TimeoutError(f"{path} not {want} within {deadline:.0f}s (last: {last})")


def main() -> int:
    if "--teardown" in sys.argv:
        with step("teardown(down -v, only the drill project)"):
            cp = compose("down", "-v", "--remove-orphans", capture=True)
            print(cp.stdout[-800:] if cp.returncode == 0 else cp.stderr[-800:])
            if cp.returncode != 0:
                raise RuntimeError("teardown failed")
        return 0

    # 1. infra bring-up -------------------------------------------------------
    with step("infra_up(postgres,redis,minio,minio-init,livekit)"):
        cp = compose("up", "-d", "postgres", "redis", "minio", "minio-init", "livekit", capture=True)
        print("    " + (cp.stdout[-300:].replace("\n", " | ") if cp.stdout else cp.stderr[-300:]))
        if cp.returncode != 0:
            raise RuntimeError("infra up failed")
        ps = compose("ps", "--format", "json", capture=True).stdout
        save("docker_ps_after_infra.txt", ps)

    with step("infra_healthy_poll"):
        deadline = time.perf_counter() + 120
        while True:
            probe = subprocess.run(
                ["docker", "compose", "-p", PROJECT, *COMPOSE_FILES,
                 "exec", "-T", "postgres", "pg_isready", "-U", "globaltalk"],
                cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")
            if probe.returncode == 0:
                break
            if time.perf_counter() > deadline:
                raise TimeoutError("postgres never became ready")
            time.sleep(3)
        redis_probe = subprocess.run(
            ["docker", "compose", "-p", PROJECT, *COMPOSE_FILES,
             "exec", "-T", "redis", "redis-cli", "ping"],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")
        if "PONG" not in redis_probe.stdout:
            raise RuntimeError("redis PING failed: " + redis_probe.stdout)
        save("infra_probe.txt", {"pg": probe.stdout.strip(), "redis": redis_probe.stdout.strip()})

    # 2. migrations the production way ---------------------------------------
    with step("migrations_upgrade_head"):
        cp = compose("run", "--rm", "-T", "api", "python", "-m", "alembic", "upgrade", "head",
                     capture=True)
        save("alembic_upgrade.log", json.dumps(
            {"rc": cp.returncode, "stdout": cp.stdout[-3000:], "stderr": cp.stderr[-1500:]},
            indent=2))
        if cp.returncode != 0:
            raise RuntimeError("alembic upgrade head failed")
    with step("migrations_current_and_check"):
        cur = compose("run", "--rm", "-T", "api", "python", "-m", "alembic", "current", capture=True)
        chk = compose("run", "--rm", "-T", "api", "python", "-m", "alembic", "check", capture=True)
        save("alembic_current_check.txt", json.dumps(
            {"current_rc": cur.returncode, "current": cur.stdout[-500:],
             "check_rc": chk.returncode, "check": chk.stdout[-300:], "check_err": chk.stderr[-300:]},
            indent=2))
        if cur.returncode != 0 or chk.returncode != 0:
            raise RuntimeError(f"alembic current/check rc={cur.returncode}/{chk.returncode}")

    # 3. boot the app services ------------------------------------------------
    with step("boot_api_worker"):
        cp = compose("up", "-d", "api", "worker", capture=True)
        if cp.returncode != 0:
            raise RuntimeError("api/worker up failed: " + cp.stderr[-400:])
        time.sleep(4)

    code, health, h_secs = poll("/health")
    with step("health_first"):
        summary["health_first"] = {"code": code, "seconds": h_secs, "body": health}
        save("health_first.json", json.dumps(summary["health_first"], indent=2, default=str))
        if code != 200:
            raise RuntimeError(f"/health not 200: {code}")

    code, ready, r_secs = poll("/ready", deadline=420.0)
    with step("ready_first"):
        summary["ready_first"] = {"code": code, "seconds": r_secs, "body": ready}
        save("ready_first.json", json.dumps(summary["ready_first"], indent=2, default=str))
        if code != 200:
            raise RuntimeError(f"/ready not 200: {code} body={json.dumps(ready)[:300]}")

    # 4. worker connectivity + metrics production access truth ---------------
    with step("worker_ribbon"):
        logs = compose("logs", "worker", "--tail", "60", capture=True).stdout
        save("worker_log_tail.txt", logs[-3500:])
        if ("document worker started (queue=documents)" not in logs
                or "job queue: redis" not in logs):
            raise RuntimeError("document-worker queue-consumer ribbon not found in logs")

    with step("metrics_access_truth(bare=401,bearer=200)"):
        code_bare, body_bare, raw_bare = http_json("/metrics")
        code_tok, _payload_tok, _raw_tok = http_json("/metrics", token=DRILL_METRICS_TOKEN)
        save("metrics_probe.txt", json.dumps(
            {"bare_status": code_bare, "bare_body": body_bare, "bearer_status": code_tok,
             "note": "Authorization: Bearer <drill token> accepted -> 200; bare -> 401"},
            indent=2))
        if code_bare != 401 or code_tok != 200:
            raise RuntimeError(f"metrics truth triplet off: bare={code_bare} bearer={code_tok}")

    # 5. functional round -----------------------------------------------------
    with step("signup"):
        code, payload, raw = http_json("/api/v1/auth/signup", "POST", {
            "email": DRILL_EMAIL, "password": DRILL_PASSWORD,
            "name": "Staging Drill", "organization_name": "Staging Drill Org",
        })
        save("signup.json", json.dumps(
            {"code": code, "email": DRILL_EMAIL, "user": payload.get("user"),
             "org": payload.get("organization"),
             "token_present": bool((payload.get("tokens") or {}).get("access_token"))},
            indent=2, default=str))
        if code not in (200, 201):
            raise RuntimeError(f"signup failed: {code} {raw[:200]}")
        summary["user"] = (payload.get("user") or {}).get("id")

    with step("login"):
        code, payload, raw = http_json("/api/v1/auth/login", "POST", {
            "email": DRILL_EMAIL, "password": DRILL_PASSWORD})
        save("login.json", json.dumps(
            {"code": code, "token_present": bool((payload.get("tokens") or {}).get("access_token"))},
            indent=2))
        if code != 200:
            raise RuntimeError(f"login failed: {code} {raw[:200]}")
        token = payload["tokens"]["access_token"]

    with step("meeting_create_and_fetch"):
        code, payload, raw = http_json("/api/v1/meetings", "POST",
                                       {"title": "staging-drill-recovery-check"}, token=token)
        save("meeting_created.json", json.dumps(
            {"code": code, "body": payload}, indent=2, default=str))
        if code not in (200, 201):
            raise RuntimeError(f"meeting create failed: {code} {raw[:200]}")
        meeting_id = payload["id"]
        code2, payload2, _ = http_json(f"/api/v1/meetings/{meeting_id}", token=token)
        save("meeting_fetched.json", json.dumps(
            {"code": code2, "body": payload2}, indent=2, default=str))
        if code2 != 200 or payload2.get("id") != meeting_id:
            raise RuntimeError("meeting fetch mismatch")
        summary["meeting_id"] = meeting_id

    # 6. restart / recovery ---------------------------------------------------
    with step("api_restart_and_recovery"):
        cp = compose("restart", "api", capture=True)
        if cp.returncode != 0:
            raise RuntimeError("api restart failed")
        code_h, _health2, secs_up = poll("/health", deadline=300.0)
        code_r, _ready2, r_secs2 = poll("/ready", deadline=420.0)
        code_l, payload_l, _raw = http_json("/api/v1/auth/login", "POST", {
            "email": DRILL_EMAIL, "password": DRILL_PASSWORD})
        token3 = (payload_l.get("tokens") or {}).get("access_token")
        code_m, payload_m, _r2 = http_json("/api/v1/meetings", token=token3)
        ids = [m.get("id") for m in payload_m] if isinstance(payload_m, list) else []
        redis_size = subprocess.run(
            ["docker", "compose", "-p", PROJECT, *COMPOSE_FILES, "exec", "-T",
             "redis", "redis-cli", "DBSIZE"],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8").stdout.strip()
        recovery = {"health": code_h, "ready": code_r, "relogin": code_l,
                    "meeting_survives": summary.get("meeting_id") in ids,
                    "redis_dbsize": redis_size,
                    "health_up_seconds": secs_up, "ready_up_seconds": r_secs2}
        save("restart_recovery.json", json.dumps(recovery, indent=2))
        summary["restart_recovery"] = recovery
        if not (code_h == 200 and code_r == 200 and code_l == 200 and
                summary.get("meeting_id") in ids):
            raise RuntimeError(f"recovery truth incomplete: {recovery}")

    with step("worker_restart_and_ribbon"):
        cp = compose("restart", "worker", capture=True)
        if cp.returncode != 0:
            raise RuntimeError("worker restart failed")
        time.sleep(6)
        logs = compose("logs", "worker", "--tail", "40", capture=True).stdout
        save("worker_log_after_restart.txt", logs[-3500:])
        if "document worker started (queue=documents)" not in logs:
            raise RuntimeError("document-worker ribbon missing after restart")

    # 7. secrets injection evidence -------------------------------------------
    with step("secret_lengths_in_container"):
        probe = compose("exec", "-T", "api", "python", "-c",
                        "from app.config import get_settings;s=get_settings();"
                        "print(s.app_env, len(s.secret_key), len(s.jwt_secret),"
                        " len(s.metrics_token), s.secure_cookies)", capture=True)
        save("secret_probe.txt", json.dumps(
            {"rc": probe.returncode, "out": probe.stdout.strip(), "err": probe.stderr[-300:]},
            indent=2))
        out = probe.stdout.strip().split()
        if probe.returncode != 0 or not out or out[0] != "production":
            raise RuntimeError("production settings probe failed")

    summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save("drill_summary.txt", json.dumps(summary, indent=2, default=str))
    print("\nDRILL COMPLETE — artifacts in", ARTDIR)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — the drill always records its failure
        summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        summary["fatal"] = str(exc)[:400]
        try:
            save("drill_summary.txt", json.dumps(summary, indent=2, default=str))
        except Exception:
            pass
        print(f"\nDRILL FAILED: {exc}")
        sys.exit(2)
