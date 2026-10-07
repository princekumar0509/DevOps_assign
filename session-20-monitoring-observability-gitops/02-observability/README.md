# Observability

Study notes for Session 20 (Monitoring, Observability & GitOps). They cover the difference between monitoring and observability, the three telemetry pillars, how the pillars connect, why observability matters for distributed systems, the common tools, and how all of it applies to Kubernetes.

## 1. Monitoring vs Observability

**Monitoring** is the practice of collecting predefined signals (CPU usage, error rate, uptime checks) and alerting when they cross known thresholds. It answers questions that were known in advance, the *known-unknowns*: "is disk usage above 90%?".

**Observability** is a property of a system: how well its internal state can be inferred from the telemetry it emits (the term comes from control theory). An observable system lets engineers ask *new* questions during an incident without shipping new code, which is what *unknown-unknowns* require: "why is checkout slow only for one payment provider since the 14:05 deploy?". Observability does not replace monitoring; monitoring is one of the activities that observability data makes possible.

| Aspect | Monitoring | Observability |
|---|---|---|
| Core question | Is the system healthy? | Why is it behaving this way? |
| Problem class | Known-unknowns (predicted failure modes) | Unknown-unknowns (novel, emergent failures) |
| Approach | Predefined dashboards, thresholds, health checks | Ad-hoc exploration and correlation of telemetry |
| Typical data | Aggregated metrics, uptime probes | Metrics, logs and traces sharing context (IDs, attributes) |
| Output | Alerts and status views | Root cause and understanding |
| Best fit | Stable systems with well-understood failures | Distributed, frequently changing systems |

## 2. The Three Pillars

Metrics, logs and traces are the three core telemetry signals (OpenTelemetry is adding profiles as a newer, fourth signal). Each has a different data shape, cost profile and set of questions it answers well.

### 2.1 Metrics

- **What it means:** numeric measurements sampled or aggregated over time. Metrics are compact and cheap to store, which makes them the basis for dashboards and alerting.
- **Data shape:** metric name + labels (key/value pairs) + timestamp + numeric value. Every unique combination of name and labels is a separate *time series*. Prometheus scrapes (pulls) a plain-text `/metrics` endpoint and records the timestamp at scrape time.

```text
# TYPE http_requests_total counter
http_requests_total{method="GET",route="/api/orders",status="200"} 10432
http_requests_total{method="GET",route="/api/orders",status="500"} 17
```

| Prometheus type | Behaviour | Example | Typical PromQL |
|---|---|---|---|
| Counter | Only increases; resets to 0 when the process restarts | `http_requests_total` | `rate()`, `increase()` |
| Gauge | Goes up and down | `node_memory_MemAvailable_bytes`, queue depth | Raw value, `avg_over_time()` |
| Histogram | Counts observations into buckets; exposes `_bucket{le="..."}`, `_sum`, `_count` | `http_request_duration_seconds` | `histogram_quantile()`; can be aggregated across instances |
| Summary | Quantiles computed in the client, plus `_sum` and `_count` | `rpc_duration_seconds{quantile="0.99"}` | Quantiles cannot be aggregated across instances |

- **Questions it answers:** How many? How fast? How full? Is it getting worse? Has a threshold been crossed?
- **Cost and cardinality:** after compression a sample costs only one to two bytes, so cost is driven by the number of active series. The series count is roughly the product of the number of distinct values of each label, so unbounded values (user ID, request ID, email, raw URL) must never be labels. Those belong in logs or trace attributes.
- **Example (PromQL):**

```promql
# Per-second rate of 5xx responses per service, averaged over the last 5 minutes
sum by (service) (rate(http_requests_total{status=~"5.."}[5m]))
# 99th percentile latency computed from a histogram
histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))
```

### 2.2 Logs

