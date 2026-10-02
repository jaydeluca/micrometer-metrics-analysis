# Bridge decision table

Registry `v2.31.1` (file_format 0.6) vs Micrometer `1.17.0`. 366 captured Micrometer instruments; 532 defined semconv metrics consulted.

## Summary

| Decision | Count |
|---|---|
| `drop:duplicate` | 155 |
| `keep` | 101 |
| `drop:non-conforming` | 61 |
| `normalize-unit` | 49 |

## Rules that cannot be checked mechanically

These decide whether a bridge mode can be a rule engine or needs a curated list.

| Rule | Cite | Why not mechanical |
|---|---|---|
| precision / descriptiveness | `naming.md:86-94` | Whether a name is 'descriptive and unambiguous' is a judgement call. `executor.active` is checkable only by a human who knows it means threads. |
| snake_case within a dot component | `naming.md:75-77` | Detecting that a component is multi-word needs a dictionary. `bytes_consumed_rate` is correct snake_case; `classes.loaded` splits one concept across two components — no regex separates those cases. |
| justified pluralization | `naming.md:249-262` | Plural is allowed when the value is a countable quantity, which the spec ties to the unit being an annotation. Micrometer units are mostly non-UCUM words, so the test is unreliable on exactly the metrics it would judge. |
| concept equivalence | `n/a` | That `hikaricp.connections.active` and `db.client.connection.count` are the same concept is human-asserted (tools/concept_map.yaml). No mechanical test exists. |
| instrument-type correctness for Micrometer-only metrics | `n/a` | Type conformance can only be checked against a semconv counterpart. A Micrometer-only metric has none, so its type cannot be judged non-conforming. |

## Per-instrument decisions

### cache

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `cache.eviction.weight` | COUNTER | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `cache.evictions` | COUNTER | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `cache.gets` | COUNTER | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `cache.puts` | COUNTER | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `cache.size` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |

