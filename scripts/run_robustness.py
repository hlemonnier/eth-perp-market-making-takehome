from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run robustness grid and write CSV outputs.")
    parser.add_argument("--mode", choices=["smoke", "standard"], default="smoke")
    parser.add_argument("--output-dir", default="reports/robustness")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "market_maker.cli",
            "robustness",
            "--output-dir",
            args.output_dir,
            "--suite-size",
            args.mode,
        ],
        check=True,
        env=env,
    )


if __name__ == "__main__":
    main()
