#!/usr/bin/env python3
"""Shared helpers for validate_rules.py and run_tests.py.

Both scripts need to turn this repo's bare-list rule files into something
promtool accepts. Keeping that in one place means validation and unit tests
always see byte-identical wrapped rules.
"""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))
RULES_DIR = os.path.join(ROOT, "rules")
TESTS_DIR = os.path.join(ROOT, "tests")

SKIP = {".yamllint.yml"}


def rule_files():
    """Absolute paths of every rule file, sorted."""
    return sorted(
        os.path.join(RULES_DIR, f)
        for f in os.listdir(RULES_DIR)
        if f.endswith(".yml") and f not in SKIP
    )


def wrap_into(path, dest_dir):
    """Write a 'groups:'-wrapped copy of `path` into `dest_dir`, same basename.

    Our rule files start with '- name:' (a bare list) rather than the canonical
    'groups:' wrapper. Preserving the basename keeps promtool's output readable
    and lets test files reference their rules as plain filenames.
    """
    dest = os.path.join(dest_dir, os.path.basename(path))
    with open(path) as src, open(dest, "w") as dst:
        dst.write("groups:\n")
        for line in src:
            dst.write("  " + line.rstrip("\n") + "\n")
    return dest
