#!/usr/bin/env python3
"""Compare the exporter version each fixture was captured from against upstream.

Fixtures go stale silently. A metric renamed between the captured version and the
one actually deployed makes a rule look dead when it works, or look fine when it
is dead -- both have happened in this repo. This script makes the drift visible
in one command.

It reads the version out of each fixture's provenance header (the first comment
block), then asks GitHub for the latest release of the matching project.

    python3 check_versions.py              # compare against upstream
    python3 check_versions.py --offline    # just list what the fixtures claim

Authentication: uses `gh api` when the GitHub CLI is available, which lifts the
unauthenticated rate limit of 60 requests/hour. Falls back to anonymous HTTP.

What it cannot tell you is which version you actually run. Fixture and upstream
are both easy to read; production is the third number that matters, and only a
query against your own Prometheus answers it -- look for `*_build_info`.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from ruleslib import ROOT

EXPORTERS_DIR = os.path.join(ROOT, "exporters")

# fixture name -> GitHub repo that releases it.
# None means there is no upstream release to compare against.
UPSTREAM = {
    "aerospike":            "aerospike/aerospike-prometheus-exporter",
    "apache_exporter":      "Lusitaniae/apache_exporter",
    "blackbox_exporter":    "prometheus/blackbox_exporter",
    "cert-manager":         "cert-manager/cert-manager",
    # promex ships inside HAProxy itself, and HAProxy does not publish GitHub
    # releases -- upstream lives at git.haproxy.org. Compare by hand.
    "haproxy_exporter_2x":  None,
    "haproxy_exporter_3x":  None,
    "ipsec_exporter":       "dennisstritzke/ipsec_exporter",
    "kafka_exporter":       "prometheus/jmx_exporter",
    "keepalived_exporter":  "cafebazaar/keepalived-exporter",
    "keydb_exporter":       "oliver006/redis_exporter",
    "memcached_exporter":   "prometheus/memcached_exporter",
    "mongodb_exporter":     "percona/mongodb_exporter",
    "mysqld_exporter":      "prometheus/mysqld_exporter",
    "node_exporter":        "prometheus/node_exporter",
    "nvme_exporter":        None,
    "phpfpm_exporter":      "hipages/php-fpm_exporter",
    "ping_exporter":        "czerwonk/ping_exporter",
    "postgres_exporter":    "prometheus-community/postgres_exporter",
    "prometheus":           "prometheus/prometheus",
    # promtail is versioned with Loki, so this compares against Loki releases.
    # Note promtail is deprecated upstream in favour of Grafana Alloy.
    "promtail_exporter":    "grafana/loki",
    "rabbitmq_exporter":    "rabbitmq/rabbitmq-server",
    "rds_enhanced":         None,
    "stackdriver_exporter": "prometheus-community/stackdriver_exporter",
    "varnish_exporter":     "jonnenauha/prometheus_varnish_exporter",
    "zookeeper_exporter":   "prometheus/jmx_exporter",
}

# Matches "1.2.3", "v1.2.3", "0.24.0" in a provenance header.
RE_VERSION = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?)\b")


def fixture_version(path):
    """Read the declared version out of a fixture's leading comment block."""
    header = []
    with open(path) as f:
        for line in f:
            if not line.startswith("#"):
                break
            if line.startswith(("# HELP", "# TYPE")):
                break
            header.append(line)
    if not header:
        return None, "no header"
    text = "".join(header)
    if re.search(r"\bversion (unknown|n/a)\b", text):
        return None, "not recorded"
    # The first version-looking token in the first line is the captured one;
    # later lines mention production or upstream versions in prose.
    m = RE_VERSION.search(header[0])
    return (m.group(1), None) if m else (None, "no version")


def norm(v):
    return v.lstrip("vV") if v else v


def latest_release(repo):
    """Latest release tag for a GitHub repo, or (None, reason)."""
    if shutil.which("gh"):
        r = subprocess.run(
            ["gh", "api", f"repos/{repo}/releases/latest", "--jq", ".tag_name"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip(), None
        return None, (r.stderr.strip().splitlines() or ["gh call failed"])[-1][:60]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "check_versions"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp).get("tag_name"), None
    except urllib.error.HTTPError as e:
        hint = " (rate limited — install gh to authenticate)" if e.code == 403 else ""
        return None, f"HTTP {e.code}{hint}"
    except Exception as e:  # noqa: BLE001 - network shape varies, report and move on
        return None, str(e)[:60]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true",
                    help="skip the upstream lookup, just list what fixtures claim")
    args = ap.parse_args()

    names = sorted(f for f in os.listdir(EXPORTERS_DIR)
                   if os.path.isfile(os.path.join(EXPORTERS_DIR, f)))

    rows, stale, unknown = [], 0, 0
    for name in names:
        captured, why = fixture_version(os.path.join(EXPORTERS_DIR, name))
        repo = UPSTREAM.get(name, "?")

        if repo is None:
            rows.append((name, captured or "—", "—", "no upstream"))
            continue
        if repo == "?":
            rows.append((name, captured or "—", "?", "not in UPSTREAM map"))
            continue
        if args.offline:
            rows.append((name, captured or f"({why})", "", ""))
            continue

        newest, err = latest_release(repo)
        if err:
            rows.append((name, captured or f"({why})", "?", err))
        elif captured is None:
            unknown += 1
            rows.append((name, f"({why})", newest, "cannot compare"))
        elif norm(captured) == norm(newest):
            rows.append((name, captured, newest, "up to date"))
        else:
            stale += 1
            rows.append((name, captured, newest, "BEHIND"))

    w = max([len(r[0]) for r in rows] + [len("fixture")])
    c = max([len(r[1]) for r in rows] + [len("captured")])
    u = max([len(r[2]) for r in rows] + [len("upstream")])
    print(f"{'fixture'.ljust(w)}  {'captured'.ljust(c)}  {'upstream'.ljust(u)}  status")
    print(f"{'-' * w}  {'-' * c}  {'-' * u}  ------")
    for name, cap, up, status in rows:
        print(f"{name.ljust(w)}  {cap.ljust(c)}  {up.ljust(u)}  {status}")

    if not args.offline:
        print()
        print(f"{stale} behind upstream, {unknown} with no recorded version.")
        print("Neither number tells you what production runs — check *_build_info there.")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
