# Exporters

Every exporter these rules are written against: which version the fixture came from,
what has to be configured on the monitored side, and the traps specific to each one.

For what the rules do with these metrics, see the [README](../README.md). For how well the
fixtures match production, see [AUDIT.md](AUDIT.md).

## Versions

**Captured from** is read out of each fixture's provenance header. **Deployed here** is
what we actually run, recorded by hand in the `DEPLOYED` map in `check_versions.py` with
the observation that established it.

The second column is the one that decides whether a rule works. A fixture captured from a
version nobody runs describes metrics that may not exist on the fleet — which is how
`PostgresChecksumFailures` came to depend on an exporter version half the estate had
already moved off.

```bash
python3 scripts/check_versions.py             # both columns, plus a live upstream check
python3 scripts/check_versions.py --offline   # skip the network
python3 scripts/check_versions.py --markdown  # regenerate the table below
```

Upstream versions are deliberately not written into this file. A document asserting
"upstream is 1.9.0" is wrong the moment upstream cuts a release, which is exactly the kind
of staleness the script exists to catch. Ask for it when you need it.

<!-- BEGIN GENERATED: python3 scripts/check_versions.py --markdown -->

<!-- Do not edit by hand: this table is rewritten from the fixture
     provenance headers and the DEPLOYED map in check_versions.py. -->

| Fixture | Captured from | Deployed here | How the deployed version is known |
|---|---|---|---|
| `aerospike` | _not recorded_ | 1.9.0 | unverified: carried over from the README |
| `apache_exporter` | 1.1.1 | — | — |
| `blackbox_exporter` | 0.24.0 | — | — |
| `cert-manager` | 1.21.1 | 1.21.1 | confirmed with the cluster operators |
| `haproxy_exporter_2x` | 2.7.11 | 2.7.11 | promex is built into HAProxy; version is HAProxy's own |
| `haproxy_exporter_3x` | 3.2.21 | 3.2.21 | promex is built into HAProxy; version is HAProxy's own |
| `ipsec_exporter` | _not recorded_ | 0.4.0 | unverified: carried over from the README |
| `kafka_exporter` | 0.17.2 | — | — |
| `keepalived_exporter` | 1.3.2 | — | — |
| `keydb_exporter` | 1.52.0 | 1.52.0 and 1.58.0 | redis_exporter_build_info: 210 instances on 1.52.0, 11 on 1.58.0 |
| `memcached_exporter` | 0.16.0 | — | — |
| `mongodb_exporter` | 0.52.0 | — | — |
| `mysqld_exporter` | 0.15.0 | — | — |
| `node_exporter` | 1.7.0 | 1.7.0, rolling to 1.12.1 | role pinned to 1.12.1; fleet rollout not yet run |
| `nvme_exporter` | _not recorded_ | — | — |
| `phpfpm_exporter` | _not recorded_ | 2.2.0 | unverified: carried over from the README |
| `ping_exporter` | _not recorded_ | — | — |
| `postgres_exporter` | 0.15.0 | 0.12.0 and 0.15.0 | counted across the fleet: 16 instances on 0.12.0, 21 on 0.15.0 |
| `prometheus` | 3.13.1 | 2.55.0 and 3.13.1 | prometheus_build_info: 2.55.0 on the main estate, 3.13.1 on dynfactory |
| `promtail_exporter` | 2.8.2 | — | — |
| `rabbitmq_exporter` | 4.3.4 | — | — |
| `rds_enhanced` | _not recorded_ | — | — |
| `stackdriver_exporter` | 0.18.0 | — | — |
| `varnish_exporter` | 1.6.1 | — | — |
| `zookeeper_exporter` | 0.17.2 | — | — |

<!-- END GENERATED -->

An exporter reading "not recorded" is not a problem with the fixture — it means nobody has
checked `*_build_info` for it yet. Several exporters here expose no version metric at all
(`nvme`, `phpfpm`, `ping`, `ipsec`, aerospike), so for those the fixture header is the only
record there will ever be.

## Notes per exporter

### misc

There's no specific exporter for JMX rules. Most of the time, process using a JVM like Kafka expose this kind of metric.

