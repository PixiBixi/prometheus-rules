# Fixtures and rules versus reality

How closely this repo matches the estate it was written against. Everything here has a
date on it and is expected to rot — that is the difference between this file and
[EXPORTERS.md](EXPORTERS.md), which describes how things work rather than how they
currently are.

Nothing below is a bug report. A rule with no data here is usually correct and simply
describes software we do not run; this ruleset is meant to be reusable.

## Investigation logs

| Document | Date | What it covers |
|---|---|---|
| [AUDIT_PROD_2026-08-01.md](AUDIT_PROD_2026-08-01.md) | 2026-08-01 | every metric the rules reference, tested against the live Prometheus |
| [ALERTS_REVIEW_2026-08.md](ALERTS_REVIEW_2026-08.md) | 2026-08 | full review of the rule set: dead expressions, vector-matching bugs, duplicates |

## Fixture completeness versus production

Counted 2026-08-01: distinct metric names per family in `exporters/` against the same
families in the live Prometheus. Exact parity is not the goal — prod aggregates hosts
running different versions and collector sets — but large gaps mean the docs
"uncovered metrics" view is misleading for that exporter.

| Family | Fixture | Prod | Gap |
|---|---|---|---|
| `pg_*` | 285 | 357 | **-72** — fixture misses a fifth of what prod exposes |
| `kafka_*` | 177 | 188 | -11 |
| `zookeeper_*` | 62 | 66 | -4 |
| `ping_*` | 6 | 10 | -4 |
| `aerospike_*`, `keepalived_*`, `promtail_*`, `certmanager_*` | — | — | -1 to -2, negligible |
| `haproxy_*`, `nvme_*`, `ipsec_*` | — | — | **0, in parity** |
| `mysql_*` | 995 | 818 | **+177** — the fixture has *more* than prod |

Two worth acting on:

- **`pg_*` is 72 metrics short.** The fixture was recaptured at 0.15.0 on 2026-08-02, which
  addressed the version drift but not the count: the missing families come from a custom
  `queries.yaml` that is deployed nowhere and cannot be reproduced from a stock exporter.
- **`mysql_*` has 177 metrics prod does not.** The fixture was captured with more
  collectors enabled than the fleet runs. Harmless for rule authoring, but it inflates
  the uncovered-metrics count for MySQL.

`haproxy_*` and `keydb_exporter` were both regenerated from real scrapes on 2026-08-01
and match their deployed versions.

## Rules with no data on our own Prometheus

Audited 2026-08-01 by testing all 394 metrics the rules reference against the live
Prometheus. The following are **not bugs** — the rules are correct, the software simply
is not deployed (or not scraped) here.

| Family | Alerts | Why there is no data |
|---|---|---|
| `stackdriver_*` | all 5 in `stackdriver.rules.yml` | exporter not scraped — zero metric families present |
| `mysql_slave_status_*` | `MySQLReplicationDown` | the fleet is Galera-only; `--collect.slave_status` is off |
| `pg_bloat_*`, `pg_stat_user_tables_*`, `pg_general_index_info_*` | `PostgresqlBloatIndexHigh`, `PostgresqlBloatTableHigh`, `PostgresqlTooManyDeadTuples`, `PostgresqlTableNotAutoVacuumed` | these come from a custom postgres_exporter `queries.yaml` that is not deployed |
| `kafka_consumer_consumer_fetch_manager_metrics_*` | `KafkaConsumerLagHigh` | the `consumer` job is not scraped |
| `blackbox_exporter_config_*`, `blackbox_module_unknown_total` | blackbox config-reload alerts | only the probe endpoint is scraped, not the exporter's own `/metrics` |

Enabling any of them is a scrape or exporter-flag change, not a rule change.

## How to be wrong about a metric

Four of these were recorded as removals or renames before turning out to be neither. The
pattern is the same every time: **a metric absent from one instance is not evidence of
anything until that instance is known to exercise the feature.**

- **Check more than one Prometheus.** CoreDNS 1.11.0 renamed the forward plugin's metrics
  from `coredns_forward_*` to `coredns_proxy_*`, and this estate runs both — 1.11.4 on one
  cluster, 1.10.x on another. Looking at a single datasource made
  `coredns_forward_responses_total` appear not to exist anywhere. The rules now match
  either naming.
- **Check the container is not `:latest`.** A fixture regenerated from `:latest` made
  `RedisTooManyConnections` look dead, when `redis_config_maxclients` is alive on 220 of
  221 production instances running v1.52.
- **Check the feature is actually configured.** cert-manager without a namespaced Issuer,
  and again without ACME, each looked like a metric had been dropped.
- **Check the metric is not a `CounterVec`.** `prometheus_remote_storage_samples_dropped_total`
  has no child series until a sample is actually dropped, so a healthy instance emits
  nothing for it. This was recorded as "removed in Prometheus 3.0" twice before the
  declaration in `storage/remote/queue_manager.go` — byte-identical in 2.55.0 and 3.13.1 —
  settled it.

Read the upstream declaration before recording a removal. It is faster than the three
production queries it replaces, and it does not depend on the estate being representative.
