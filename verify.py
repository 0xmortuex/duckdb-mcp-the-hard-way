"""Run every module's main.py for real, the way CI does.

Each main.py checks its own claims with assert and exits 0 only if they all hold, so a
chapter whose code drifts away from what its README says fails here. Modules 04, 06 and 07
launch a real MCP server over stdio; module 07 also builds two 1,000,000-row files.

Usage: python verify.py            # all modules
       python verify.py 03 06      # just these
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def run_module(module: str) -> tuple[bool, str, float]:
    script = os.path.join(ROOT, module, "main.py")
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, script], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300, cwd=os.path.join(ROOT, module),
        )
    except subprocess.TimeoutExpired:
        return False, "timed out after 300s", time.monotonic() - start
    ok = proc.returncode == 0 and proc.stdout.rstrip().endswith("OK")
    return ok, proc.stdout + proc.stderr, time.monotonic() - start


def main() -> int:
    wanted = sys.argv[1:]
    modules = sorted(
        d for d in os.listdir(ROOT)
        if os.path.isfile(os.path.join(ROOT, d, "main.py"))
        and (not wanted or any(d.startswith(w) for w in wanted))
    )
    if not modules:
        print("no modules matched")
        return 1
    failed = []
    for m in modules:
        ok, output, secs = run_module(m)
        print(f"{'PASS' if ok else 'FAIL'}  {m}  ({secs:.1f}s)")
        if not ok:
            failed.append(m)
            print("    " + output.strip().replace("\n", "\n    "))
    print(f"\n{len(modules) - len(failed)}/{len(modules)} modules verified")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
