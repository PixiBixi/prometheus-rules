# Review des règles Prometheus — août 2026

Review complète des **378 alertes / 23 fichiers** et **3 fichiers de recording rules**,
menée par 5 agents en parallèle, chaque constat re-vérifié contre les fixtures
`exporters/` et, quand c'était reproductible, contre `promtool test rules`.

**État : la majorité est corrigée** (30 commits, `f4276f2`..`a0e8382`). Ce document ne
conserve que ce qui reste ouvert, plus le contexte nécessaire pour l'arbitrer.

Le compte d'alertes passe de **378 à 372** : 4 alertes mortes supprimées, 2 paires de
doublons fusionnées.

---

## Ce qui a été fait

| Thème | Effet |
|---|---|
| 4 faux positifs permanents | Alertes qui hurlaient en continu → silencieuses |
| 3 recording rules en erreur d'évaluation | `found duplicate series for the match group` → fonctionnelles |
| 18 alertes mortes + 1 RR morte | 14 réparées, 4 supprimées |
| 20 RR HAProxy orphelines | Re-taguées et consommées par 11 alertes |
| 13 watchdogs `up == 0` | Couvrent à nouveau les deux modes de panne |
| ~45 P2 / ~25 P3 | Bruit, fenêtres, gardes, annotations |
| 2 paires de doublons | Fusionnées |
| Scripts Python | `build.py` 2× plus rapide, `validate_rules.py` 4× |
| **`tests/`** | **12 fichiers `promtool test rules`, joués contre la révision avant *et* après chaque correctif** |

### Deux régressions issues de l'audit précédent, annulées

`ALERTS_AUDIT.md` (mai 2026, supprimé) a causé deux dégâts, tous deux réparés :

- Sa correction P0 #1 proposait `jvm_memory_used_bytes` / `jvm_memory_max_bytes`. Ces
  noms n'existent pas — le JMX exporter expose `jvm_memory_bytes_used`. Appliquée en
  `c137592`, elle a supprimé `HighJVMUsage` (cassée, mais qui visait la vraie métrique)
  au profit de deux alertes mortes. Annulé par `7c32078`.
- Sa recommandation I1 a été appliquée à 12 fichiers en `5334c57` et a retiré `up == 0`
  de tous les watchdogs par exporter. Annulé par `66c2b44`.

**Leçon appliquée** : `promtool check rules` ne valide que la syntaxe. Ces deux
régressions passaient la validation. C'est ce qui a motivé `tests/`.

---

## Ce qui reste ouvert

### R1 — `KeepalivedSplitBrain` / `KeepalivedNoMaster` sont probablement inversées

**Priorité : la plus haute du reliquat.** Non corrigé faute de confirmation de
l'énumération exacte de l'exporter déployé.

`rules/keepalived.rules.yml:13,22`
```promql
count by (vrid) (keepalived_vrrp_state == 1) > 1    # KeepalivedSplitBrain
count by (vrid) (keepalived_vrrp_state == 1) == 0   # KeepalivedNoMaster
```

RFC 3768, reprise telle quelle par keepalived (`vrrp_state_t`) :
`INIT=0, BACKUP=1, MASTER=2`. La fixture montre `keepalived_vrrp_state{vrid="1"} 2`,
cohérent avec un nœud MASTER.

Si l'énumération est bien celle-là, `== 1` sélectionne les **BACKUP** :

- `KeepalivedSplitBrain` compte les nœuds en veille → **vrai en permanence** dès qu'il y
  a 2 backups, et ne détecte jamais un vrai split-brain (2 MASTER) ;
- `KeepalivedNoMaster` tire dès qu'aucun nœud n'est en BACKUP — cas normal d'un cluster à
  un seul membre — et ne détecte jamais l'absence réelle de MASTER.

**À faire** : confirmer l'énumération sur l'exporter déployé (`curl` sur un nœud MASTER
et un nœud BACKUP), puis remplacer `== 1` par `== 2` dans les deux.

### R2 — Constats « à confirmer » nécessitant un accès à l'infra réelle

Les fixtures ne permettent pas de trancher. Aucun n'est corrigé.

