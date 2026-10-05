"""Run repeatable local release checks; production checks need injected credentials."""

import subprocess
import shutil
import sys


def main() -> int:
    npm = shutil.which("npm") or "npm"
    commands = [
        [sys.executable, "-m", "compileall", "-q", "app.py", "web_app.py", "server"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-q"],
        [npm, "run", "build:css"],
        [npm, "test"],
        [npm, "--prefix", "frontend", "run", "build"],
        [npm, "--prefix", "frontend", "run", "lint"],
        [npm, "--prefix", "frontend", "test"],
        [sys.executable, "tools/smoke_cloud_run.py"],
    ]
    for command in commands:
        print("RUN", " ".join(command), flush=True)
        try:
            result = subprocess.run(command, check=False)
        except OSError as exc:
            print(f"FAIL cannot start {command[0]}: {exc}", flush=True)
            return 1
        if result.returncode:
            print("FAIL release checks", flush=True)
            return result.returncode
    print("PASS local release checks; run python -m server.production_check with production credentials", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