### db.pool

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `hikaricp.connections` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `hikaricp.connections.acquire` | TIMER | `seconds` | drop (duplicate) ⚠️cond | agent emits db.client.connection.wait_time; gated on semconv-opt-in |
| `hikaricp.connections.active` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits db.client.connection.count; gated on semconv-opt-in |
| `hikaricp.connections.creation` | TIMER | `seconds` | drop (duplicate) ⚠️cond | agent emits db.client.connection.create_time; gated on semconv-opt-in |
| `hikaricp.connections.idle` | GAUGE | `None` | drop (duplicate) | agent emits db.client.connections.usage |
| `hikaricp.connections.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits db.client.connection.max; gated on semconv-opt-in |
| `hikaricp.connections.min` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits db.client.connection.idle.min; gated on semconv-opt-in |
| `hikaricp.connections.pending` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits db.client.connection.pending_requests; gated on semconv-opt-in |
| `hikaricp.connections.timeout` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits db.client.connection.timeouts; gated on semconv-opt-in |
| `hikaricp.connections.usage` | TIMER | `seconds` | drop (duplicate) ⚠️cond | agent emits db.client.connection.use_time; gated on semconv-opt-in |
| `jdbc.connections.max` | GAUGE | `None` | drop (duplicate) | agent emits db.client.connections.max |
| `jdbc.connections.min` | GAUGE | `None` | drop (duplicate) | agent emits db.client.connections.idle.min |

### executor

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `executor.active` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `executor.active` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `executor.completed` | COUNTER | `tasks` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'tasks' -> '{task}' |
| `executor.parallelism` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `executor.pool.core` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `executor.pool.max` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `executor.pool.size` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `executor.queue.remaining` | GAUGE | `tasks` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'tasks' -> '{task}' |
| `executor.queued` | GAUGE | `tasks` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'tasks' -> '{task}' |
| `executor.queued` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `executor.running` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `executor.steals` | COUNTER | `None` | keep | no agent equivalent and no mechanical conformance violation |

### http.client

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `http.client.requests` | TIMER | `seconds` | drop (duplicate) | agent emits http.client.request.duration |
| `http.client.requests.active` | LONG_TASK_TIMER | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `httpcomponents.httpclient.request` | TIMER | `seconds` | drop (duplicate) | agent emits http.client.request.duration |
| `okhttp.pool.connection.count` | GAUGE | `connections` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'connections' -> '{connection}' |
| `okhttp.requests` | TIMER | `seconds` | drop (duplicate) | agent emits http.client.request.duration |

### http.server

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `http.server.requests` | TIMER | `seconds` | drop (duplicate) | agent emits http.server.request.duration |
| `http.server.requests.active` | LONG_TASK_TIMER | `seconds` | drop (duplicate) ⚠️cond | agent emits http.server.active_requests; gated on experimental-flag |

### jvm

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `jvm.buffer.count` | GAUGE | `buffers` | drop (duplicate) | agent emits jvm.buffer.count |
| `jvm.buffer.memory.used` | GAUGE | `bytes` | drop (duplicate) | agent emits jvm.buffer.memory.used |
| `jvm.buffer.total.capacity` | GAUGE | `bytes` | drop (duplicate) | agent emits jvm.buffer.memory.limit |
| `jvm.classes.loaded` | GAUGE | `classes` | drop (duplicate) | agent emits jvm.class.count |
| `jvm.classes.loaded.count` | COUNTER | `classes` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'classes' -> '{class}' |
| `jvm.classes.unloaded` | COUNTER | `classes` | drop (duplicate) | agent emits jvm.class.unloaded |
| `jvm.compilation.time` | COUNTER | `ms` | keep | no agent equivalent and no mechanical conformance violation |
| `jvm.gc.concurrent.phase.time` | TIMER | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `jvm.gc.live.data.size` | GAUGE | `bytes` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'bytes' -> 'By' |
| `jvm.gc.max.data.size` | GAUGE | `bytes` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'bytes' -> 'By' |
| `jvm.gc.memory.allocated` | COUNTER | `bytes` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'bytes' -> 'By' |
| `jvm.gc.memory.promoted` | COUNTER | `bytes` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'bytes' -> 'By' |
| `jvm.gc.overhead` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `jvm.gc.pause` | TIMER | `seconds` | drop (duplicate) | agent emits jvm.gc.duration |
| `jvm.info` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `jvm.memory.committed` | GAUGE | `bytes` | drop (duplicate) | agent emits jvm.memory.committed |
| `jvm.memory.max` | GAUGE | `bytes` | drop (duplicate) | agent emits jvm.memory.limit |
| `jvm.memory.usage.after.gc` | GAUGE | `None` | drop (duplicate) | agent emits jvm.memory.used_after_last_gc |
| `jvm.memory.used` | GAUGE | `bytes` | drop (duplicate) | agent emits jvm.memory.used |
| `jvm.threads.daemon` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `jvm.threads.deadlocked` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `jvm.threads.deadlocked.monitor` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `jvm.threads.live` | GAUGE | `threads` | drop (duplicate) | agent emits jvm.thread.count |
| `jvm.threads.peak` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `jvm.threads.started` | COUNTER | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `jvm.threads.states` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `jvm.threads.virtual.pinned` | TIMER | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `jvm.threads.virtual.submit.failed` | COUNTER | `None` | keep | no agent equivalent and no mechanical conformance violation |

### kafka

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `kafka.admin.client.connection.close.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.connection.close.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.connection.count` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.connection.creation.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.connection.creation.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.failed.authentication.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.failed.authentication.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.failed.reauthentication.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.failed.reauthentication.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.incoming.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.admin.client.incoming.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.io.ratio` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['ratio'] (no semconv target to rename onto) |
| `kafka.admin.client.io.time.ns.avg` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['ns'] (no semconv target to rename onto) |
| `kafka.admin.client.io.time.ns.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['ns']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.io.wait.ratio` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['ratio'] (no semconv target to rename onto) |
| `kafka.admin.client.io.wait.time.ns.avg` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['ns'] (no semconv target to rename onto) |
| `kafka.admin.client.io.wait.time.ns.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['ns']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.io.waittime.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.iotime.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.network.io.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.network.io.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.node.incoming.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.admin.client.node.incoming.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.node.outgoing.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.admin.client.node.outgoing.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.node.request.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.node.request.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.node.request.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.node.request.size.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.node.request.size.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.node.request.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.node.response.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.node.response.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.outgoing.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.admin.client.outgoing.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.reauthentication.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.reauthentication.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.request.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.request.size.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.request.size.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.request.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.response.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.response.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.select.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.select.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.successful.authentication.no.reauth.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.successful.authentication.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.successful.authentication.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.admin.client.successful.reauthentication.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.admin.client.successful.reauthentication.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.app.info.start.time.ms` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['ms'] (no semconv target to rename onto) |
| `kafka.consumer.commit.sync.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.commit_sync_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.committed.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.committed_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.connection.close.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.connection_close_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.connection.close.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.connection_close_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.connection.count` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.connection_count via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.connection.creation.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.connection_creation_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.connection.creation.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.connection_creation_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.coordinator.assigned.partitions` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.commit.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.commit.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.commit.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.commit.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.coordinator.failed.rebalance.rate.per.hour` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.failed.rebalance.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.coordinator.heartbeat.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.heartbeat.response.time.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.heartbeat.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.coordinator.join.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.join.time.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.join.time.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.join.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.coordinator.last.heartbeat.seconds.ago` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['seconds'] (no semconv target to rename onto) |
| `kafka.consumer.coordinator.last.rebalance.seconds.ago` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['seconds'] (no semconv target to rename onto) |
| `kafka.consumer.coordinator.partition.assigned.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.partition.assigned.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.partition.lost.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.partition.lost.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.partition.revoked.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.partition.revoked.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.rebalance.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.rebalance.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.rebalance.latency.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.coordinator.rebalance.rate.per.hour` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.rebalance.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.coordinator.sync.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.sync.time.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.sync.time.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.coordinator.sync.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.failed.authentication.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.failed_authentication_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.failed.authentication.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.failed_authentication_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.failed.reauthentication.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.failed_reauthentication_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.failed.reauthentication.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.failed_reauthentication_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.fetch.manager.bytes.consumed.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['bytes'] (no semconv target to rename onto) |
| `kafka.consumer.fetch.manager.bytes.consumed.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['bytes']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.fetch.manager.fetch.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.fetch.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.fetch.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.fetch.size.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.fetch.size.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.fetch.throttle.time.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.fetch.throttle.time.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.fetch.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.fetch.manager.preferred.read.replica` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.records.consumed.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.records.consumed.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.fetch.manager.records.lag` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.records.lag.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.records.lag.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.records.lead` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.records.lead.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.records.lead.min` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.fetch.manager.records.per.request.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.incoming.byte.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.incoming_byte_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.incoming.byte.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.incoming_byte_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.io.ratio` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.io_ratio via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.io.time.ns.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.io_time_ns_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.io.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.io_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.io.wait.ratio` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.io_wait_ratio via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.io.wait.time.ns.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.io_wait_time_ns_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.io.wait.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.io_wait_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.io.waittime.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.io_waittime_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.iotime.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.iotime_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.last.poll.seconds.ago` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.last_poll_seconds_ago via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.network.io.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.network_io_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.network.io.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.network_io_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.node.incoming.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.consumer.node.incoming.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.node.outgoing.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.consumer.node.outgoing.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.node.request.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.node.request.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.node.request.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.node.request.size.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.node.request.size.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.node.request.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.node.response.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.node.response.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.consumer.outgoing.byte.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.outgoing_byte_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.outgoing.byte.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.outgoing_byte_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.poll.idle.ratio.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.poll_idle_ratio_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.reauthentication.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.reauthentication.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.consumer.request.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.request_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.request.size.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.request_size_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.request.size.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.request_size_max via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.request.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.request_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.response.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.response_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.response.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.response_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.select.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.select_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.select.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.select_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.successful.authentication.no.reauth.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.successful_authentication_no_reauth_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.successful.authentication.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.successful_authentication_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.successful.authentication.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.successful_authentication_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.successful.reauthentication.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.successful_reauthentication_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.successful.reauthentication.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.successful_reauthentication_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.time.between.poll.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.time_between_poll_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.consumer.time.between.poll.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.consumer.time_between_poll_max via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.batch.size.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.batch_size_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.batch.size.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.batch_size_max via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.batch.split.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.batch_split_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.batch.split.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.batch_split_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.buffer.available.bytes` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.buffer_available_bytes via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.buffer.exhausted.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.buffer_exhausted_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.buffer.exhausted.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.buffer_exhausted_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.buffer.total.bytes` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.buffer_total_bytes via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.bufferpool.wait.ratio` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.bufferpool_wait_ratio via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.bufferpool.wait.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.bufferpool_wait_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.bufferpool.wait.time.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.bufferpool_wait_time_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.compression.rate.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.compression_rate_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.connection.close.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.connection_close_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.connection.close.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.connection_close_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.connection.count` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.connection_count via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.connection.creation.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.connection_creation_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.connection.creation.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.connection_creation_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.failed.authentication.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.failed_authentication_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.failed.authentication.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.failed_authentication_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.failed.reauthentication.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.failed_reauthentication_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.failed.reauthentication.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.failed_reauthentication_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.flush.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.flush_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.incoming.byte.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.incoming_byte_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.incoming.byte.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.incoming_byte_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.io.ratio` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.io_ratio via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.io.time.ns.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.io_time_ns_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.io.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.io_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.io.wait.ratio` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.io_wait_ratio via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.io.wait.time.ns.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.io_wait_time_ns_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.io.wait.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.io_wait_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.io.waittime.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.io_waittime_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.iotime.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.iotime_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.metadata.age` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.metadata_age via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.metadata.wait.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.metadata_wait_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.network.io.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.network_io_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.network.io.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.network_io_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.node.incoming.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.producer.node.incoming.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.producer.node.outgoing.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.producer.node.outgoing.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.producer.node.request.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.node.request.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.node.request.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.node.request.size.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.node.request.size.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.node.request.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.producer.node.response.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.node.response.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.producer.outgoing.byte.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.outgoing_byte_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.outgoing.byte.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.outgoing_byte_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.produce.throttle.time.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.produce_throttle_time_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.produce.throttle.time.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.produce_throttle_time_max via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.reauthentication.latency.avg` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.reauthentication.latency.max` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.record.error.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_error_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.error.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_error_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.queue.time.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_queue_time_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.queue.time.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_queue_time_max via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.retry.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_retry_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.retry.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_retry_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.send.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_send_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.send.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_send_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.size.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_size_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.record.size.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.record_size_max via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.records.per.request.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.records_per_request_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.request.latency.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.request_latency_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.request.latency.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.request_latency_max via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.request.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.request_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.request.size.avg` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.request_size_avg via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.request.size.max` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.request_size_max via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.request.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.request_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.requests.in.flight` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.requests_in_flight via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.response.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.response_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.response.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.response_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.select.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.select_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.select.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.select_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.successful.authentication.no.reauth.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.successful_authentication_no_reauth_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.successful.authentication.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.successful_authentication_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.successful.authentication.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.successful_authentication_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.successful.reauthentication.rate` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.successful_reauthentication_rate via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.successful.reauthentication.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.successful_reauthentication_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.topic.byte.rate` | GAUGE | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte'] (no semconv target to rename onto) |
| `kafka.producer.topic.byte.total` | COUNTER | `None` | drop (non-conforming) | unit-in-name: name encodes its unit via component(s) ['byte']; total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.producer.topic.compression.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.topic.record.error.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.topic.record.error.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.producer.topic.record.retry.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.topic.record.retry.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.producer.topic.record.send.rate` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `kafka.producer.topic.record.send.total` | COUNTER | `None` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `kafka.producer.txn.abort.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.txn_abort_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.txn.begin.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.txn_begin_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.txn.commit.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.txn_commit_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.txn.init.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.txn_init_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.txn.send.offsets.time.ns.total` | COUNTER | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.txn_send_offsets_time_ns_total via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |
| `kafka.producer.waiting.threads` | GAUGE | `None` | drop (duplicate) ⚠️cond | agent emits kafka.producer.waiting_threads via its own metric bridge (bridge-vs-bridge); gated on semconv-preview |