- **What it means:** timestamped records of discrete events (a request served, an exception thrown, a login) emitted by applications, the operating system and infrastructure.
- **Data shape:** plain-text logs are easy for humans to read but need fragile regex parsing. Structured logs (usually one JSON object per line) carry named fields that a backend can filter and aggregate without parsing, including a `trace_id` for correlation. The same event in both forms:

```text
2026-10-07 14:05:12 ERROR payment failed for order 8812 after 3 retries
{"ts":"2026-10-07T14:05:12.481Z","level":"error","service":"checkout","msg":"payment failed","order_id":"8812","retries":3,"status":502,"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7"}
```

- **Questions it answers:** What exactly happened, in what order, with which error message or stack trace? Logs also support audit and security investigations.
- **Cost and cardinality:** logs are usually the largest and most expensive signal; cost follows ingestion volume, indexing and retention. Full-text indexing (Elasticsearch/OpenSearch) is fast to search but expensive. Loki indexes only a small set of labels and scans log content at query time, which is cheaper but requires low-cardinality labels. Cost is controlled with log levels, dropping noisy lines (health checks), sampling debug output and tiered retention. Secrets and personal data should never be logged.
- **Example (LogQL for Loki):** error lines with an HTTP 5xx status from the checkout app.

```logql
{namespace="shop", app="checkout"} | json | level="error" and status >= 500
```

### 2.3 Traces

- **What it means:** a distributed trace records the end-to-end path of one request across services. A trace is a tree of **spans**; each span is one unit of work (an HTTP handler, a database query, a call to another service).
- **Data shape:** every span has a `trace_id` (16 bytes, shared by all spans of the trace), its own `span_id` (8 bytes), a `parent_span_id` (empty for the root span), a name, start and end timestamps, attributes (such as `http.route`), events and a status. To keep the tree connected across process boundaries, each caller passes its context to the callee. This **context propagation** is standardised by the W3C Trace Context `traceparent` header (a companion `tracestate` header carries vendor-specific data, and the separate W3C `baggage` header carries application key/value pairs):

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             |  |                                |                |
             |  |                                |                +-- trace-flags: 01 = sampled
             |  |                                +-- parent-id: span-id of the calling span (16 hex)
             |  +-- trace-id: shared by every span in the trace (32 hex)
             +-- version: 00
```

- **Example (span waterfall for one illustrative request):** indentation shows parent/child relationships; all spans share the same trace-id.

```text
Span (service)                    0ms       100       200       300       400
                                  |---------|---------|---------|---------|
GET /checkout (api-gateway)       [=======================================]  412 ms
  POST /orders (order-svc)         [======================================]  395 ms
    SELECT orders (postgres)        [==]                                      38 ms
    POST /charge (payment-svc)           [============================]      301 ms
      POST /v1/charges (psp-api)          [==========================]       280 ms  <- slowest span
    PUBLISH order.created (kafka)                                       [=]    9 ms
```

- **Questions it answers:** Where did the time go? Which hop failed? What does the real call graph look like?
- **Cost and cardinality:** one request can produce dozens of spans, so keeping every trace is expensive. **Head sampling** decides at the root span (for example, keep 10%); it is cheap but can discard the interesting traces. **Tail sampling** decides after the trace completes (for example, keep all errors and anything slower than 1 s); it needs buffering, typically in the OpenTelemetry Collector. Span attributes tolerate high-cardinality values (user ID, order ID) far better than metric labels.

## 3. How the Pillars Connect

Each pillar alone is incomplete: metrics show that *something* is wrong, traces show *where*, and logs show *why*. Correlating them is what makes a system observable.

- **Exemplars:** a metric sample (usually a histogram bucket) annotated with the `trace_id` of one real request behind it. In Grafana, clicking a latency spike opens that exact trace in Tempo or Jaeger. Applications expose exemplars in the OpenMetrics format (first line below), and Prometheus stores them when exemplar storage is enabled.
- **Trace IDs in logs:** writing `trace_id` and `span_id` into every log line (OpenTelemetry SDKs and log bridges do this automatically) allows jumping from a span to its logs and back, for example with Loki derived fields and Tempo's trace-to-logs links in Grafana.
- **Shared resource attributes:** the same `service.name`, `k8s.namespace.name` and `k8s.pod.name` on every signal (OpenTelemetry semantic conventions) let an engineer pivot between signals for the same workload.

```text
http_request_duration_seconds_bucket{le="0.5"} 2048 # {trace_id="4bf92f3577b34da6a3ce929d0e0e4736"} 0.43

