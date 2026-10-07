# Session 14 — Kubernetes Troubleshooting

**Name:** Prince Kumar  ·  **Roll No:** 24bcs10658

The question this session answers: *"My Kubernetes application is not working. How do I find
out why?"* Everything below was broken on purpose, investigated and fixed on my laptop's kind
cluster (`devops-lab`, Kubernetes v1.37.0). Every screenshot is rendered from a raw transcript
in [`utility/transcripts/session-14/`](../utility/transcripts/session-14/).

| Task | Folder | Content |
|---|---|---|
| 1 — Commands | [`01-kubectl-commands/`](01-kubectl-commands/) | `get`, `get -o wide`, `describe`, `logs`, `exec`, `events`, `explain`, `top` on a two-container demo app |
| 2 — Common issues | [`02-common-issues/`](02-common-issues/) | CrashLoopBackOff, ErrImagePull/ImagePullBackOff, Pending, ContainerCreating, Service connectivity, DNS, Pod networking (bind address + NetworkPolicy), configuration (CreateContainerConfigError), OOMKilled. Each with a broken + fixed manifest and before/after screenshots |
| 3 — Mini project | [`03-mini-project/`](03-mini-project/) | the course troubleshooting challenge: Q1–Q5, selector challenge, troubleshooting table, the 10 README questions |

Shared files: [`namespace.yaml`](namespace.yaml) (`session14`) and
[`client-pod.yaml`](client-pod.yaml), a long-lived busybox toolbox used for in-cluster tests.
`kubectl exec` into it is more reliable than `kubectl run -i`, which can lose the output of
very short commands.

## The method

```text
1. Observe         kubectl get pods -o wide          what state? which node? restarts?
2. Details         kubectl describe pod <p>          state, last state, exit code, conditions
3. Events          kubectl events --for pod/<p>      what Kubernetes tried, what failed
4. Logs            kubectl logs <p> [-c] [--previous] what the app says
5. Inside          kubectl exec <p> -- sh -c '...'   env, files, ports (netstat), DNS
6. Connectivity    endpointslices, labels, ports, nslookup, NetworkPolicy
7. Root cause  →  8. Fix (in the YAML, in Git)  →  9. Verify with the same command that showed the problem
```

## Issue summary

| Issue | Status | Root cause | Fix |
|---|---|---|---|
| CrashLoopBackOff | `Error` / `CrashLoopBackOff`, exit 1 | `DATABASE_URL` not set | ConfigMap + `envFrom` |
| ErrImagePull / ImagePullBackOff | `ErrImagePull` ⇄ `ImagePullBackOff` | non-existent tag; misspelt repository | real image references |
| Pending | `Pending`, `FailedScheduling` | 64 CPU / 256 Gi requested; nodeSelector without matching node | right-sized requests; matching node label |
| ContainerCreating | stuck, `FailedMount` | ConfigMap volume missing | create ConfigMap; kubelet recovers by itself |
| Service connectivity | `Connection refused` | selector typo + targetPort 8080 vs 80 | correct selector and targetPort |
| DNS | `NXDOMAIN` | short name across namespaces | FQDN; recreate Pod (env read only at start) |
| Pod networking | refused / timed out | app bound to `127.0.0.1`; default-deny NetworkPolicy | bind `0.0.0.0` + readiness probe; narrow allow policy |
| Configuration | `CreateContainerConfigError` | wrong ConfigMap key; Secret missing | right key; Secret created with kubectl, not committed |
| OOMKilled | `OOMKilled`, exit 137 | 32Mi limit for a ~200 MB job | limit sized to the workload |

## Deliverables checklist

| Deliverable | Where |
|---|---|
| Commands | [`01-kubectl-commands/README.md`](01-kubectl-commands/README.md) and every case in Task 2 |
| Problem statement / investigation / root cause / solution | each section of [`02-common-issues/README.md`](02-common-issues/README.md) |
| Before/after output | paired "broken" and "fixed" screenshots per issue |
| Screenshots | [`utility/screenshots/session-14/`](../utility/screenshots/session-14/) |
| Mini project | [`03-mini-project/README.md`](03-mini-project/README.md) |
