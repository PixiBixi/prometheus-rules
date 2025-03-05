# prometheus-rules
A bunch of Prometheus rules using some exporters

  * In the `exporter` folder, you have the output of some exporters
  * In the `rules` folder, you have the matching rules

You'll see not so much warning severity rules. Why would you tell me? Because from my own experience, warning rules are ignored most of the time, so why bother create this kind of rule? :)

## Specifications

### Rules

Most of these rules have been grabbed from [Awesome Prometheus alerts](https://samber.github.io/awesome-prometheus-alerts/rules#haproxy), [Mixin Rules](https://monitoring.mixins.dev/) or simply from official exporters and customizing by myself (or left as grabbed)

  * Most of rules have a `job{} == 0` rule to be sure the exporter is working fine. Please don't forget to change this to match with your job name
    * This kind of rule doesn't work with `remote_write`

These rules have been tested with specific exporters version/ some custom parameters

### Exporters

Here the list of all used exporters

#### misc

There's no specific exporter for JMX rules. Most of the time, process using a JVM like Kafka expose this kind of metric.

I do use [Maven JMX Exporter](https://github.com/prometheus/jmx_exporter/)

#### node-exporter

**Exporter link :** [node_exporter](https://github.com/prometheus/node_exporter)
**Version used :** 1.7.0

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

#### aerospike-prometheus-exporter

**Exporter link :** [aerospike-prometheus-exporter](https://github.com/aerospike/aerospike-prometheus-exporter)
**Version used :** 1.9.0

#### blackbox_exporter

**Exporter link :** [blackbox_exporter](https://github.com/prometheus/blackbox_exporter)
**Version used :** 0.24.0

#### ssl_exporter

**Exporter link :** [ssl_exporter](https://github.com/ribbybibby/ssl_exporter)
**Version used :** 2.4.2

#### haproxy

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

**HAproxy link :** [haproxy](https://github.com/haproxy/haproxy)
**Version used :** 2.8.0

#### ipsec_exporter

**Exporter link :** [ipsec_exporter](https://github.com/dennisstritzke/ipsec_exporter)
**Version used :** 0.4.0

#### kafka

**Exporter link :** [jmx_exporter](https://github.com/prometheus/jmx_exporter/)
**Version used :** 0.17.2

Kafka metrics rely on the way to configure the exporter. Please refer to the `kafka_exporter_config.yaml` to have the same metrics as me.

Then, you must create an override of your Kafka systemd unit like this :

```
[Service]
Environment="KAFKA_OPTS=-javaagent:/usr/share/java/kafka/jmx_prometheus_javaagent-0.17.2.jar=7072:/etc/kafka/zookeeper_exporter_config.yaml"
```

#### ksql

**Exporter link :** [jmx_exporter](https://github.com/prometheus/jmx_exporter/)
**Version used :** 0.17.2

KSQL metrics rely on the way to configure the exporter. Please refer to the `ksqldb_exporter_config.yaml` to have the same metrics as me.

Then, you must create an override of your KSQL systemd unit like this :

```
[Service]
Environment="KSQL_OPTS=-javaagent:/usr/share/java/kafka/jmx_prometheus_javaagent-{{ jmxexporter_version }}.jar=7073:/etc/ksqldb/ksqldb_exporter_config.yaml"
```

#### zookeeper

**Exporter link :** [jmx_exporter](https://github.com/prometheus/jmx_exporter/)
**Version used :** 0.17.2

Zookeeper metrics rely on the way to configure the exporter. Please refer to the `ksqldb_exporter_config.yaml` to have the same metrics as me.

Then, you must create an override of your zookeeper systemd unit like this :

```
[Service]
Environment="KAFKA_OPTS=-javaagent:/usr/share/java/kafka/jmx_prometheus_javaagent-0.17.2.jar=7072:/etc/kafka/zookeeper_exporter_config.yaml"
```

#### redis_exporter

Redis exporter is also used for KeyDB exporter as KeyDB is a fork of Redis

**Exporter link :** [redis_exporter](https://github.com/oliver006/redis_exporter)
**Version used :** 1.58.0

#### php-fpm_exporter

**Exporter link :** [php-fpm_exporter](https://github.com/hipages/php-fpm_exporter)
**Version used :** 2.2.0

#### mysqld_exporter

**Exporter link :** [mysqld_exporter](https://github.com/prometheus/mysqld_exporter/)
**Version used :** 0.16.0

#### prometheus

We're using the internal exporter for Prometheus

**HAproxy link :** [prometheus](https://github.com/prometheus/prometheus)
**Version used :** 3.0.0

Please don't forget there's no sense to monitor Prometheus uptime from Prom itself... seems obivous but still good to remind

#### postgres_exporter


**postgres_exporter link :** [postgres_exporter](https://github.com/prometheus-community/postgres_exporter)

**Version used :** 0.15.0

If you want running the exporter as a non-super user, please follow [these steps](https://github.com/prometheus-community/postgres_exporter?tab=readme-ov-file#running-as-non-superuser)