ALERT   checkout error ratio > 2% for 10m                      metrics: something is wrong
  |  exemplar trace_id
  v
TRACE   payment-svc -> psp-api span, 280 ms, status=ERROR      traces:  where
  |  trace_id in log lines
  v
LOGS    "upstream timeout calling psp-api after 3 retries"     logs:    why
```

**Methods for deciding what to measure** (the four golden signals are defined below the table):

| Method | Signals | Applies to | Origin |
|---|---|---|---|
| RED | Rate, Errors, Duration | Request-driven services (APIs, microservices) | Tom Wilkie |
| USE | Utilization, Saturation, Errors | Resources (CPU, memory, disk, network, connection pools) | Brendan Gregg |
| Four golden signals | Latency, Traffic, Errors, Saturation | User-facing systems | Google SRE book, ch. 6 |

- **Latency:** time taken to serve a request. Track successful and failed requests separately, because fast errors can hide slow successes.
- **Traffic:** demand on the system, such as HTTP requests per second.
- **Errors:** rate of failed requests, whether explicit (HTTP 5xx), implicit (HTTP 200 with wrong content) or by policy (slower than the agreed limit).
- **Saturation:** how "full" the service is, measured on its most constrained resource (CPU throttling, memory, queue depth, connection pool usage).

## 4. Why Observability Is Required

- **Microservices:** one user request may cross an API gateway, several services, a message queue and a database. No single host or log file holds the whole story.
- **Distributed failure modes:** partial failures (one replica or one zone), cascading failures and retry storms, timeouts, network partitions, noisy neighbours, version skew during rolling updates, and short-lived pods whose logs disappear with them. Many of these failures are novel, so dashboards built in advance cannot cover them all.
- **MTTD and MTTR:** *mean time to detect* and *mean time to recover/resolve* (the exact meaning of "R" varies between organisations) are the key incident metrics. SLO-based alerting shortens detection; correlated telemetry shortens diagnosis, which is usually the largest part of MTTR.

```text
incident starts        detected             diagnosed            recovered
      |------ MTTD -------|                                          |
      |------------------------------ MTTR --------------------------|
