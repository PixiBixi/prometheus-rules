#!/usr/bin/env python3
"""Validate Prometheus rule files with promtool.

Our rule files start with '- name:' (a bare list) rather than the canonical
'groups:' wrapper. This script prepends 'groups:' to a temp file before
handing it to promtool, so validation works without modifying the source files.

Exits 0 if all files are valid (or promtool is not installed).
Exits 1 on the first invalid file.
"""

import os
import subprocess
import sys
import tempfile

RULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")
SKIP = {".yamllint.yml"}


def promtool_available():
    return subprocess.run(
        ["promtool", "--version"],
        capture_output=True,
    ).returncode == 0


def validate_file(path):
    with open(path) as f:
        content = f.read()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tmp:
        tmp.write("groups:\n")
        for line in content.splitlines():
            tmp.write("  " + line + "\n")
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["promtool", "check", "rules", tmp_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  FAIL: {os.path.basename(path)}")
            print(result.stdout)
            print(result.stderr)
            return False
        return True
    finally:
        os.unlink(tmp_path)


def main():
    if not promtool_available():
        print("Warning: promtool not found — skipping PromQL validation.")
        print("Install: brew install prometheus  or  https://github.com/prometheus/prometheus/releases")
        sys.exit(0)

    files = sorted(
        os.path.join(RULES_DIR, f)
        for f in os.listdir(RULES_DIR)
        if f.endswith(".yml") and f not in SKIP
    )

    print(f"Validating {len(files)} rule files with promtool…")
    failed = []
    for path in files:
        if not validate_file(path):
            failed.append(path)

    if failed:
        print(f"\n{len(failed)} file(s) failed validation:")
        for f in failed:
            print(f"  {f}")
        sys.exit(1)

    print(f"All {len(files)} rule files are valid.")


if __name__ == "__main__":
    main()
