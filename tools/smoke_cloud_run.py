"""Start the real web entry point with PORT and verify public routes locally."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]

env = dict(os.environ, PORT=str(port), MUASAMCONG_NO_BROWSER="1")
env.pop("SITE_URL", None)
process = subprocess.Popen(
    [sys.executable, "-u", "web_main.py"], cwd=ROOT, env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
try:
    deadline = time.monotonic() + 12
    while True:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early: {process.stderr.read().decode(errors='replace')}")
        try:
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                if response.status == 200:
                    break
        except (URLError, TimeoutError):
            if time.monotonic() >= deadline:
                raise RuntimeError("Server did not become healthy within 12 seconds")
            time.sleep(0.2)

    for path in ("/", "/loc-du-lieu-mua-sam-cong", "/robots.txt", "/sitemap.xml",
                 "/tailwind.css", "/vendor/lucide.min.js", "/admin.css",
                 "/admin-ui.js", "/api/health"):
        with urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            data = response.read()
            assert response.status == 200 and data, path
            print(f"200 {path}: {len(data)} bytes")
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
