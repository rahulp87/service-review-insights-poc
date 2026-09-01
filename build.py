"""
build.py — one command to regenerate everything.

    python build.py

Runs the synthetic data generator, then the review-pack builder.
Equivalent to running src/generate_data.py and src/build_review_pack.py
in sequence.
"""

import runpy
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))

print("[1/2] generating synthetic weekly data ...")
runpy.run_path(str(SRC / "generate_data.py"), run_name="__main__")

print("\n[2/2] building the review pack ...")
runpy.run_path(str(SRC / "build_review_pack.py"), run_name="__main__")

print("\nDone. Open output/service_review_pack.html")