### logging

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `log4j2.events` | COUNTER | `events` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'events' -> '{event}' |
| `logback.events` | COUNTER | `events` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'events' -> '{event}' |

### netty

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `netty.allocator.memory.pinned` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `netty.allocator.memory.used` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `netty.allocator.pooled.arenas` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `netty.allocator.pooled.cache.size` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `netty.allocator.pooled.chunk.size` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `netty.allocator.pooled.threadlocal.caches` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `netty.eventexecutor.tasks.pending` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |
| `netty.eventexecutor.workers` | GAUGE | `None` | keep | no agent equivalent and no mechanical conformance violation |

### pool

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `commons.pool2.borrowed` | COUNTER | `objects` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'objects' -> '{object}' |
| `commons.pool2.created` | COUNTER | `objects` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'objects' -> '{object}' |
| `commons.pool2.destroyed` | COUNTER | `objects` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'objects' -> '{object}' |
| `commons.pool2.destroyed.by.borrow.validation` | COUNTER | `objects` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'objects' -> '{object}' |
| `commons.pool2.destroyed.by.evictor` | COUNTER | `objects` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'objects' -> '{object}' |
| `commons.pool2.max.borrow.wait` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `commons.pool2.mean.active` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `commons.pool2.mean.borrow.wait` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `commons.pool2.mean.idle` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `commons.pool2.num.active` | GAUGE | `objects` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'objects' -> '{object}' |
| `commons.pool2.num.idle` | GAUGE | `objects` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'objects' -> '{object}' |
| `commons.pool2.num.waiters` | GAUGE | `threads` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'threads' -> '{thread}' |
| `commons.pool2.returned` | COUNTER | `objects` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'objects' -> '{object}' |

