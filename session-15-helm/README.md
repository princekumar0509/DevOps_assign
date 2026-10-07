# Session 15 — Helm

**Name:** Prince Kumar  ·  **Roll No:** 24bcs10658

Helm v4.3.0 against the local kind cluster (`devops-lab`, Kubernetes v1.37.0). Every screenshot
is rendered from a raw transcript in
[`utility/transcripts/session-15/`](../utility/transcripts/session-15/).

| Task | Folder | Content |
|---|---|---|
| 1 — Helm commands | [`01-helm-commands/`](01-helm-commands/) | `create`, `lint`, `template`, `install`, `list`, `status`, `get`, `test`, `upgrade`, `history`, `rollback`, `uninstall` (+ `--keep-history`), `repo`, `search repo/hub`, `show` |
| 2 — Rollback workflow | [`02-helm-rollback/`](02-helm-rollback/) | own chart `release-demo` behind the ingress: install v1 → upgrade v2 → bad v3 marked `failed` while v2 keeps serving → rollback to 2 |
| 3 — Mini project | [`03-mini-project/`](03-mini-project/) | `notes-chart` with dev/prod values, NodePort 30090, bad upgrade, rollback, uninstall |

## Deliverables checklist

| Deliverable | Where |
|---|---|
| Helm chart | [`01-helm-commands/webapp/`](01-helm-commands/webapp/) (generated), [`02-helm-rollback/release-demo/`](02-helm-rollback/release-demo/), [`03-mini-project/notes-chart/`](03-mini-project/notes-chart/) |
| values.yaml | in each chart; plus [`values-prod.yaml`](03-mini-project/notes-chart/values-prod.yaml) |
| Templates | `templates/` of each chart: Deployment, Service, ConfigMap, Ingress, helpers, NOTES |
| Installation / Upgrade / Rollback | Task 2 and Task 3 READMEs, with screenshots |
| Screenshots | [`utility/screenshots/session-15/`](../utility/screenshots/session-15/) |
| README files | this file + one per task |
| Mini project | [`03-mini-project/`](03-mini-project/) |

## Helm 4 differences I ran into

The course material is written for Helm 3. With Helm 4.3:

- `helm list --all` → `unknown flag`. `helm list` now shows releases in every state.
- Releases are applied with **server-side apply** by default (`helm get metadata` →
  `APPLY_METHOD: server-side apply`).
- `--atomic` is now `--rollback-on-failure`.
- `helm create` also generates an `httproute.yaml` (Gateway API) next to `ingress.yaml`.

## Lessons

1. Use `--wait --timeout` on every upgrade. Otherwise "deployed" only means "the API server
   accepted the YAML".
2. Always pass the environment's values file (or `--reuse-values`) to `helm upgrade`. The
   course's bad-upgrade step silently turned production (3 replicas) back into the dev defaults
   (1 replica).
3. `helm rollback` never rewrites history. It deploys an old revision's manifests as a new
   revision.
