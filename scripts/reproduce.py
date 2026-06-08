from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the project reproduction workflow.")
    parser.add_argument("--mode", choices=["smoke", "core", "full", "standard"], default="smoke")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--skip-tests", action="store_true")
    return parser.parse_args()


def run(cmd: list[str], env: dict[str, str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    mode = "core" if args.mode == "standard" else args.mode
    output_dir = args.output_dir or ("reports/reproduce_smoke" if mode == "smoke" else "reports/reproduce")
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
        ],
        env,
    )


if __name__ == "__main__":
    main()
