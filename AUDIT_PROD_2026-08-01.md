# Audit des règles contre le Prometheus de production — 1ᵉʳ août 2026

Journal d'investigation. Chaque constat est vérifié par requête contre
`grafana.dynfactory.com` (datasource `0wjZprLnk`), pas déduit des fixtures.

## Méthode

1. Extraction locale des **394 métriques externes** référencées par les 26 fichiers de
   règles (les 50 recording rules définies dans le dépôt sont exclues).
2. Test d'existence de chacune contre la prod, par lots.
3. Pour chaque absence : distinguer **bug de règle** (mauvais nom de métrique) de
   **logiciel non déployé ici** (la règle est correcte, elle n'a simplement pas de données).

Cette distinction est la clé de tout le document. Le dépôt est un jeu de règles
réutilisable : une alerte sans données chez nous peut être parfaitement valide pour
quelqu'un d'autre.

---

## A. Bugs de règles — nom de métrique ou de label faux

Ces alertes sont **mortes chez nous et ailleurs**. À corriger.

### A1. CoreDNS expose `coredns_proxy_*`, pas `coredns_forward_*`

Métriques réellement présentes en prod :

```
coredns_forward_healthcheck_broken_total      <- existe
coredns_forward_max_concurrent_rejects_total  <- existe
coredns_proxy_healthcheck_failures_total
coredns_proxy_request_duration_seconds_bucket
coredns_proxy_conn_cache_hits_total / _misses_total
```

| Alerte | Métrique utilisée | Réalité |
|---|---|---|
| `CoreDNSForwardLatencyHigh` | `coredns_forward_request_duration_seconds_bucket` | → `coredns_proxy_request_duration_seconds_bucket` |
| `CoreDNSForwardHealthcheckFailureCount` | `coredns_forward_healthcheck_failures_total` | → `coredns_proxy_healthcheck_failures_total` |
| `CoreDNSForwardErrorsHigh` / `…Elevated` | `coredns_forward_responses_total` | **n'existe sous aucun préfixe** |
| `CoreDNSForwardHealthcheckBrokenCount` | `coredns_forward_healthcheck_broken_total` | OK |

Les deux premières sont réparables par renommage. Les deux `ForwardErrors` n'ont aucun
équivalent : ni `coredns_forward_responses_total` ni `coredns_proxy_responses_total`
n'existent. À trancher — voir §D.

### A2. `PromtailRequestErrors` rate tous les échecs réseau

`promtail.rules.yml` filtre `status_code=~"5..|failed"`. Valeurs réellement exposées :

```
promtail_request_duration_seconds_count{host="loki.dynfactory.com", status_code="204"}
promtail_request_duration_seconds_count{host="loki.dynfactory.com", status_code="-1"}
```

Le client Loki met `-1` quand l'appel HTTP échoue avant réponse. La chaîne `"failed"`
n'existe pas. L'alerte ne voit donc que les 5xx HTTP et **rate exactement les pannes
réseau**, qui sont le cas le plus courant.

### A3. `PromtailRequestLatency` groupe sur un label inexistant

`by (namespace, job, route, instance)` — le label `route` n'est pas exposé
(vérifié : `count by (route)` ne renvoie aucune valeur). Probablement copié depuis
`loki_request_duration_seconds`, côté serveur Loki. L'annotation rend vide.

---

## B. Logiciel non déployé ici — règles correctes, sans données

À **ne pas supprimer** : elles servent à qui déploie ces exporters. À documenter.

| Famille | Alertes concernées | Constat prod |
|---|---|---|
| `stackdriver_*` | les 5 de `stackdriver.rules.yml` | **0 famille de métrique** — exporter non scrapé |
| `mysql_slave_status_*` | `MySQLReplicationDown` | **0 famille** — parc Galera pur, `--collect.slave_status` inactif |
| `pg_bloat_*`, `pg_stat_user_tables_*`, `pg_general_index_info_*` | `PostgresqlBloatIndexHigh`, `PostgresqlBloatTableHigh`, `PostgresqlTooManyDeadTuples`, `PostgresqlTableNotAutoVacuumed` | absentes — issues d'un `queries.yaml` custom non déployé |
| `kafka_consumer_consumer_fetch_manager_metrics_*` | `KafkaConsumerLagHigh` | absente — job `consumer` non scrapé |
| `blackbox_exporter_config_*`, `blackbox_module_unknown_total` | alertes de rechargement de conf blackbox | absentes — seul l'endpoint de sonde est scrapé, pas le `/metrics` de l'exporter |

**Bonne nouvelle au passage** : `pg_replication_slots_active` **existe** en prod. Les
alertes `PostgreSQLRepliDown` et `PostgresqlUnusedReplicationSlot`, marquées « à
confirmer » dans la review précédente, sont donc valides.

---

## C. Confirmations positives

Vérifiées présentes en prod, aucune action :

- toute la famille `jvm_*` et `jmx_scrape_error` (les correctifs JMX de la review tiennent)
- les 11 métriques `kafka_*` hors consumer lag
- les 9 `keepalived_*`, dont `keepalived_vrrp_state`
- les 6 `ksql_ksql_engine_query_stats_*`
- `nvme_*`, `ping_*`, `phpfpm_*`, `probe_*`, `ipsec_status`, `ssl_ocsp_response_status`
- `server_metrics` (utilisée par `Segfault`), `rest_client_requests_total`
- `zookeeper_Leader`, `_QuorumSize`, `_AvgRequestLatency`, `_OutstandingRequests`
- les 9 `aerospike_*` utilisées par les règles, `backup_aerospike_state`
- `apiserver_*`, `container_*`, `certmanager_*`, `alertmanager_*`

---

## D. Décisions à prendre

1. **`CoreDNSForwardErrorsHigh` / `…Elevated`** — aucune métrique de réponses forward
   n'existe. Supprimer, ou reconstruire sur `coredns_proxy_request_duration_seconds_count`
   (qui compte les requêtes mais ne distingue pas les erreurs) ?
2. **Les 5 alertes stackdriver** — garder pour la réutilisabilité du dépôt, ou retirer
   puisque l'exporter n'est pas déployé ?
3. **`MySQLReplicationDown`** — le parc est Galera. Garder pour une future topologie
   master/replica, ou retirer ?

En l'absence d'arbitrage, l'option retenue est **garder et documenter** : la suppression
est destructive et le dépôt a vocation à être réutilisable.

---

## E. Reste à faire

- [ ] Compléter l'audit de complétude des fixtures (§A/B portent sur les métriques
      *utilisées par les règles*, pas sur l'exhaustivité des fixtures)
- [ ] Corriger A1, A2, A3 + tests promtool joués contre la révision d'avant
- [ ] Documenter B dans le README
- [ ] Logiciels non couverts (apache2 et autres) — une MR par produit
- [ ] Upgrades d'exporters côté dépôt ansible
- [ ] Ticket Jira PE consolidé, avec la MR !184
