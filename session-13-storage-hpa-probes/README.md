# Session 13 — Kubernetes Storage, HPA & Probes

**Name:** Prince Kumar  ·  **Roll No:** 24bcs10658

All tasks were run on my laptop (`prince-kumar@VivoBook`, Ubuntu) against a local
**kind** cluster `devops-lab` (Kubernetes v1.37.0) with metrics-server and ingress-nginx;
see [`utility/cluster/`](../utility/cluster/). Every screenshot is rendered from the raw
terminal transcript in [`utility/transcripts/session-13/`](../utility/transcripts/session-13/).

| # | Task | Folder | Highlights |
|---|---|---|---|
| 1 | Kubernetes volumes | [`01-kubernetes-volumes/`](01-kubernetes-volumes/) | emptyDir, hostPath, static PV/PVC, StorageClass + dynamic provisioning, Retain vs Delete shown live |
| 2 | HPA hands-on | [`02-hpa/`](02-hpa/) | 1 → 3 → 5 replicas under load, `TooManyReplicas` cap, controlled scale-down 5 → 1; two failed attempts diagnosed |
| — | Probes | [`03-probes/`](03-probes/) | readiness gating Service traffic, liveness restart (exit 137), startup budget right vs too short |
| 3 | Mini project | [`04-mini-project/`](04-mini-project/) | PVC + probes + HPA together; data survives Pod deletion; 2 → 5 under ApacheBench; bonus challenges |

## Deliverables checklist

| Deliverable | Where |
|---|---|
| Volume documentation | [`01-kubernetes-volumes/README.md`](01-kubernetes-volumes/README.md) |
| HPA YAML | [`02-hpa/hpa.yml`](02-hpa/hpa.yml), [`04-mini-project/hpa.yaml`](04-mini-project/hpa.yaml) |
| Load generator | [`02-hpa/load-generator.yaml`](02-hpa/load-generator.yaml), [`04-mini-project/load-generator-ab.yaml`](04-mini-project/load-generator-ab.yaml) |
| HPA output | `kubectl get hpa / get pods / top pods / describe hpa` in [`02-hpa/README.md`](02-hpa/README.md) |
| Screenshots | [`utility/screenshots/session-13/`](../utility/screenshots/session-13/) (embedded in each README) |
| Mini-project implementation | [`04-mini-project/`](04-mini-project/) |
| README documentation | this file + one README per folder |

## Things that went wrong (and what they taught me)

1. **`ImagePullBackOff` → HPA `<unknown>`.** Docker Hub returned `429 Too Many Requests`
   because the anonymous pull quota for my network's shared IP was used up. Fixed by
   pulling through `mirror.gcr.io` (containerd `hosts.toml` + Docker `registry-mirrors`).
2. **nginx would not autoscale.** A static page costs almost no CPU, so the HPA (correctly)
   kept scaling *down* even with 8 load generators. CPU-based HPA only works when CPU tracks
   load. Switched the HPA demo to the CPU-bound `hpa-example` image.
3. **The mini project's busybox load generator peaked at 45 %.** Used ApacheBench with 50
   keep-alive connections to get realistic load.
4. **`kubectl get endpointslices` looked "wrong"** during the readiness demo: the IP stayed
   listed. EndpointSlices keep not-ready endpoints with `ready=false`, and only ready ones get
   traffic.