```

### SLIs, SLOs and error budgets

| Term | Meaning | Example |
|---|---|---|
| SLI (indicator) | Measured ratio of good events to valid events | Share of requests that return non-5xx in under 300 ms |
| SLO (objective) | Target for an SLI over a time window | 99.9% of requests are good over a rolling 30 days |
| SLA (agreement) | Contract with customers, with penalties; usually looser than the SLO | 99.5% monthly, otherwise service credits are paid |
| Error budget | `1 - SLO`: the unreliability allowed in the window | 0.1% of requests (or minutes) |

**Worked example: 99.9% monthly availability**

```text
SLO                = 99.9%
Error budget       = 1 - 0.999 = 0.001 (0.1%)
Average month      = 365.25 days / 12 = 30.44 days = 43,830 minutes
Allowed downtime   = 43,830 min x 0.001 = ~43.8 minutes per month
Fixed 30-day month = 43,200 min x 0.001 = 43.2 minutes
Request-based view = 10,000,000 requests x 0.001 = 10,000 failed requests allowed
```

On the same average month, 99% allows about 7 h 18 min, 99.5% about 3 h 39 min, 99.95% about 21.9 min and 99.99% about 4.4 min. While budget remains, teams can ship faster and accept risk; once it is spent, an error budget policy typically freezes risky releases and prioritises reliability work. Alerts should be based on the **burn rate** (how fast the budget is consumed) rather than raw thresholds. A burn rate of 14.4 sustained for one hour consumes 2% of a 30-day budget, which is the fast-burn threshold suggested in the Google SRE Workbook (paired with a 5-minute window to confirm the problem is still happening).

## 5. Common Tools

| Pillar / role | Tool | Purpose and notes |
|---|---|---|
| Metrics | **Prometheus** | Pull-based collection, time-series database, PromQL, rule evaluation. CNCF graduated. Prometheus 3.x can also receive OTLP. |
| Metrics at scale | **Thanos**, **Grafana Mimir** | Long-term, horizontally scalable storage and a global query view across many Prometheus servers, backed by object storage. |
| Alerting | **Alertmanager** | Receives alerts from Prometheus; deduplicates, groups and routes them (Slack, PagerDuty, email); supports silences and inhibition. |
| Visualisation | **Grafana** | Dashboards and Explore across all pillars (Prometheus, Loki, Tempo, Jaeger, Elasticsearch, CloudWatch, and more); has its own alerting too. |
| Logs | **Loki** | Log store that indexes labels only; LogQL; object storage. Cheaper at scale than full-text indexing. |
| Logs | **Elasticsearch / OpenSearch** + **Kibana / OpenSearch Dashboards** | Full-text indexed search and analytics. ELK = Elasticsearch, Logstash, Kibana; EFK replaces Logstash with Fluentd or Fluent Bit. OpenSearch is the Apache-2.0 fork created in 2021. |
| Log shipping | **Fluent Bit**, **Fluentd** | Collect, parse, enrich and forward logs. Fluent Bit (C, small footprint) is the usual node DaemonSet; Fluentd (Ruby, large plugin ecosystem) is often used as an aggregator. |
| Log shipping | **Promtail**, **Grafana Alloy** | Promtail, the original Loki agent, is **deprecated** (LTS from February 2025, end-of-life March 2026). Its replacement is Grafana Alloy, Grafana's OpenTelemetry Collector distribution, which also replaces Grafana Agent and handles metrics, logs, traces and profiles. |
| Traces | **Jaeger** | CNCF graduated tracing backend and UI. Jaeger v2 is built on the OpenTelemetry Collector and ingests OTLP natively; the old Jaeger client libraries are retired in favour of OpenTelemetry SDKs. |
| Traces | **Grafana Tempo** | Cost-efficient trace store on object storage; TraceQL query language; integrates with Loki and Prometheus exemplars. |
| Traces | **Zipkin** | One of the first open-source tracers (based on Google's Dapper paper); B3 propagation headers; mostly found in older stacks. |
| All pillars (standard) | **OpenTelemetry** | CNCF vendor-neutral standard: APIs, SDKs, semantic conventions, the OTLP protocol, and the **Collector** (receivers -> processors -> exporters). Instrument once, send to any backend. |
| Managed | **Amazon CloudWatch** | AWS-native metrics, logs and alarms; tracing through AWS X-Ray; Container Insights for EKS. |
| Managed | **Datadog**, **New Relic** | SaaS platforms covering all pillars plus APM and real-user monitoring; priced by hosts, ingested data and users. Managed options remove the work of running backends but cost more at volume and risk lock-in; OTLP support keeps switching possible. |

## 6. Kubernetes Observability

### 6.1 What to observe at each layer

| Layer | What to observe | Main source |
|---|---|---|
| Cluster / control plane | API server request rate, latency and errors; etcd health; pending pods; requested vs allocatable capacity | API server and etcd `/metrics`, kube-state-metrics |
| Node | CPU, memory, disk, filesystem, network; conditions `Ready`, `MemoryPressure`, `DiskPressure`, `PIDPressure` | node-exporter, kubelet |
| Pod | Phase, readiness, restarts, `OOMKilled`, scheduling failures, evictions | kube-state-metrics, Events |
| Container | CPU vs requests/limits, CPU throttling, memory working set vs limit | cAdvisor (inside the kubelet) |
| Application | RED metrics, business metrics, logs, traces | App `/metrics`, OpenTelemetry SDK, stdout/stderr |

### 6.2 metrics-server vs Prometheus

| | metrics-server | Prometheus |
|---|---|---|
| Purpose | Serves the Resource Metrics API (`metrics.k8s.io`) | General-purpose monitoring and alerting |
| Data | CPU and memory only; latest values, held in memory | Any metric, with history in a time-series database |
| Consumers | HPA, VPA, `kubectl top` | Grafana, Alertmanager, engineers |
| Queries and alerts | None | PromQL, recording and alerting rules |

The metrics-server project states that it is meant only for autoscaling and should not be used as a source for monitoring solutions. Autoscaling on custom metrics is done with prometheus-adapter or KEDA on top of Prometheus.

### 6.3 kube-state-metrics vs node-exporter vs cAdvisor

| Component | Runs as | Answers | Example metrics |
|---|---|---|---|
| kube-state-metrics | Deployment that watches the API server | What state are Kubernetes *objects* in (desired vs actual)? No resource usage. | `kube_deployment_status_replicas_available`, `kube_pod_container_status_restarts_total`, `kube_pod_status_phase` |
| node-exporter | DaemonSet with host access | How is the *machine* doing? | `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes`, `node_filesystem_avail_bytes` |
| cAdvisor | Built into the kubelet; scraped at `/metrics/cadvisor` | How much does each *container* use? | `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `container_cpu_cfs_throttled_periods_total` |

