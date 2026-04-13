#!/usr/bin/env python3
"""Build docs/data.json from exporters/ and rules/."""

import json
import os
import re
import yaml

ROOT      = os.path.dirname(os.path.abspath(__file__))
EXPORTERS_DIR = os.path.join(ROOT, "exporters")
RULES_DIR     = os.path.join(ROOT, "rules")
OUT           = os.path.join(ROOT, "docs", "data.json")

GITHUB_REPO = "https://github.com/PixiBixi/prometheus-rules"
BRANCH      = "main"

SKIP_EXPORTERS = set()
SKIP_RULES     = {".yamllint.yml"}

# Metric prefixes that belong to the exporter process itself (Go runtime,
# Prometheus client, HTTP handler) — not relevant as "uncovered business metrics"
# when the exporter is a proxy (separate process scraping another system).
EXPORTER_GENERIC_PREFIXES = (
    "go_",
    "process_",
    "promhttp_",
    "net_conntrack_",
)

# Exporters where the software IS the thing being monitored — their go_*/process_*
# metrics are legitimate business metrics (GC pressure, goroutine leaks, etc.)
# and must NOT be filtered out.
NATIVE_EXPORTERS = {
    "cert-manager",
    "promtail_exporter",
}

# PromQL keywords to ignore when extracting metric names
PROMQL_KEYWORDS = {
    "by", "without", "on", "ignoring", "group_left", "group_right",
    "sum", "avg", "count", "min", "max", "stddev", "stdvar", "topk", "bottomk",
    "count_values", "quantile", "rate", "irate", "increase", "delta", "idelta",
    "deriv", "predict_linear", "histogram_quantile", "label_replace", "label_join",
    "vector", "scalar", "time", "bool", "offset", "and", "or", "unless",
    "absent", "absent_over_time", "ceil", "floor", "round", "clamp", "clamp_max",
    "clamp_min", "changes", "resets", "avg_over_time", "min_over_time", "max_over_time",
    "sum_over_time", "count_over_time", "last_over_time", "present_over_time",
    "sort", "sort_desc", "inf", "nan",
}


# ── Exporters ────────────────────────────────────────────────────────────────

def parse_exporter(path, native=False):
    metrics = []
    current_help = None
    current_type = None
    seen = set()

    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("# HELP "):
                parts = line.split(" ", 3)
                current_help = parts[3] if len(parts) > 3 else ""
            elif line.startswith("# TYPE "):
                parts = line.split(" ", 3)
                current_type = parts[3] if len(parts) > 3 else ""
            elif line and not line.startswith("#"):
                m = re.match(r"^(\S+?)(\{[^}]*\})?\s+(.+)$", line)
                if not m:
                    continue
                name = m.group(1)
                if name in seen:
                    continue
                seen.add(name)
                labels = re.findall(r'(\w+)="[^"]*"', m.group(2) or "")
                metrics.append({
                    "name": name,
                    "type": current_type or "",
                    "help": current_help or "",
                    "labels": labels,
                    "example": line,
                    "generic": not native and name.startswith(EXPORTER_GENERIC_PREFIXES),
                })
                current_help = None
                current_type = None

    return metrics


def load_exporters():
    exporters = []
    for fname in sorted(os.listdir(EXPORTERS_DIR)):
        if fname in SKIP_EXPORTERS:
            continue
        fpath = os.path.join(EXPORTERS_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath) as f:
            first = f.read(50)
        if not re.match(r"^(# HELP|# TYPE|\w+[{ ])", first):
            continue
        metrics = parse_exporter(fpath, native=fname in NATIVE_EXPORTERS)
        if not metrics:
            continue
        exporters.append({
            "name": fname,
            "metrics": metrics,
            "github_url": f"{GITHUB_REPO}/blob/{BRANCH}/exporters/{fname}",
        })
        print(f"  {fname}: {len(metrics)} metrics")
    return exporters


# ── Rules ────────────────────────────────────────────────────────────────────

