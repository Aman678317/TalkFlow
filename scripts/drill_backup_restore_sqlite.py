#!/usr/bin/env python3
"""Day-5 backup/restore drill for the SQLite lane (30-DAY-ROADMAP §Day 5).

Creates its OWN throwaway origin database inside an isolated temp directory
(never touches `data/globaltalk.db` or `./data`), migrates it to head,
seeds a minimal realistic tenant, takes a consistent backup with SQLite's
online backup API, deletes the origin (simulated loss), restores the backup
into a second isolated directory, and verifies integrity, logical equality
and alembic compatibility. Prints a JSON report with RTO/RPO observations
and exits non-zero on any failed stage.

Usage:
    python scripts/drill_backup_restore_sqlite.py [--root PATH] [--keep]

`--root` pins the temp root (defaults to a fresh `tempfile.mkdtemp`).
`--keep` keeps the drill directory for post-mortem inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone

REPO = pathlib.Path(__file__).resolve().parents[1]
API_DIR = REPO / "services" / "api"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_head(revision_output: str) -> str:
    """Extract the alembic revision id from `alembic current` output."""
    for line in revision_output.splitlines():
        if "(head)" in line:
            return line.strip()
    for line in revision_output.splitlines():
        if ("INFO" not in line and "Will assume" not in line and line.strip()):
            return line.strip()
    return "unknown"


def _sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_sql_dump(db_path: pathlib.Path) -> str:
    """Logical digest of a SQLite database (schema + rows, fully ordered)."""
    conn = sqlite3.connect(str(db_path))
    try:
        data = "\n".join(conn.iterdump())
    finally:
        conn.close()
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _alembic(db_url: str, *args: str, stage: str) -> str:
    cmd = [sys.executable, "-m", "alembic", "-c", str(API_DIR / "alembic.ini"), *args]
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = "services/api;apps/api;ai;." if os.name == "nt" else "services/api:apps/api:ai:."
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run = subprocess.run(cmd, cwd=str(API_DIR), env=env, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=300)
    if run.returncode != 0:
        raise RuntimeError(f"stage={stage} alembic {' '.join(args)} failed rc={run.returncode}\n"
                           f"stdout={run.stdout[-2000:]}\nstderr={run.stderr[-2000:]}")
    return (run.stdout or "") + (run.stderr or "")


SEED_SQL = """
INSERT INTO organizations (id, name, slug, plan, status, settings_json, retention_json, deleted_at, created_at, updated_at)
VALUES (:org_id, :org_name, :org_slug, 'free', 'active', '{}', '{}', NULL, :ts, :ts);
INSERT INTO users (id, email, password_hash, name, locale, speak_lang, hear_lang, status,
                   email_verified, is_platform_admin, mfa_enabled, mfa_secret, last_login_at, deleted_at,
                   created_at, updated_at)
VALUES (:user_id, :email, :password_hash, 'Day5 Drill User', 'en', 'en', 'en', 'active',
        0, 0, 0, NULL, NULL, NULL, :ts, :ts);