### 6.4 kube-prometheus-stack and the Prometheus Operator

`kube-prometheus-stack` is a community Helm chart that installs the Prometheus Operator, Prometheus, Alertmanager, Grafana, node-exporter and kube-state-metrics, together with default alerting rules and dashboards for the cluster:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
```

The Operator replaces hand-edited `prometheus.yml` files with custom resources in the `monitoring.coreos.com` API group (others include `AlertmanagerConfig`, `Probe` and `ScrapeConfig`):

| CRD | Purpose |
|---|---|
| `Prometheus`, `Alertmanager` | Declare the servers; the Operator runs them as StatefulSets |
| `ServiceMonitor` | Scrape the endpoints behind Services that match a label selector |
| `PodMonitor` | Scrape pods directly, without a Service |
| `PrometheusRule` | Recording and alerting rules, loaded into Prometheus automatically |

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: checkout
  namespace: shop
  labels:
    release: monitoring        # chart default: Prometheus selects monitors carrying its release label
spec:
  selector:
    matchLabels:
      app: checkout            # Services with this label are scraped
  endpoints:
    - port: http-metrics       # named port on the Service
      path: /metrics
      interval: 30s
```

### 6.5 Logs and events

Containers should log to stdout/stderr. The container runtime writes these streams to files on the node under `/var/log/pods/` (symlinked from `/var/log/containers/`), and the kubelet rotates them.

```bash
kubectl logs deploy/checkout -n shop --since=1h               # one pod of the Deployment
kubectl logs checkout-6f7c9d8b5-x2k4p -n shop --previous      # the instance before the last restart
kubectl get events -n shop --sort-by=.metadata.creationTimestamp
```

