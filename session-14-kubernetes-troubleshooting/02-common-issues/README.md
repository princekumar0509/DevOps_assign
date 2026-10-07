# 02 — Troubleshooting Common Issues

Each folder holds a deliberately broken manifest and its fix. Every case follows the same
six steps: **identify → investigate → root cause → fix → verify → document**. All of them ran
in the `session14` namespace (the DNS case also uses `storefront`). The "before" and "after"
screenshots are separate transcripts.

| # | Issue | Status seen | Root cause | Command that found it |
|---|---|---|---|---|
| 1 | [CrashLoopBackOff](#1-crashloopbackoff) | `Error` → `CrashLoopBackOff` | required env var missing → exit 1 | `kubectl logs` |
| 2 | [ErrImagePull / ImagePullBackOff](#2-errimagepull--imagepullbackoff) | `ErrImagePull` ⇄ `ImagePullBackOff` | tag does not exist; repository misspelt | `kubectl describe pod` events |
| 3 | [Pending](#3-pending) | `Pending`, no node | requests > node capacity; nodeSelector matches no node | `describe pod` → `FailedScheduling` |
| 4 | [ContainerCreating](#4-containercreating) | stuck `ContainerCreating` | mounted ConfigMap does not exist | `describe pod` → `FailedMount` |
| 5 | [Service connectivity](#5-service-connectivity) | Pods fine, Service refuses | selector typo **and** wrong targetPort | `get endpointslice`, `--show-labels`, `netstat` |
| 6 | [DNS](#6-dns) | `NXDOMAIN` | short name used across namespaces | `nslookup`, `/etc/resolv.conf` |
| 7a | [Pod networking (bind)](#7a-pod-networking--app-bound-to-127001) | Pod `Running`, peers refused | app listens on `127.0.0.1` | `netstat -tln` inside the Pod |
| 7b | [Pod networking (policy)](#7b-pod-networking--networkpolicy) | requests time out | default-deny NetworkPolicy | `get/describe networkpolicy` |
| 8 | [Configuration](#8-configuration-issues) | `CreateContainerConfigError` | wrong ConfigMap key; missing Secret | `describe pod` events |
| 9 | [OOMKilled](#9-bonus--oomkilled) | `OOMKilled`, exit 137 | memory limit below real usage | `describe pod` Last State |

---

## 1. CrashLoopBackOff

[`01-crashloopbackoff/`](01-crashloopbackoff/): `orders-worker` exits unless `DATABASE_URL` is set.

![CrashLoopBackOff: the watch shows Running, Error, CrashLoopBackOff with growing back-off; logs show FATAL DATABASE_URL missing; describe shows exit code 1, restart count 3, Environment none](../../utility/screenshots/session-14/10_crashloop_broken.png)

- **Identify:** `--watch` shows the cycle `Running → Error → CrashLoopBackOff` with the gaps
  growing (10 s, 20 s, 40 s ...). That is the kubelet's exponential back-off, capped at 5 min.
- **Investigate:** `describe` → `Last State: Terminated, Reason: Error, Exit Code: 1`,
  `Environment: <none>`, event `Back-off restarting failed container`.
- **Root cause:** `kubectl logs` → `[FATAL] DATABASE_URL environment variable is missing`.
  The app exits on purpose. Kubernetes keeps restarting it because `restartPolicy` is `Always`.
- Note: `--previous` failed with "unable to retrieve container logs". The pod was *in* `Error`,
  so the current container was already the dead one, and the kubelet had already
  garbage-collected the one before it. Plain `kubectl logs` showed the crash output.
- **Fix:** [`fixed.yaml`](01-crashloopbackoff/fixed.yaml) adds a ConfigMap and `envFrom`.

![Fixed: diff adds the ConfigMap and envFrom, pod is Running 1/1 with zero restarts and logs show orders-worker started](../../utility/screenshots/session-14/11_crashloop_fixed.png)

- **Verify:** `1/1 Running`, 0 restarts, log line `orders-worker started, using postgresql://...`.

## 2. ErrImagePull / ImagePullBackOff

[`02-imagepullbackoff/`](02-imagepullbackoff/): `catalog-web` uses tag
`1.27-alpine-doesnotexist`; `catalog-cache` uses repository `princekumar/redis-typo`.

![Both pods alternate between ErrImagePull and ImagePullBackOff; events show NotFound failed to resolve reference docker.io/library/nginx:1.27-alpine-doesnotexist not found](../../utility/screenshots/session-14/12_imagepull_broken.png)

- **ErrImagePull** is one failed pull attempt; **ImagePullBackOff** is the kubelet waiting
  before the next attempt. The watch shows them alternating.
- **Root cause** from the events: `code = NotFound ... failed to resolve reference
  "docker.io/library/nginx:1.27-alpine-doesnotexist": not found`. The registry was reached,
  but the tag or repository does not exist. (Other causes look different: `401 Unauthorized` /
  `pull access denied` for a private image without `imagePullSecrets`,
  `429 Too Many Requests` for rate limiting, which hit me in Session 13, and
  `dial tcp ... i/o timeout` for network/DNS problems.)
- **Fix:** real tag `nginx:1.27-alpine` and the official `redis:7-alpine`.

![Fixed: diff of image lines, both pods Running and redis-cli ping returns PONG](../../utility/screenshots/session-14/13_imagepull_fixed.png)

## 3. Pending

[`03-pending/`](03-pending/): `report-generator` requests 64 CPUs and 256 Gi;
`gpu-trainer` has `nodeSelector: accelerator=nvidia-a100`.

![Both pods Pending with no node; FailedScheduling Insufficient cpu, Insufficient memory and didn't match Pod's node affinity/selector; node allocatable is 12 CPU and about 3.2Gi; node labels have no accelerator](../../utility/screenshots/session-14/14_pending_broken.png)

- `Pending` with `NODE <none>` means the **scheduler** could not place the Pod. Nothing on
  the node has happened yet.
- `FailedScheduling: 0/1 nodes are available: 1 Insufficient cpu, 1 Insufficient memory`.
  The node's **Allocatable** is 12 CPU / ~3.2 Gi.
- `FailedScheduling: ... didn't match Pod's node affinity/selector`. The node has no
  `accelerator` label.
- **Fix:** right-size the requests (100m / 64Mi). Pod resources cannot be edited in place
  here, so the Pod is recreated. For the selector, the real-world fix is to add a matching
  node (a GPU node pool). To simulate that, the node was labelled
  `accelerator=nvidia-a100`, and the label was removed again afterwards.

![Fixed: report-generator recreated with small requests, node labelled, both pods Running; gpu-trainer events show FailedScheduling then Scheduled without recreating the pod](../../utility/screenshots/session-14/15_pending_fixed.png)

- **Verify:** both `Running`. `gpu-trainer` was **not** recreated: the scheduler retries
  Pending Pods and placed it one second after a matching node appeared
  (`FailedScheduling` → `Scheduled`).

## 4. ContainerCreating

[`04-containercreating/`](04-containercreating/): `pricing-api` mounts ConfigMap
`pricing-settings`, which does not exist.

![Pod stuck in ContainerCreating; events show FailedMount MountVolume.SetUp failed for volume settings configmap pricing-settings not found; the configmap get returns NotFound](../../utility/screenshots/session-14/16_containercreating_broken.png)

- `ContainerCreating` for more than a few seconds means the kubelet is stuck *before* starting
  the container: usually volumes (missing ConfigMap/Secret, PVC not bound, CSI attach
  failure), image pulls, or CNI not ready.
- Events: `FailedMount ... configmap "pricing-settings" not found`.
- **Fix:** create the ConfigMap ([`fix-configmap.yaml`](04-containercreating/fix-configmap.yaml)).

![After applying the configmap the pod becomes Ready by itself, the files currency and tax-rate are mounted with INR and 0.18](../../utility/screenshots/session-14/17_containercreating_fixed.png)

- **Verify:** the Pod became `1/1 Running` **without being recreated**. The kubelet retries
  mounts. `/etc/pricing/currency` = `INR`, `/etc/pricing/tax-rate` = `0.18`.

## 5. Service connectivity

[`05-service-connectivity/`](05-service-connectivity/): the `payments` Pods are healthy,
but [`broken-service.yaml`](05-service-connectivity/broken-service.yaml) has **two** bugs.

![Connection refused through the service; the endpoint slice has no endpoints; pods are labelled app=payments while the service selects app=payment](../../utility/screenshots/session-14/18_service_broken.png)

1. `wget http://payments-svc` → `Connection refused`. A Service with **no endpoints** gets
   rejected by kube-proxy.
2. `get endpointslice` → `ENDPOINTS <unset>`. `get pods --show-labels` shows `app=payments`;
   `-l app=payment` finds nothing; `describe svc` → `Selector: app=payment`. **Root cause 1:**
   selector typo.

![After fixing the selector the endpoints appear on port 8080 but connections are still refused; direct pod IP on 8080 refused, on 80 works; netstat shows nginx on port 80](../../utility/screenshots/session-14/19_service_fix_selector.png)

3. After patching the selector the endpoints appear, **but on port 8080**, and requests are
   still refused. Testing the Pod IP directly: `:8080` refused, `:80` works. `netstat -tln`
   inside the Pod: nginx listens on **80**. **Root cause 2:** `targetPort: 8080`.

![Fixed service: selector app=payments, targetPort 80, endpoints on port 80, the page loads and four requests return HTTP 200 OK](../../utility/screenshots/session-14/20_service_fixed.png)

- **Verify:** `Endpoints: 10.244.0.78:80,10.244.0.79:80`, page loads, 4/4 `HTTP/1.1 200 OK`
  through the FQDN.
- Lesson: fixing the first bug changed the symptom only a little (still `refused`). Re-check
  every layer after a fix.

## 6. DNS

[`06-dns/`](06-dns/): `inventory-svc` lives in `session14`; the `frontend` Pod in namespace
`storefront` calls `http://inventory-svc`.

![frontend logs inventory UNREACHABLE; nslookup inventory-svc returns NXDOMAIN for every search domain; resolv.conf search list starts with storefront.svc.cluster.local; the service exists in session14; CoreDNS pods running; full FQDN resolves](../../utility/screenshots/session-14/21_dns_broken.png)

- **Identify:** the frontend logs `inventory UNREACHABLE (http://inventory-svc)`.
- **Investigate:** `nslookup inventory-svc` → `NXDOMAIN` for
  `inventory-svc.storefront.svc.cluster.local`, `...svc.cluster.local`, `...cluster.local`.
  The resolver tries every `search` domain from `/etc/resolv.conf`, and the first one is the
  **Pod's own** namespace.
- `kubectl get svc -A` → the Service exists, but in `session14`.
- CoreDNS is healthy: both Pods `Running`, and `kubernetes.default.svc.cluster.local` resolves.
  (The two `plugin/ready: Plugins not ready` lines are old CoreDNS start-up messages from when
  Docker Desktop was restarted earlier, not part of this problem.)
- The fully-qualified name `inventory-svc.session14.svc.cluster.local` resolves.
- **Root cause:** a short Service name only resolves inside its own namespace.
- **Fix:** [`fixed-frontend-config.yaml`](06-dns/fixed-frontend-config.yaml) uses the FQDN.

![After updating the configmap the running pod still has the old value; after recreating the pod it has the FQDN and logs inventory OK](../../utility/screenshots/session-14/22_dns_fixed.png)

- Gotcha: after `kubectl apply` of the ConfigMap, the running Pod **still had the old value**.
  Environment variables from a ConfigMap are read only when the container starts. The Pod had
  to be recreated (with a Deployment: `kubectl rollout restart`). After that: `inventory OK`.

## 7a. Pod networking — app bound to 127.0.0.1

[`07-pod-networking/broken.yaml`](07-pod-networking/broken.yaml): `ledger` runs
`python3 -m http.server 8000 --bind 127.0.0.1`.

![Pod running but both the service and the pod IP refuse connections; inside the pod 127.0.0.1:8000 works; netstat shows 127.0.0.1:8000 LISTEN; the command has --bind 127.0.0.1](../../utility/screenshots/session-14/23_podnet_broken_1.png)
![the container command printed with --bind 127.0.0.1](../../utility/screenshots/session-14/23_podnet_broken_2.png)

- The Pod is `1/1 Running`, yet both the Service and the Pod IP give `Connection refused`.
- Inside the Pod, `wget http://127.0.0.1:8000` works. `netstat -tln` shows
  `127.0.0.1:8000 LISTEN`: the socket accepts loopback only. Traffic from other Pods arrives
  on the Pod's `eth0` IP and is refused.
- **Fix:** `--bind 0.0.0.0` ([`fixed.yaml`](07-pod-networking/fixed.yaml)), plus a
  `tcpSocket` readiness probe. The kubelet probes the Pod IP, so this mistake would now show
  as `0/1` instead of hiding behind `Running`.

![Fixed: netstat shows 0.0.0.0:8000, the service and the pod IP return HTTP 200 from SimpleHTTP](../../utility/screenshots/session-14/24_podnet_fixed.png)

- The first verification after the fix still got `refused`. The old Pods were still
  `Terminating`: Python as PID 1 ignores SIGTERM, so each waited the full 30 s grace period,
  and kube-proxy can fall back to terminating endpoints. The recorded run waits for the old
  ReplicaSet's Pods to be gone (`kubectl wait --for=delete`) before testing.

## 7b. Pod networking — NetworkPolicy

The cluster's CNI (kindnet) enforces NetworkPolicy, so this is a real block, not a simulation.

![After applying default-deny-ingress the request times out although the app listens; describe networkpolicy shows pod selector none and no allowed ingress](../../utility/screenshots/session-14/25_netpol_broken.png)

- Symptom differs from 7a: **`download timed out`**, not `refused`. Packets are dropped, not
  rejected. The app still listens on `0.0.0.0:8000`.
- `describe networkpolicy default-deny-ingress`: `PodSelector: <none>` (every Pod in the
  namespace), `Allowing ingress traffic: <none>`.
- **Fix:** keep default-deny and add a narrow allow rule
  ([`allow-client-networkpolicy.yaml`](07-pod-networking/allow-client-networkpolicy.yaml)):
  Pods labelled `role=client` may reach `app=ledger` on TCP 8000.

![Allow policy applied: client (role=client) gets HTTP 200, intruder (role=untrusted) still times out](../../utility/screenshots/session-14/26_netpol_fixed.png)

- **Verify:** `client` → `HTTP/1.0 200 OK`; `intruder` (`role=untrusted`) → still
  `timed out`. The policy is selective.

## 8. Configuration issues

[`08-configuration/broken.yaml`](08-configuration/broken.yaml): env refers to ConfigMap key
`LOG_LVL` (the key is `LOG_LEVEL`) and to Secret `db-credentials` (never created).

![Pod in CreateContainerConfigError; event couldn't find key LOG_LVL in ConfigMap; the configmap has LOG_LEVEL; the secret is NotFound](../../utility/screenshots/session-14/27_config_broken.png)

- `CreateContainerConfigError`: the kubelet cannot build the container's config (env/volumes).
- Event: `couldn't find key LOG_LVL in ConfigMap session14/billing-config`. Comparing the env
  references with the ConfigMap's actual keys shows the typo. `get secret db-credentials` →
  `NotFound`.
- Only the **first** error is reported. Fixing the key revealed the second:
  `secret "db-credentials" not found`.

![Fixed: key corrected, pod still blocked by the missing secret, secret created from literals with a random password, the pod starts by itself and logs show log level info, currency INR, db_user billing_app](../../utility/screenshots/session-14/28_config_fixed.png)

- The Secret was created with `kubectl create secret --from-literal` and a generated password,
  **not** committed as YAML. Secrets are only base64-encoded, so a committed Secret is a
  leaked Secret.
- **Verify:** Pod `1/1 Running`, log `log level=info currency=INR db_user=billing_app`.

## 9. Bonus — OOMKilled

[`09-oomkilled/`](09-oomkilled/): a job builds ~200 MB in memory with a 32Mi limit.

![OOMKilled repeatedly then CrashLoopBackOff; Last State Terminated Reason OOMKilled Exit Code 137; limit memory 32Mi](../../utility/screenshots/session-14/29_oom_broken.png)

- `OOMKilled`, `Exit Code: 137` (SIGKILL from the kernel's OOM killer, enforced by the
  container's memory cgroup at `limits.memory`).
- **Fix:** request 256Mi / limit 320Mi, sized to the job's real need. (Alternatively, process
  the data in smaller chunks.)

![Fixed: the job runs to Completed with exit code 0 and logs processed 20 chunks](../../utility/screenshots/session-14/30_oom_fixed.png)

---

## Patterns worth remembering

```text
Pending            → scheduler problem      → describe pod: FailedScheduling
ContainerCreating  → kubelet setup problem  → describe pod: FailedMount / image / CNI
CreateContainerConfigError → env/volume refs → describe pod: missing key / ConfigMap / Secret
ErrImagePull/ImagePullBackOff → registry    → describe pod: NotFound / 401 / 429 / timeout
CrashLoopBackOff   → the app exits          → logs (and --previous), exit code
OOMKilled (137)    → memory limit           → describe pod: Last State, top pods
Running but unreachable → Service/DNS/network → endpoints, labels, ports, netstat, nslookup, NetworkPolicy
```
