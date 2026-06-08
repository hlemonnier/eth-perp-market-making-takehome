from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run robustness grid and write CSV outputs.")
    parser.add_argument("--mode", choices=["smoke", "core", "full_core", "full", "standard"], default="core")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--smoke-rows", type=int, default=1_000)
    parser.add_argument("--sample-rows", type=int, default=50_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    mode = "core" if args.mode == "standard" else args.mode
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = "reports/full/robustness_core" if mode == "full_core" else "reports/sample/robustness"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "market_maker.cli",
            "robustness",
            "--output-dir",
            output_dir,
            "--suite-size",
            mode,
            "--smoke-rows",
            str(args.smoke_rows),
            "--sample-rows",
            str(args.sample_rows),
        ],
        check=True,
        env=env,
    )


if __name__ == "__main__":
    main()