These commands are useful for debugging a single pod but are not a logging solution. Logs are lost when a pod is deleted or evicted or a node fails, only the current and the previous container instance are kept, rotation caps the size, there is no search across pods, and Events are retained for only one hour by default (the API server's `--event-ttl`). The standard answer is a **node-level logging agent** run as a **DaemonSet** (Fluent Bit, Grafana Alloy or the OpenTelemetry Collector) that tails `/var/log/pods` on every node, adds Kubernetes metadata (namespace, pod, labels) and ships the logs to a central backend. Event exporters do the same for Events.

### 6.6 Probes as health signals

| Probe | Question it asks | Action on failure |
|---|---|---|
| `startupProbe` | Has the application finished starting? | Other probes wait; the container is restarted if it never succeeds |
| `livenessProbe` | Is the process alive, or stuck? | The kubelet restarts the container |
| `readinessProbe` | Can it serve traffic right now? | The pod is removed from Service endpoints (no restart) |

Probe failures surface as `Unhealthy` Events, restart counts and the `kube_pod_status_ready` metric, so they double as alerting signals. Liveness probes should not check downstream dependencies; otherwise a database outage becomes a cluster-wide restart loop.

### 6.7 A typical in-cluster observability stack

```text
 SOURCES                      COLLECTION                 BACKEND                    UI
 app pods (/metrics)       -+
 kubelet + cAdvisor        -+-> Prometheus             -> TSDB (+ Thanos/Mimir   --+
 node-exporter (DaemonSet) -+   targets selected by       for long-term storage)   |
 kube-state-metrics        -+   ServiceMonitor/PodMonitor                          |
                                    | rules from PrometheusRule                    |
                                    v                                              |
                                Alertmanager -> Slack / PagerDuty / email          |
                                                                                   +-> Grafana
 container stdout/stderr   ---> log agent DaemonSet    -> Loki (or Elasticsearch --+
 (/var/log/pods on node)        (Fluent Bit / Alloy)      / OpenSearch)            |
                                                                                   |
 app OpenTelemetry SDK     ---> OTel Collector         -> Tempo / Jaeger         --+
 (OTLP spans)                   (DaemonSet or gateway)

 kubelet resource metrics  ---> metrics-server -> metrics.k8s.io -> HPA, VPA, kubectl top
                                (latest values only; not part of the monitoring path)
```

## 7. Key Takeaways

- Monitoring answers questions known in advance; observability makes it possible to investigate failures nobody predicted.
- Metrics are cheap and alertable but must stay low-cardinality; logs hold the detail and dominate cost; traces show the path and timing of a request across services.
- Correlation (exemplars, trace IDs in logs, shared resource attributes) turns three data sets into one workflow: alert, then trace, then logs.
- RED suits services, USE suits resources, and the four golden signals suit user-facing systems. Alerts work best on SLO burn rate rather than raw thresholds.
- A 99.9% monthly SLO leaves about 43.8 minutes of error budget.
- OpenTelemetry is the vendor-neutral instrumentation standard; Grafana Alloy replaces the deprecated Promtail.
- In Kubernetes, metrics-server exists for autoscaling only. Monitoring comes from Prometheus with kube-state-metrics, node-exporter and cAdvisor, and durable logs need a node-level DaemonSet agent.

## 8. References

- Prometheus: <https://prometheus.io/docs/introduction/overview/>, <https://prometheus.io/docs/concepts/metric_types/>, <https://prometheus.io/docs/practices/histograms/>
- OpenTelemetry signals and Collector: <https://opentelemetry.io/docs/concepts/signals/>, <https://opentelemetry.io/docs/collector/>
- W3C Trace Context: <https://www.w3.org/TR/trace-context/>
- Grafana Loki, Tempo and Alloy: <https://grafana.com/docs/loki/latest/>, <https://grafana.com/docs/tempo/latest/>, <https://grafana.com/docs/alloy/latest/>
- Promtail deprecation notice: <https://grafana.com/docs/loki/latest/send-data/promtail/>
- Jaeger: <https://www.jaegertracing.io/docs/>
- Kubernetes logging, resource metrics pipeline and probes: <https://kubernetes.io/docs/concepts/cluster-administration/logging/>, <https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/>, <https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/>
- metrics-server: <https://github.com/kubernetes-sigs/metrics-server>
- Prometheus Operator and kube-prometheus-stack: <https://prometheus-operator.dev/>, <https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack>
- Google SRE book and workbook: <https://sre.google/sre-book/monitoring-distributed-systems/>, <https://sre.google/workbook/alerting-on-slos/>
- The USE Method: <https://www.brendangregg.com/usemethod.html>
