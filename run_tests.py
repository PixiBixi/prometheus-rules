#!/usr/bin/env python3
"""Run the promtool unit tests in tests/ against the rule files.

`promtool check rules` only validates syntax. It happily passes a rule whose
vector matching never matches, or whose selector names a metric no exporter
emits -- such a rule is simply silent forever, which looks exactly like
"nothing is wrong". These tests exercise the rules against synthetic series so
that silence is a failure, not a default.

Rule files are bare lists, so they are 'groups:'-wrapped into a temp directory
first. The test files are copied in alongside them, which lets each test
reference its rules by plain basename:

    rule_files: [basis.rules.yml]

promtool does not print which file a failing test came from, so give every
test a descriptive `name:` -- that is what identifies it in the output.

Exits 0 if all tests pass (or promtool is not installed), 1 otherwise.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from ruleslib import TESTS_DIR, rule_files, wrap_into


def main():
    if shutil.which("promtool") is None:
        print("Warning: promtool not found — skipping rule unit tests.")
        print("Install: brew install prometheus  or  https://github.com/prometheus/prometheus/releases")
        sys.exit(0)

    if not os.path.isdir(TESTS_DIR):
        print("No tests/ directory — nothing to run.")
        sys.exit(0)

    tests = sorted(
        os.path.join(TESTS_DIR, f)
        for f in os.listdir(TESTS_DIR)
        if f.endswith(".test.yml")
    )
    if not tests:
        print("No *.test.yml files in tests/ — nothing to run.")
        sys.exit(0)

    print(f"Running {len(tests)} rule test file(s) with promtool…")

    with tempfile.TemporaryDirectory() as tmpdir:
        for path in rule_files():
            wrap_into(path, tmpdir)

        staged = []
        for path in tests:
            dest = os.path.join(tmpdir, os.path.basename(path))
            shutil.copyfile(path, dest)
            staged.append(dest)

        result = subprocess.run(
            ["promtool", "test", "rules", *staged],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # promtool echoes the temp paths it was handed.
        output = result.stdout.replace(tmpdir + os.sep, "tests/")

    if result.returncode != 0:
        print(output)
        print("Rule unit tests failed.")
        sys.exit(1)

    print(f"All {len(tests)} rule test file(s) passed.")


if __name__ == "__main__":
    main()