def extract_metric_names(expr):
    """Extract likely metric names from a PromQL expression."""
    expr = re.sub(r'\{[^}]*\}', '', str(expr))  # strip label matchers
    tokens = re.findall(r'[a-zA-Z_:][a-zA-Z0-9_:]*', expr)
    return {
        t for t in tokens
        if t not in PROMQL_KEYWORDS
        and '_' in t          # metric names almost always have underscores
        and not t.startswith('__')
    }


def load_rules():
    rule_groups = []
    for fname in sorted(os.listdir(RULES_DIR)):
        if fname in SKIP_RULES or not fname.endswith(".yml"):
            continue
        fpath = os.path.join(RULES_DIR, fname)
        with open(fpath) as f:
            raw = yaml.safe_load(f)
        if not raw or not isinstance(raw, list):
            continue

        for group in raw:
            name = group.get("name", fname)
            rules = []
            for rule in group.get("rules", []):
                expr = rule.get("expr", "")
                metric_refs = sorted(extract_metric_names(expr))
                if "alert" in rule:
                    rules.append({
                        "kind": "alert",
                        "alert": rule["alert"],
                        "expr": expr,
                        "for": rule.get("for", ""),
                        "severity": rule.get("labels", {}).get("severity", ""),
                        "summary": rule.get("annotations", {}).get("summary", ""),
                        "description": rule.get("annotations", {}).get("description", ""),
                        "runbook_url": rule.get("annotations", {}).get("runbook_url", ""),
                        "metric_refs": metric_refs,
                    })
                elif "record" in rule:
                    rules.append({
                        "kind": "record",
                        "record": rule["record"],
                        "expr": expr,
                        "metric_refs": metric_refs,
                    })

            if rules:
                rule_groups.append({
                    "file": fname,
                    "name": name,
                    "rules": rules,
                    "github_url": f"{GITHUB_REPO}/blob/{BRANCH}/rules/{fname}",
                })
                alerts  = sum(1 for r in rules if r["kind"] == "alert")
                records = sum(1 for r in rules if r["kind"] == "record")
                print(f"  {fname}: {alerts} alerts, {records} records")

    return rule_groups


# ── Cross-reference: exporter → related alerts ───────────────────────────────

def build_cross_refs(exporters, rule_groups):
    """For each exporter, find alerts that reference its metrics."""
    # Build a set of all metric names per exporter
    exporter_metrics = {
        e["name"]: {m["name"] for m in e["metrics"]}
        for e in exporters
    }

    # Build index: metric_name → list of (file, alert_name, severity)
    metric_to_alerts = {}
    for grp in rule_groups:
        for rule in grp["rules"]:
            if rule["kind"] != "alert":
                continue
            for ref in rule["metric_refs"]:
                metric_to_alerts.setdefault(ref, []).append({
                    "file": grp["file"],
                    "alert": rule["alert"],
                    "severity": rule["severity"],
                })

    # Attach related_alerts to each exporter
    for exp in exporters:
        seen_alerts = set()
        related = []
        for mname in exporter_metrics[exp["name"]]:
            for alert in metric_to_alerts.get(mname, []):
                key = (alert["file"], alert["alert"])
                if key not in seen_alerts:
                    seen_alerts.add(key)
                    related.append(alert)
        exp["related_alerts"] = sorted(related, key=lambda x: (x["file"], x["alert"]))

    return exporters, rule_groups


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Parsing exporters...")
    exporters = load_exporters()

    print("Parsing rules...")
    rule_groups = load_rules()

    print("Building cross-references...")
    exporters, rule_groups = build_cross_refs(exporters, rule_groups)

    data = {
        "meta": {
            "github_repo": GITHUB_REPO,
            "branch": BRANCH,
        },
        "exporters": exporters,
        "rules": rule_groups,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    size_kb = os.path.getsize(OUT) / 1024
    print(f"\nWrote {OUT} ({size_kb:.0f} KB)")
    print(f"  {len(exporters)} exporters, {sum(len(e['metrics']) for e in exporters)} metrics")
    total_alerts  = sum(len([r for r in g["rules"] if r["kind"]=="alert"])  for g in rule_groups)
    total_records = sum(len([r for r in g["rules"] if r["kind"]=="record"]) for g in rule_groups)
    print(f"  {len(rule_groups)} rule groups, {total_alerts} alerts, {total_records} records")
