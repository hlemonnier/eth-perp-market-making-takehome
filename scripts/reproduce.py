from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the project reproduction workflow.")
    parser.add_argument("--mode", choices=["smoke", "core", "full_core", "full", "standard"], default="smoke")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--smoke-rows", type=int, default=1_000)
    parser.add_argument("--sample-rows", type=int, default=5_000)
    parser.add_argument("--clean-output", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def run(cmd: list[str], env: dict[str, str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    mode = "core" if args.mode == "standard" else args.mode
    if args.output_dir is not None:
        output_dir = args.output_dir
    elif mode == "smoke":
        output_dir = "reports/sample/smoke"
    elif mode == "core":
        output_dir = "reports/sample/reproduce"
    else:
        output_dir = "reports/full/reproduce"
    output_path = root / output_dir
    if args.clean_output and output_path.exists():
        shutil.rmtree(output_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    run([sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"], env)
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q"], env)
    run(
        [
            sys.executable,
            "-m",
            "market_maker.cli",
            "reproduce",
            "--output-dir",
            output_dir,
            "--suite-size",
            mode,
            "--smoke-rows",
            str(args.smoke_rows),
            "--sample-rows",
            str(args.sample_rows),
        ],
        env,
    )


if __name__ == "__main__":
    main()
