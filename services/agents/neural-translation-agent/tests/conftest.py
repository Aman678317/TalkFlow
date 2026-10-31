"""Pytest configuration ensuring neural-translation-agent root is on sys.path."""
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["APP_ENV"] = "test"