| Constat | Fichier | À vérifier |
|---|---|---|
| `PromtailRequestErrors` : le regex `5..\|failed` ne matche pas les échecs réseau, qui remontent `status_code="-1"` | `promtail.rules.yml:5` | La valeur réelle sur votre version de promtail |
| `PromtailRequestLatency` groupe `by (…, route, …)` ; `route` n'existe pas sur cette métrique (probablement copié depuis `loki_request_duration_seconds`) | `promtail.rules.yml` | Idem — l'annotation rend vide |
| `MySQLReplicationDown` utilise `mysql_slave_status_*` et le label `master_host`, absents de la fixture (cluster Galera pur) | `mysql.rules.yml:3` | Le collecteur `--collect.slave_status` est-il activé ? |
| `PostgreSQLRepliDown` / `PostgresqlUnusedReplicationSlot` : `pg_replication_slots_active` absent de la fixture | `postgresql.rules.yml:93,174` | Nom réel selon la version de postgres_exporter |
| Métriques PG issues d'un `queries.yaml` custom : `pg_stat_user_tables_*`, `pg_bloat_*`, `pg_general_index_info_*`, `pg_replication_is_replica` | `postgresql.rules.yml` | Aucun `queries.yaml` dans `misc/`, contrairement aux configs JMX |
| `cert-manager` : les annotations lisent `exported_namespace`, la fixture porte `namespace` | `cert-manager.rules.yml:29,42` | Dépend de votre scrape (Operator/ServiceMonitor ou non) |
| `HAproxyFrontendDown` suppose que la série `state="OPEN"` est émise même quand ce n'est pas l'état courant | `haproxy.rules.yml:145` | Voir R4 — la fixture est dédupliquée, impossible à trancher |
| `HAproxySticktable*` : `haproxy_sticktable_size`/`_used` présentes en 2x, absentes en 3x | `haproxy.rules.yml:484,496` | Artefact de fixture, ou vraiment supprimé en 3.x ? |
| `Segfault` : `server_metrics{dimension="segfault"}` — counter cumulatif ou gauge remise à 0 ? | `basis.rules.yml:142` | Si counter, l'alerte reste bloquée à vie |
| `k8s.records` : `+Inf` si un conteneur déclare `requests: 0` | `k8s.records.yml:17-21,35-39` | Risque faible (KSM n'émet la série que si déclarée) |

### R3 — Paliers qui se déclenchent ensemble → règles d'inhibition Alertmanager

Ce n'est pas corrigeable dans les règles seules : il faut des `inhibit_rule` côté
Alertmanager, ou un chaînage `unless`. Aucun n'est en place.

- HAProxy `maxconn` : paliers à 50 %, 80 % et 90 % → **3 alertes** à 92 %
  (`haproxy.rules.yml:62,74,86`)
- HAProxy 4xx backend et serveur : paires `> 50` critical / `> 15` warning
- HAProxy stick tables : 90 / 80
- CoreDNS : paires `High` / `Elevated` (`coredns.rules.yml:26/49`, `:64/87`)
- node températures : `crit_celsius >= max_celsius` par construction, donc
  `NodeHardwareTemperatureTooHigh` et `…Warning` partent toujours ensemble
  (`basis.rules.yml:560-576`)
- k8s : `KubernetesDeploymentReplicasMismatch` et `KubernetesReplicasetReplicasMismatch`
  — chaque Deployment possède un ReplicaSet, donc double notification systématique
- k8s : `KubernetesStatefulsetDown` (critical) et `…ReplicasMismatch` (warning) se
  recouvrent sur un StatefulSet dégradé

### R4 — Hygiène des fixtures

- **`exporters/keydb_exporter` contient du JMX Kafka/KSQL** — 0 ligne `redis_*`, 139
  lignes `kafka_`/`ksql_`/`jvm_`. Les 12 alertes KeyDB ne sont validables contre rien, et
  `build.py` présente KeyDB avec des métriques Kafka dans `docs/data.json` (la vue
  « uncovered metrics » est donc fausse pour cet exporter). Seul des 20 fichiers dont le
  contenu ne correspond pas au nom. À régénérer depuis un vrai `redis_exporter`.
- Les fixtures HAProxy ne respectent pas la règle de dédup annoncée dans `CLAUDE.md`
  (« Enum labels (`mode`, `state`, etc.): all values kept ») pour les métriques
  `*_status` : une seule valeur d'état est conservée. C'est ce qui empêche de trancher
  `HAproxyFrontendDown` en R2.

### R5 — Reliquat P2/P3 non traité

- **9 ratios HAProxy sans garde de volume** (`:249,258,267,360,373,387,428,437,446`) : un
  backend recevant 1 requête en 5 min, en erreur, produit 100 % → critical. Leurs
  voisines bien écrites (`:172,233,335,412`) ont toutes un `and … > 10`.
- **`PrometheusTimeseriesCardinality`** (`prometheus.rules.yml`) : la requête la plus
  chère du dépôt. Trois réserves — coût d'un scan intégral du head block toutes les 10
  min ; **auto-référence** (`{__name__=~".+"}` inclut la sortie de la RR, qui crée N
  séries) ; seuil `> 10000` absolu, banal pour `kube-state-metrics` ou `cadvisor`.
  Alternative : `prometheus_tsdb_head_series` pour le total, et
  `/api/v1/status/tsdb` pour le détail par métrique (déjà calculé, coût nul).
- **`KubernetesApiServerLatency`** (`kubernetes.rules.yml`) : `sum … WITHOUT (subresource)`
  ne retire qu'un label sur la métrique la plus cardinale de l'apiserver → quantile
  calculé sur ~tout, et p99 **par code HTTP** (les 504 ont mécaniquement un p99 > 1s).
  Manque aussi le sélecteur `job="apiserver"` présent sur ses voisines.
- **`KubernetesCronjobFailing`** : un CronJob qui **n'a jamais réussi** n'a pas de série
  `kube_cronjob_status_last_successful_time`, donc la comparaison ne retourne rien. Le
  cas le plus grave n'est pas couvert.
- **`KubernetesJobSlowCompletion`** : depuis KSM ≥ 2.1, `kube_job_status_failed` porte un
  label `reason` **seulement quand `failed > 0`**. La soustraction ne matche alors plus,
  et le Job disparaît du résultat — précisément le cas intéressant. Correctif si
  confirmé : `sum without (reason) (…)`.
- **`OldMetricsTextfile`** (`basis.rules.yml:40,48,56`) : trois alertes de même nom et
  mêmes labels. Fonctionnellement correctes (sélecteurs `file` disjoints) mais c'est le
  dernier lint `duplicate-rules` du dépôt. **Vrai trou au passage** : le catch-all `:57`
  exclut `.*server_metrics.*` et aucune alerte ne couvre ce pattern — ces textfiles ne
  sont surveillés par rien.
- **`GaleraWrongSize`** (`mysql.rules.yml:40`) : seuil absolu `< 3` non portable (un
  cluster peut légitimement avoir 5 ou 7 nœuds).
- **`MysqlConnectionErrors`** (`mysql.rules.yml:30`) : `critical` dès la première erreur,
  sans distinguer le label `error` (`accept`, `internal`, `max_connections`, `tcpwrap`…),
  dont certains sont bénins.
- **`RedisDisconnectedSlaves`** (`keydb.rules.yml:47`) : `count(…) - sum(…) - 1 > 0`
  suppose une topologie à un seul master.
- **`PostgresChecksumFailures`** : `NaN` quand `data_checksums` est désactivé — no-op
  silencieux. Précondition opérationnelle, pas un bug de règle.

### R6 — Renommages : décision prise de ne pas les faire

Renommer une alerte change son identité côté Alertmanager, ce qui casse les silences en
cours et toute route matchant `alertname`. **Arbitré : on garde les noms historiques.**
Consigné ici pour que le décalage nom/sémantique ne soit pas re-signalé comme un bug :

- `HAproxyServerQueueFull` teste « file non vide » (`> 0`), pas « pleine »
- `HAproxyBackendMaxActiveSessionHigh` est préfixé `Backend` mais bâti sur
  `haproxy_server_*`, et lit désormais `current_sessions` et non `max_sessions`
- `k8s.records` : `kube_namespace_cpu_limit` / `_request` et leurs équivalents mémoire
  sont agrégés **par pod**, pas par namespace (les vraies agrégations namespace sont plus
  bas dans le fichier)
- `KubernetesJobRunningTooLong` a en revanche bien été renommé (ex-`KubernetesCronjobTooLong`),
  parce que l'alerte était morte : aucun silence ni route ne pouvait en dépendre.

---

## Constats infirmés

Signalés par la review puis **réfutés** à la vérification. Documentés pour ne pas être
re-signalés :

- **`NVMEHighTemperature > 158`** : pas un bug d'unité. Le HELP de la fixture confirme que
  `nvme_temperature` est nativement en Fahrenheit, et `158` = 70 °C exactement. Le constat
  X3 de l'ancien audit est faux.
- **Guillemets typographiques** : aucun dans les 26 fichiers. Le constat X2 de l'ancien
  audit était déjà obsolète.
- **`HostDown` n'était pas un angle mort** : `PrometheusTargetMissing`, alors sans filtre
  de job, rattrapait `up == 0` pour tous les exporters. Le défaut réel était la perte de
  routage métier et la double notification — corrigé en `66c2b44`, pas une perte de
  détection.
- **`cluster_id` dans `k8s.records`** : le label n'existe nulle part. `on()` le traite
  comme vide des deux côtés, donc c'est un no-op silencieux et non une casse. Laissé en
  place (no-op s'il reste absent, régression s'il existe en prod). Le message d'erreur
  reproduit en `46b7450` le confirme : le groupe d'appariement réel est
  `{container, instance, pod}`.
- **`by (namespace,…)` dans `PostgresqlHighRollbackRate`** : donné comme label mort. Il est
  en fait utilisé 5 fois dans la même alerte, de façon cohérente des deux côtés de la
  division — inoffensif s'il est absent, correct s'il vient du relabeling k8s. Ressemble à
  un choix, pas à une coquille.

---

## Travailler sur ce dépôt

```bash
python3 validate_rules.py           # syntaxe + lint (lint non bloquant par défaut)
python3 validate_rules.py --strict  # lint bloquant
python3 run_tests.py                # tests unitaires promtool
```

Les trois tournent via pre-commit. **Toute correction de règle doit venir avec un cas
dans `tests/`** — idéalement un qui tire et un qui doit rester silencieux. C'est le seul
mécanisme qui aurait attrapé les 18 alertes mortes de cette review, et le seul qui
empêchera la prochaine régression du type `c137592`.

Un lint `duplicate-rules` subsiste volontairement : les trois `OldMetricsTextfile`
(voir R5).
