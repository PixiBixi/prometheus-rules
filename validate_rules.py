#!/usr/bin/env python3
"""Validate Prometheus rule files with promtool.

Our rule files start with '- name:' (a bare list) rather than the canonical
'groups:' wrapper. This script writes 'groups:'-wrapped copies into a temp
directory — keeping each file's original basename so promtool's output stays
readable — then validates them all in a single promtool invocation.

Lint issues (e.g. duplicate rules) are always printed: promtool reports them on
stdout but exits 0, so they used to pass unnoticed. They are non-blocking by
default because promtool's duplicate-rules lint only compares record name and
static labels — recording rules deliberately split over disjoint selectors trip
it as false positives. Pass --strict to make them fail the run.

Exits 0 if all files are valid (or promtool is not installed).
Exits 1 if any file is invalid, or if lint issues were found under --strict.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from ruleslib import rule_files, wrap_into


def promtool_available():
    return shutil.which("promtool") is not None


def main():
    strict = "--strict" in sys.argv[1:]

    if not promtool_available():
        print("Warning: promtool not found — skipping PromQL validation.")
        print("Install: brew install prometheus  or  https://github.com/prometheus/prometheus/releases")
        sys.exit(0)

    files = rule_files()
    if not files:
        print("No rule files found.")
        sys.exit(0)

    print(f"Validating {len(files)} rule files with promtool…")

    with tempfile.TemporaryDirectory() as tmpdir:
        wrapped = [wrap_into(p, tmpdir) for p in files]
        cmd = ["promtool", "check", "rules"]
        if strict:
            cmd.append("--lint-fatal")
        result = subprocess.run(
            [*cmd, *wrapped],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # keep FAILED blocks next to their file
            text=True,
        )
        # promtool echoes the temp paths it was handed — point them back at the
        # real sources so the output is actionable.
        output = result.stdout.replace(tmpdir + os.sep, "rules/")

    lint_issues = "lint error" in output

    if result.returncode != 0:
        print(output)
        print("Validation failed.")
        sys.exit(1)

    if lint_issues:
        print(output)
        print("Rule syntax is valid, but promtool reported lint issues (see above).")
        print("Re-run with --strict to treat them as failures.")
        sys.exit(0)

    print(f"All {len(files)} rule files are valid.")


if __name__ == "__main__":
    main()
