"""Pack the entire GlobalTalk AI full-stack application into a clean ZIP archive.

Excludes node_modules, .git, virtual environments, build artifacts, and caches.
"""
import os
import sys
import time
import zipfile
from pathlib import Path

# Directories to ignore anywhere in the tree
EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".vite-temp",
    "dist",
    "build",
    ".gemini",
    ".idea",
    ".vscode",
}

# File extensions or specific filenames to ignore
EXCLUDE_EXTS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".DS_Store",
}

EXCLUDE_FILES = {
    "globaltalk-ai-fullstack.zip",
    "Thumbs.db",
}


def create_fullstack_zip():
    root_dir = Path(__file__).resolve().parent
    output_zip = root_dir / "globaltalk-ai-fullstack.zip"

    print("=" * 65)
    print("      GlobalTalk AI — Full-Stack Application Archiver")
    print("=" * 65)
    print(f"Source Directory : {root_dir}")
    print(f"Output Archive   : {output_zip.name}")
    print("-" * 65)

    start_time = time.time()
    file_count = 0
    total_uncompressed_bytes = 0

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for current_root, dirs, files in os.walk(root_dir):
            current_path = Path(current_root)

            # Filter out excluded directories in-place so os.walk does not recurse into them
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".git")]

            # Double check relative path components
            rel_root = current_path.relative_to(root_dir)
            if any(part in EXCLUDE_DIRS for part in rel_root.parts):
                continue

            for file in files:
                file_path = current_path / file
                rel_file = file_path.relative_to(root_dir)

                if file in EXCLUDE_FILES or file_path.suffix.lower() in EXCLUDE_EXTS:
                    continue

                try:
                    zf.write(file_path, arcname=str(rel_file))
                    file_count += 1
                    total_uncompressed_bytes += file_path.stat().st_size
                    if file_count % 50 == 0:
                        print(f"[*] Packaged {file_count} files...", end="\r", flush=True)
                except Exception as e:
                    print(f"\n[!] Warning: Could not include {rel_file}: {e}")

    elapsed = time.time() - start_time
    zip_size_mb = output_zip.stat().st_size / (1024 * 1024)
    uncompressed_mb = total_uncompressed_bytes / (1024 * 1024)

    print("\n" + "=" * 65)
    print("SUCCESS! Full-stack application packaged successfully.")
    print(f"Total files included : {file_count}")
    print(f"Uncompressed size    : {uncompressed_mb:.2f} MB")
    print(f"Archive size         : {zip_size_mb:.2f} MB")
    print(f"Archive location     : {output_zip}")
    print(f"Time taken           : {elapsed:.2f} seconds")
    print("=" * 65)


if __name__ == "__main__":
    create_fullstack_zip()
