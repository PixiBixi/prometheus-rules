# prometheus-rules
A bunch of Prometheus rules using some exporters

  * In the `exporters` folder, you have sample outputs of each exporter (one example per metric)
  * In the `rules` folder, you have the matching rules

| | |
|---|---|
| **[EXPORTERS.md](reference/EXPORTERS.md)** | every exporter: versions, required configuration, per-exporter traps |
| **[AUDIT.md](reference/AUDIT.md)** | how closely the fixtures and rules match the estate they were written against |
| **[docs/](docs/)** | browsable metric and alert reference, built from this repo |

### Exporter sample files

The files in `exporters/` are cleaned Prometheus text format samples. They can be used to understand available metrics and develop/test rules.

**Deduplication rules:**
- One example per unique metric+label combination
- Histogram buckets: all `le=…` values are preserved
- Enum/dimension labels (`mode`, `state`, `operation`, `pool`, `gc`, …): all values preserved
- High-cardinality instance labels: collapsed to one representative value

> **Note:** Fixture files are trimmed for readability — high-cardinality families (e.g. one series per partition, per process, per request type) are reduced to a few representative samples. The metric *names* are complete, but the number of label combinations is intentionally limited. The uncovered metrics view in the docs may therefore undercount coverage for these families.

**Native vs proxy exporters:**

Some exporters are *proxy exporters* (a separate Go process scraping another system — e.g. `node_exporter`, `mysqld_exporter`). Their `go_*`, `process_*`, and `promhttp_*` metrics describe the exporter process itself and are excluded from the uncovered metrics view.

Other exporters are *native exporters* (the software exposes its own metrics — e.g. `cert-manager`, `promtail`). Their `go_*` metrics reflect the actual application runtime (GC pressure, goroutine count…) and are kept visible. Native exporters are listed in `NATIVE_EXPORTERS` in `build.py`.

You'll see not so much warning severity rules. Why would you tell me? Because from my own experience, warning rules are ignored most of the time, so why bother create this kind of rule? :)

## Specifications

### Rules

These rules are a curated mix from multiple sources, reviewed and adapted for production use:

- **[Awesome Prometheus Alerts](https://samber.github.io/awesome-prometheus-alerts/)** (samber) — community-maintained alert collection
- **[Monitoring Mixins](https://monitoring.mixins.dev/)** — vendor/project-maintained mixin rules (cert-manager, etcd, CoreDNS, Loki…)
- **Official exporters** — alerts and recording rules extracted from exporter documentation or default configs
- **Custom rules** — written from scratch based on operational experience, not available in any of the above

All rules have been reviewed, deduplicated, and adjusted (thresholds, labels, expressions) to avoid common pitfalls from blindly copy-pasting community rules.

> **Running Kubernetes?** [kube-prometheus](https://github.com/prometheus-operator/kube-prometheus/tree/main/manifests) ships a comprehensive set of production-grade rules out of the box — look for the `*-prometheusRule.yaml` manifests. It covers etcd, kube-state-metrics, node-exporter, Prometheus itself, Alertmanager, and more. The rules in this repo are complementary and focus on the application layer (databases, proxies, message queues…).

  * Most of rules have a `job{} == 0` rule to be sure the exporter is working fine. Please don't forget to change this to match with your job name
    * This kind of rule doesn't work with `remote_write`

These rules have been tested with specific exporters version/ some custom parameters

### Validating and testing rules

```bash
# Syntax + lint (promtool check rules), all files in one invocation
python3 scripts/validate_rules.py

# Same, but treat lint issues such as duplicate rules as failures
python3 scripts/validate_rules.py --strict

# Behavioural unit tests (promtool test rules) from tests/
python3 scripts/run_tests.py
```

Both run automatically via pre-commit. They cover different failure modes, and
the second is the one that matters most here:

`promtool check rules` only validates syntax. It passes a rule whose vector
matching never matches, or whose selector names a metric no exporter emits —
such a rule is silent forever, which is indistinguishable from "nothing is
wrong". Several alerts in this repo were dead that way for a long time: a
`name=` matcher containing regex metacharacters, a `sum by (instance)` divided
by a vector still carrying `server`, a heap alert querying
`jvm_memory_used_bytes` when the exporter emits `jvm_memory_bytes_used`.

`tests/*.test.yml` feeds synthetic series through the rules and asserts what
does and does not fire, so silence becomes a test failure. When you fix or add
a rule, add a case — ideally one that fires and one that must stay quiet.

Rule files are bare lists, so both scripts wrap them under a `groups:` key in a
temp directory first (shared logic in `scripts/ruleslib.py`). Tests reference their
rules by plain basename: `rule_files: [basis.rules.yml]`. promtool does not
report which file a failing test came from, so give every test a descriptive
`name:`.

### Keeping fixtures honest

Every fixture opens with a provenance header recording the exporter and software version
it was captured from. `check_versions.py` reads those headers and compares them against
what we deploy and against upstream:

```bash
python3 scripts/check_versions.py             # both comparisons
python3 scripts/check_versions.py --offline   # skip the network
python3 scripts/check_versions.py --markdown  # regenerate the version table in reference/EXPORTERS.md
```

It fails only when a fixture was captured from a version nobody runs, because that is the
comparison that decides whether a rule works. Upstream moving ahead is news, not a defect.

The version table in reference/EXPORTERS.md is generated from those headers — do not hand-edit it.
It exists because the versions used to live in this README as a second, manual copy, and
that copy had drifted on five exporters, including one changed an hour earlier.