I do use [Maven JMX Exporter](https://github.com/prometheus/jmx_exporter/)

### node_exporter

[node_exporter](https://github.com/prometheus/node_exporter)

> The collector list below includes `openvpn-client@.*`, but the node_exporter Ansible
> role does not — verified against the live Prometheus, zero hosts collect an openvpn
> unit. `DownSystemdOpenVPN` therefore has no series to match. Either add the pattern to
> the role's `--collector.systemd.unit-include`, or drop the alert.

You must enable custom collectors for node-exporter :
```
--collector.systemd
--no-collector.rapl
--no-collector.schedstat
--no-collector.tapestats
--no-collector.fibrechannel
--no-collector.pressure
--no-collector.wifi
--no-collector.nfs
--no-collector.nfsd
--no-collector.xfs
--no-collector.zfs
--no-collector.infiniband
--no-collector.ipvs
--no-collector.btrfs
--collector.textfile.directory=/home/node_exporter
--collector.cpu.info
--collector.systemd.unit-include="(nginx|docker|mysql|aerospike|as-rest-gateway|promtail|crond?|sshd?|haproxy|keydb|redis_.*|bid_request_.*|php.*-fpm|teleport|keepalived|confluent-.*|squid|openvpn-client@.*|chrony|systemd-timesyncd|supervisor)".service
```

Be aware some of these module use "a lot" of CPU time, specially `--collector.cpu.info` and `--collector.systemd.unit-include`

Also, some collector have been disabled because I don't use them

### apache_exporter

[apache_exporter](https://github.com/Lusitaniae/apache_exporter) — fixture tested against Apache 2.4.68.

Requires `mod_status` with extended status, and the exporter pointed at it:

```apache
<Location "/server-status">
    SetHandler server-status
    Require all granted
</Location>
ExtendedStatus On
```

```
apache_exporter --scrape_uri=http://localhost/server-status?auto
```

Without `ExtendedStatus On` the exporter still reports worker and scoreboard state, but
`apache_accesses_total`, `apache_duration_ms_total` and `apache_sent_kilobytes_total` stay
at zero — which silently disables `ApacheSlowRequests`.

### memcached_exporter

[memcached_exporter](https://github.com/prometheus/memcached_exporter) — fixture tested against memcached 1.6.45.

No configuration needed on memcached's side; the exporter speaks the text protocol and only needs `--memcached.address`.

### varnish_exporter

[prometheus_varnish_exporter](https://github.com/jonnenauha/prometheus_varnish_exporter) — fixture tested against Varnish 9.0.3.

The exporter shells out to `varnishstat`, so it must run on the same host as Varnish with access to the shared memory in `/var/lib/varnish`. It cannot be run as a remote scraper.

Only amd64 binaries are published upstream.

### rabbitmq_exporter

[RabbitMQ Prometheus plugin](https://www.rabbitmq.com/docs/prometheus) — fixture tested against RabbitMQ 4.3.4.

RabbitMQ 3.8+ ships the `rabbitmq_prometheus` plugin, enabled by default, serving metrics on :15692. **There is no third-party exporter to deploy.**

Note the metric names differ from the old kbudde/rabbitmq_exporter that most community alert sets were written against: memory is `rabbitmq_process_resident_memory_bytes` over `rabbitmq_resident_memory_limit_bytes`, not `rabbitmq_node_mem_used`.

### mongodb_exporter

[mongodb_exporter](https://github.com/percona/mongodb_exporter) — fixture tested against MongoDB 8.

This exporter names serverStatus metrics `mongodb_ss_*` and carries dimensions as labels. Connections are `mongodb_ss_connections{conn_type="current"}`, **not** `mongodb_connections_current` as most community alert sets assume.

The fixture is trimmed: `--collector.diagnosticdata` emits ~3460 metric names, of which `mongodb_ss_metrics_*`, `mongodb_ss_wt_*` and `mongodb_sys_netstat_*` are ~2800. Those three families are sampled to 50 each; every metric the rules use is kept, and all other families are complete.

### aerospike-prometheus-exporter

[aerospike-prometheus-exporter](https://github.com/aerospike/aerospike-prometheus-exporter)

### blackbox_exporter

[blackbox_exporter](https://github.com/prometheus/blackbox_exporter)

### ssl_exporter

[ssl_exporter](https://github.com/ribbybibby/ssl_exporter)

### haproxy

We're using the internal exporter for HAproxy with this configuration

```
frontend prometheus
    bind :10011
    mode            http
    compression algo gzip
    compression type text/html text/plain
    stats enable
    stats show-node
    stats show-legends
    stats refresh 10s
    stats uri  /
    http-request use-service prometheus-exporter if { path /metrics }
```

[haproxy](https://github.com/haproxy/haproxy)

Two sample files cover both major versions — `diff exporters/haproxy_exporter_2x exporters/haproxy_exporter_3x` shows what changed between them. promex ships inside HAProxy itself, so the version in the table is HAProxy's own; there is no separate release to track.

### ipsec_exporter

[ipsec_exporter](https://github.com/dennisstritzke/ipsec_exporter)

### kafka

[jmx_exporter](https://github.com/prometheus/jmx_exporter/)

Kafka metrics rely on the way to configure the exporter. Please refer to the `kafka_exporter_config.yaml` to have the same metrics as me.

Then, you must create an override of your Kafka systemd unit like this :

```
[Service]
Environment="KAFKA_OPTS=-javaagent:/usr/share/java/kafka/jmx_prometheus_javaagent-0.17.2.jar=7072:/etc/kafka/zookeeper_exporter_config.yaml"
```

### ksql

[jmx_exporter](https://github.com/prometheus/jmx_exporter/)

KSQL metrics rely on the way to configure the exporter. Please refer to the `ksqldb_exporter_config.yaml` to have the same metrics as me.

Then, you must create an override of your KSQL systemd unit like this :

```
[Service]
Environment="KSQL_OPTS=-javaagent:/usr/share/java/kafka/jmx_prometheus_javaagent-{{ jmxexporter_version }}.jar=7073:/etc/ksqldb/ksqldb_exporter_config.yaml"
```

### zookeeper

[jmx_exporter](https://github.com/prometheus/jmx_exporter/)

Zookeeper metrics rely on the way to configure the exporter. Please refer to the `ksqldb_exporter_config.yaml` to have the same metrics as me.

Then, you must create an override of your zookeeper systemd unit like this :

```
[Service]
Environment="KAFKA_OPTS=-javaagent:/usr/share/java/kafka/jmx_prometheus_javaagent-0.17.2.jar=7072:/etc/kafka/zookeeper_exporter_config.yaml"
```

### redis_exporter / keydb_exporter

Redis exporter is also used for KeyDB exporter as KeyDB is a fork of Redis

[redis_exporter](https://github.com/oliver006/redis_exporter)

> **Metric names move between versions of this exporter.** v1.52 exposes
> `redis_config_maxclients`; current releases renamed it to `redis_max_clients`.
> The rules in this repo target the former. `exporters/keydb_exporter` is a real
> v1.52.0 scrape against KeyDB, merged from three roles — primary (with AOF and
> maxmemory configured), replica, and a cluster-enabled node — so that
> replication, AOF and `redis_cluster_*` metrics are all represented.
> Regenerate it against the version you actually run, not `:latest`.

### php-fpm_exporter

[php-fpm_exporter](https://github.com/hipages/php-fpm_exporter)

### mysqld_exporter

[mysqld_exporter](https://github.com/prometheus/mysqld_exporter/)

### prometheus

We're using the internal exporter for Prometheus

[prometheus](https://github.com/prometheus/prometheus)

Please don't forget there's no sense to monitor Prometheus uptime from Prom itself... seems obivous but still good to remind

> `prometheus_remote_storage_samples_dropped_total` is a `CounterVec` labelled by `reason`
> with no child series pre-initialised, so a healthy instance emits nothing for it. Its
> absence from a scrape is the healthy state, **not** a removal — the declaration is
> identical in 2.55.0 and 3.13.1. The fixture carries real series for it from the earlier
> 2.55.0 capture so the family stays documented.

### postgres_exporter

[postgres_exporter](https://github.com/prometheus-community/postgres_exporter)

If you want running the exporter as a non-super user, please follow [these steps](https://github.com/prometheus-community/postgres_exporter?tab=readme-ov-file#running-as-non-superuser)

> **0.15 changed two things the rules depend on.** `pg_replication_lag` became
> `pg_replication_lag_seconds` — both names are live across the estate, so both lag alerts
> match either. And 0.15 dropped the legacy auto-discovery query mode that emitted
> `pg_stat_database_checksum_failures`: only the instances still on 0.12 expose it, so
> upgrading the rest of the fleet would silently kill `PostgresChecksumFailures`.

The fixture also carries families from a custom `queries.yaml` that is deployed nowhere
(`pg_bloat_*`, `pg_general_index_info_*`, `pg_stat_user_tables_*`). The rules read them, so
dropping them would make covered alerts look uncovered.

### nvme_exporter

nvme metrics are collected through a custom exporter; there is no upstream release to track.

### ping_exporter

[ping_exporter](https://github.com/czerwonk/ping_exporter)

### promtail

We're using the internal metrics endpoint exposed by Promtail (Loki agent).

[promtail](https://grafana.com/docs/loki/latest/send-data/promtail/) — versioned with Loki, so the table's version is a Loki release. Note promtail is deprecated upstream in favour of Grafana Alloy.

### rds_enhanced

RDS Enhanced Monitoring metrics exposed via a custom exporter reading CloudWatch.

[rds_exporter](https://github.com/percona/rds_exporter)

### stackdriver_exporter

Exposes Google Cloud metrics (GCP Load Balancer, Cloud SQL, GKE, etc.) via the Stackdriver/Cloud Monitoring API.

[stackdriver_exporter](https://github.com/prometheus-community/stackdriver_exporter)

### cert-manager

Cert-manager exposes its own metrics endpoint natively (no separate exporter needed) on
port 9402.

[cert-manager](https://cert-manager.io/docs/observability/prometheus-metrics/)

Three families in the fixture are carried over from the previous capture rather than
observed: `certmanager_controller_sync_error_count` and the two
`certmanager_http_acme_client_request_*` ones only appear once there is a sync error or
real ACME activity. All three are confirmed present on our production Prometheus and are
read by the rules, so dropping them would make working alerts look uncovered.

`certmanager_issuer_ready_status` and `certmanager_clusterissuer_ready_status` are
separate metrics — a cluster with only ClusterIssuers emits just the second.