INSERT INTO organization_members (id, org_id, user_id, role, status, created_at, updated_at)
VALUES (:member_id, :org_id, :user_id, 'owner', 'active', :ts, :ts)
"""

TABLES_TO_COUNT = ("organizations", "users", "organization_members")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="temp root directory for the drill")
    parser.add_argument("--keep", action="store_true", help="keep the drill directory afterwards")
    args = parser.parse_args()

    report: dict = {"drill": "sqlite_backup_restore", "started_utc": _utcnow(), "stages": []}
    t_start = time.monotonic()

    root = pathlib.Path(args.root).resolve() if args.root else pathlib.Path(tempfile.mkdtemp(prefix="day5_drill_"))
    if args.root:
        root.mkdir(parents=True, exist_ok=True)
    report["drill_root"] = str(root)

    origin_dir = root / "origin"
    backup_dir = root / "backup"
    restore_dir = root / "restored"
    # The drill is deterministic: each run starts from an empty scene, even
    # over a kept directory from a previous (possibly failed) run.
    for d in (origin_dir, backup_dir, restore_dir):
        shutil.rmtree(d, ignore_errors=True)
        (d / "db").mkdir(parents=True, exist_ok=True)  # each lane gets its own nested dir
    origin_db = origin_dir / "db" / "drill_origin.db"
    backup_db = backup_dir / "db" / "drill_backup.db"
    restored_db = restore_dir / "db" / "drill_restored.db"

    org_id, user_id, member_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    seed_params = {
        "org_id": org_id, "org_name": "Day5 Drill Org", "org_slug": f"day5-drill-{uuid.uuid4().hex[:8]}",
        "user_id": user_id, "email": f"day5.drill.{uuid.uuid4().hex[:8]}@example.invalid",
        "password_hash": "day5-drill-not-a-real-hash", "member_id": member_id,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    origin_url = f"sqlite:///{origin_db.as_posix()}"
    restored_url = f"sqlite:///{restored_db.as_posix()}"

    try:
        # Stage 0: migrate origin to head (schema under test comes from the real migrations).
        t0 = time.monotonic()
        _alembic(origin_url, "upgrade", "head", stage="migrate_origin")
        head_out = _alembic(origin_url, "current", stage="alembic_current_origin")
        report["stages"].append({"stage": "migrate_origin", "ok": True, "seconds": round(time.monotonic() - t0, 3)})
        report["alembic_head"] = _parse_head(head_out)

        # Stage 1: seed a minimal realistic tenant through plain SQL.
        t0 = time.monotonic()
        conn = sqlite3.connect(str(origin_db))
        seeded_counts: dict[str, int] = {}
        try:
            for statement in filter(None, (s.strip() for s in SEED_SQL.split(";"))):
                conn.execute(statement, seed_params)
            conn.commit()
            for table in TABLES_TO_COUNT:
                (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                seeded_counts[table] = count
        finally:
            conn.close()
        report["stages"].append({"stage": "seed", "ok": True, "seconds": round(time.monotonic() - t0, 3),
                                 "seeded_counts": seeded_counts})

        # Stage 2: take a consistent backup via SQLite's online backup API.
        # RPO note: the snapshot is transactionally consistent as of this moment;
        # production equivalent is pg_dump / managed snapshot.
        t0 = time.monotonic()
        src = sqlite3.connect(str(origin_db))
        dst = sqlite3.connect(str(backup_db))
        src.backup(dst)
        dst.close()
        src.close()
        t_backup = round(time.monotonic() - t0, 3)
        origin_dump_digest = _sha256_sql_dump(origin_db)
        backup_sha = _sha256_file(backup_db)
        report["stages"].append({"stage": "backup", "ok": True, "seconds": t_backup,
                                 "backup_sha256": backup_sha, "origin_dump_digest": origin_dump_digest})

        # Stage 3: simulate origin loss (delete the origin DB file + WAL/SHM companions).
        t0 = time.monotonic()
        for companion in ("", "-wal", "-shm"):
            target = pathlib.Path(str(origin_db) + companion)
            if target.exists():
                target.unlink()
        origin_gone = not origin_db.exists()
        report["stages"].append({"stage": "simulate_origin_loss", "ok": origin_gone,
                                 "seconds": round(time.monotonic() - t0, 3)})

        # Stage 4: restore the backup into the isolated target directory.
        t0 = time.monotonic()
        shutil.copyfile(backup_db, restored_db)
        t_restore = round(time.monotonic() - t0, 3)
        restored_sha = _sha256_file(restored_db)
        report["stages"].append({"stage": "restore", "ok": True, "seconds": t_restore,
                                 "restored_sha256": restored_sha,
                                 "byte_identical_to_backup": restored_sha == backup_sha})

        # Stage 5: verify the restored database.
        t0 = time.monotonic()
        conn = sqlite3.connect(str(restored_db))
        try:
            (integrity,) = conn.execute("PRAGMA integrity_check").fetchone()
            fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
            row_counts = {}
            for table in TABLES_TO_COUNT:
                (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                row_counts[table] = count
        finally:
            conn.close()
        restored_dump_digest = _sha256_sql_dump(restored_db)
        current_out = _alembic(restored_url, "current", stage="alembic_current_restored")
        _alembic(restored_url, "check", stage="alembic_check_restored")  # raises on drift
        t_verify = round(time.monotonic() - t0, 3)
        head_after = _parse_head(current_out)
        logically_equal = (restored_dump_digest == origin_dump_digest
                           and row_counts == seeded_counts)
        report["stages"].append({"stage": "verify", "ok": True, "seconds": t_verify,
                                 "integrity_check": integrity, "foreign_key_violations": fk_violations,
                                 "row_counts": row_counts,
                                 "logical_dump_digest": restored_dump_digest,
                                 "logically_equal_to_origin": logically_equal,
                                 "alembic_head_restored": head_after,
                                 "alembic_check_drift": "clean"})

        report["rto_rpo"] = {
            "backup_seconds": t_backup,
            "restore_seconds": t_restore,
            "verify_seconds": t_verify,
            "restore_to_verified_seconds": round(t_restore + t_verify, 3),
            "total_drill_seconds": round(time.monotonic() - t_start, 3),
            "rpo_observation": "backup is a transactionally consistent snapshot; RPO equals the backup interval policy in production (see runbook)",
        }
        report["result"] = "PASS" if (origin_gone and integrity == "ok" and fk_violations == 0 and logically_equal) else "FAIL"
        report["finished_utc"] = _utcnow()
    except Exception as exc:  # noqa: BLE001 - the drill reports failures as data, never masks them
        report["result"] = "FAIL"
        report["error"] = str(exc)
        report["finished_utc"] = _utcnow()
        print(json.dumps(report, indent=2))
        return 1
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)

    print(json.dumps(report, indent=2))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
