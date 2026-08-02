#!/usr/bin/env python3
"""Track the exporter version behind every fixture, against upstream and against us.

Fixtures go stale silently. A metric renamed between the captured version and the
one actually deployed makes a rule look dead when it works, or look fine when it
is dead -- both have happened in this repo. This script makes the drift visible
in one command.

It reads the version out of each fixture's provenance header (the first comment
block) and compares it two ways:

  fixture vs DEPLOYED   what we run. The comparison that decides whether a rule
                        works, and the only one that can fail this script.
  fixture vs upstream   informational. Upstream moving ahead costs nothing until
                        we follow it.

    python3 check_versions.py              # both comparisons
    python3 check_versions.py --offline    # skip the network, fixture vs deployed only
    python3 check_versions.py --markdown   # regenerate the table in EXPORTERS.md

Authentication: uses `gh api` when the GitHub CLI is available, which lifts the
unauthenticated rate limit of 60 requests/hour. Falls back to anonymous HTTP.

--markdown deliberately writes only the local two columns. A document asserting
"upstream is 1.9.0" is wrong the moment upstream cuts a release, which is the
class of staleness this whole script exists to catch. Upstream is something you
ask for at the moment you need it, not something you commit.
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

# fixture name -> what we actually run, and how that was established.
#
# Only versions observed directly belong here -- a *_build_info query, or a pin
# read out of the Ansible role. An entry absent from this map renders as "not
# recorded", which is the honest answer and reads as an invitation to go find
# out. Guessing here would defeat the point of the whole file.
#
# Several instances of the same exporter on different versions is the normal
# case, not an anomaly, so the value is free text rather than a version string.
DEPLOYED = {
    "postgres_exporter":   ("0.12.0 and 0.15.0", "counted across the fleet: 16 instances on 0.12.0, 21 on 0.15.0"),
    "keydb_exporter":      ("1.52.0 and 1.58.0", "redis_exporter_build_info: 210 instances on 1.52.0, 11 on 1.58.0"),
    "prometheus":          ("2.55.0 and 3.13.1", "prometheus_build_info: 2.55.0 on the main estate, 3.13.1 on dynfactory"),
    "node_exporter":       ("1.7.0, rolling to 1.12.1", "role pinned to 1.12.1; fleet rollout not yet run"),
    "cert-manager":        ("1.21.1", "confirmed with the cluster operators"),
    "haproxy_exporter_2x": ("2.7.11", "promex is built into HAProxy; version is HAProxy's own"),
    "haproxy_exporter_3x": ("3.2.21", "promex is built into HAProxy; version is HAProxy's own"),

    # Carried over from the README's per-exporter sections when they were split
    # out into EXPORTERS.md. These fixtures have no version in their header, so
    # this was the only record of them and would otherwise have been lost. None
    # has been re-verified against a running instance -- treat as a lead, not a
    # measurement, and promote it once you have checked.
    "aerospike":           ("1.9.0", "unverified: carried over from the README"),
    "ipsec_exporter":      ("0.4.0", "unverified: carried over from the README"),
    "phpfpm_exporter":     ("2.2.0", "unverified: carried over from the README"),
}

# Matches "1.2.3", "v1.2.3", "0.24.0" in a provenance header.
RE_VERSION = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?)\b")

MARK_BEGIN = "<!-- BEGIN GENERATED: python3 scripts/check_versions.py --markdown -->"
MARK_END = "<!-- END GENERATED -->"
EXPORTERS_MD = os.path.join(ROOT, "reference", "EXPORTERS.md")


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


def fixture_names():
    return sorted(f for f in os.listdir(EXPORTERS_DIR)
                  if os.path.isfile(os.path.join(EXPORTERS_DIR, f)))


def deployed_status(captured, name):
    """Compare a fixture's captured version against what we run.

    Returns (deployed_text, note, status). An exporter running on several
    versions at once is normal here, so the match is a substring test against
    free text rather than an equality check.
    """
    entry = DEPLOYED.get(name)
    if entry is None:
        return "—", "", "not recorded"
    text, note = entry
    if captured is None:
        return text, note, "fixture has no version"
    if norm(captured) in text:
        return text, note, "matches"
    return text, note, "MISMATCH"


def write_markdown():
    """Rewrite the generated table in EXPORTERS.md, between its markers.

    Local data only -- no network, so this is safe to run from a pre-commit
    hook. See the module docstring for why upstream is not written here.
    """
    rows = []
    for name in fixture_names():
        captured, why = fixture_version(os.path.join(EXPORTERS_DIR, name))
        text, note, status = deployed_status(captured, name)
        cap = captured or f"_{why}_"
        flag = " ⚠️" if status == "MISMATCH" else ""
        rows.append(f"| `{name}` | {cap} | {text}{flag} | {note or '—'} |")

    table = "\n".join([
        MARK_BEGIN,
        "",
        "<!-- Do not edit by hand: this table is rewritten from the fixture",
        "     provenance headers and the DEPLOYED map in check_versions.py. -->",
        "",
        "| Fixture | Captured from | Deployed here | How the deployed version is known |",
        "|---|---|---|---|",
        *rows,
        "",
        MARK_END,
    ])

    with open(EXPORTERS_MD) as f:
        doc = f.read()
    start, end = doc.find(MARK_BEGIN), doc.find(MARK_END)
    if start == -1 or end == -1:
        print(f"error: markers not found in {EXPORTERS_MD}", file=sys.stderr)
        return 1
    new = doc[:start] + table + doc[end + len(MARK_END):]
    if new == doc:
        print(f"{EXPORTERS_MD}: already up to date")
        return 0
    with open(EXPORTERS_MD, "w") as f:
        f.write(new)
    print(f"{EXPORTERS_MD}: table regenerated ({len(rows)} fixtures)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true",
                    help="skip the upstream lookup, just list what fixtures claim")
    ap.add_argument("--markdown", action="store_true",
                    help="regenerate the version table in EXPORTERS.md and exit")
    args = ap.parse_args()

    if args.markdown:
        return write_markdown()

    rows, behind, mismatched, unrecorded = [], 0, 0, 0
    for name in fixture_names():
        captured, why = fixture_version(os.path.join(EXPORTERS_DIR, name))
        deployed, _, dstatus = deployed_status(captured, name)
        if dstatus == "MISMATCH":
            mismatched += 1
        elif dstatus == "not recorded":
            unrecorded += 1

        repo = UPSTREAM.get(name, "?")
        if repo is None:
            up, ustatus = "—", "no upstream"
        elif repo == "?":
            up, ustatus = "?", "not in UPSTREAM map"
        elif args.offline:
            up, ustatus = "", ""
        else:
            newest, err = latest_release(repo)
            if err:
                up, ustatus = "?", err
            elif captured is None:
                up, ustatus = newest, "cannot compare"
            elif norm(captured) == norm(newest):
                up, ustatus = newest, "current"
            else:
                up, ustatus = newest, "behind"
                behind += 1

        rows.append((name, captured or f"({why})", deployed, dstatus, up, ustatus))

    def width(i, title):
        return max([len(r[i]) for r in rows] + [len(title)])

    w, c, d, ds, u = (width(0, "fixture"), width(1, "captured"),
                      width(2, "deployed"), width(3, "vs deployed"), width(4, "upstream"))
    print(f"{'fixture'.ljust(w)}  {'captured'.ljust(c)}  {'deployed'.ljust(d)}  "
          f"{'vs deployed'.ljust(ds)}  {'upstream'.ljust(u)}  vs upstream")
    print(f"{'-' * w}  {'-' * c}  {'-' * d}  {'-' * ds}  {'-' * u}  -----------")
    for name, cap, dep, dstat, up, ustat in rows:
        print(f"{name.ljust(w)}  {cap.ljust(c)}  {dep.ljust(d)}  "
              f"{dstat.ljust(ds)}  {up.ljust(u)}  {ustat}")

    print()
    if mismatched:
        print(f"{mismatched} fixture(s) captured from a version we do not run. "
              "This is the one that breaks rules.")
    else:
        print("Every fixture with a recorded deployment matches it.")
    print(f"{unrecorded} fixture(s) have no recorded deployed version — fill in DEPLOYED "
          "in this script once you have checked *_build_info.")
    if not args.offline:
        print(f"{behind} behind upstream, which costs nothing until you upgrade.")

    # Only the deployed mismatch is a failure. Upstream moving ahead is news,
    # not a defect: it was the reason this script cried wolf on 10 of 11
    # fixtures that in fact matched the fleet exactly.
    return 1 if mismatched else 0


if __name__ == "__main__":
    sys.exit(main())