### rpc

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `grpc.client.processing.duration` | TIMER | `seconds` | drop (duplicate) ⚠️cond | agent emits rpc.client.call.duration; gated on semconv-opt-in |
| `grpc.client.requests.sent` | COUNTER | `messages` | drop (duplicate) | agent emits rpc.client.request.size |
| `grpc.client.responses.received` | COUNTER | `messages` | drop (duplicate) | agent emits rpc.client.response.size |
| `grpc.server.processing.duration` | TIMER | `seconds` | drop (duplicate) ⚠️cond | agent emits rpc.server.call.duration; gated on semconv-opt-in |
| `grpc.server.requests.received` | COUNTER | `messages` | drop (duplicate) | agent emits rpc.server.request.size |
| `grpc.server.responses.sent` | COUNTER | `messages` | drop (duplicate) | agent emits rpc.server.response.size |

### spring

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `application.ready.time` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `application.started.time` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |

### system

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `disk.free` | GAUGE | `bytes` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'bytes' -> 'By' |
| `disk.total` | GAUGE | `bytes` | drop (non-conforming) | total-suffix: Counters and UpDownCounters SHOULD NOT append `total` (no semconv target to rename onto) |
| `process.cpu.time` | COUNTER | `ns` | drop (duplicate) | agent emits jvm.cpu.time |
| `process.cpu.usage` | GAUGE | `None` | drop (duplicate) | agent emits jvm.cpu.recent_utilization |
| `process.files.max` | GAUGE | `files` | drop (duplicate) | agent emits jvm.file_descriptor.limit |
| `process.files.open` | GAUGE | `files` | drop (duplicate) | agent emits jvm.file_descriptor.count |
| `process.start.time` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `process.uptime` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `system.cpu.count` | GAUGE | `None` | drop (duplicate) | agent emits jvm.cpu.count |
| `system.cpu.usage` | GAUGE | `None` | drop (duplicate) | agent emits jvm.system.cpu.utilization |
| `system.load.average.1m` | GAUGE | `None` | drop (duplicate) | agent emits jvm.system.cpu.load_1m |

### tomcat

| Micrometer instrument | Type | Unit | Decision | Reason |
|---|---|---|---|---|
| `tomcat.sessions.active.current` | GAUGE | `sessions` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'sessions' -> '{session}' |
| `tomcat.sessions.active.max` | GAUGE | `sessions` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'sessions' -> '{session}' |
| `tomcat.sessions.alive.max` | GAUGE | `seconds` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'seconds' -> 's' |
| `tomcat.sessions.created` | COUNTER | `sessions` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'sessions' -> '{session}' |
| `tomcat.sessions.expired` | COUNTER | `sessions` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'sessions' -> '{session}' |
| `tomcat.sessions.rejected` | COUNTER | `sessions` | normalize-unit | Micrometer-only metric, conforming apart from base unit 'sessions' -> '{session}' |

