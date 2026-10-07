# GitOps — Concepts

Study notes for Session 20 (Monitoring, Observability & GitOps). They cover the GitOps principles, Git as the source of truth, declarative configuration, continuous reconciliation, the end-to-end workflow, push vs pull delivery, Argo CD and Flux on Kubernetes, and handling secrets.

## 1. What Is GitOps?

GitOps is an operating model in which the desired state of infrastructure and applications is declared in version control, and software agents continuously make the running system match it. The term was coined by Weaveworks in 2017. The vendor-neutral definition is now maintained by **OpenGitOps**, a CNCF project that grew out of the GitOps Working Group. Its principles (v1.0.0) are:

| # | Principle | OpenGitOps wording | In practice |
|---|---|---|---|
| 1 | Declarative | "A system managed by GitOps must have its desired state expressed declaratively." | Kubernetes YAML, Helm values and Kustomize overlays describe *what*, not *how* |
| 2 | Versioned and immutable | "Desired state is stored in a way that enforces immutability, versioning and retains a complete version history." | Git commits (content-addressed SHAs), tags, signed commits |
| 3 | Pulled automatically | "Software agents automatically pull the desired state declarations from the source." | Argo CD or Flux in the cluster fetch from Git; nobody pushes to the cluster |
| 4 | Continuously reconciled | "Software agents continuously observe actual system state and attempt to apply the desired state." | A control loop detects and corrects drift |

The principles refer to a "source" rather than Git specifically. Git is by far the most common source, but OCI registries and object storage buckets are also used (Flux supports both). GitOps changes the *delivery* half of CI/CD: CI still builds and tests, while deploying becomes a commit.

## 2. Git as the Source of Truth

The config repository describes what should run in each environment, and the cluster is treated as a projection of it. Changes made directly with `kubectl edit` or `kubectl scale` bypass the benefits below, so they are reserved for break-glass situations (and self-heal usually reverts them). Git as the source of truth provides:

- **Audit trail:** every change is a commit with an author, timestamp, message and diff, so "who changed what, when and why" is answered by Git history (`git log -- <path>`, `git blame <file>`) rather than shell histories or pipeline logs. Signed commits add provenance, and Flux can verify signatures before applying.
- **Review before change:** changes arrive as pull requests with required reviewers, CODEOWNERS, branch protection and CI checks (YAML linting, schema validation with kubeconform, policy checks with Kyverno or Conftest). Production changes get the same four-eyes control as application code.
- **Rollback = `git revert`:** reverting the bad commit creates a new commit that restores the previous desired state, and the agent syncs it. History stays linear and the rollback is itself audited.
- **Disaster recovery:** a rebuilt cluster can be pointed at the same repository to recreate its workloads (persistent data and secret material still need their own backups).

## 3. Declarative Configuration

An **imperative** approach issues commands that describe *how* to reach a state. A **declarative** approach describes the desired *end state* and lets the tool compute and apply the difference.

| Aspect | Imperative | Declarative |
|---|---|---|
| Expresses | Steps to perform | Desired end state |
| kubectl examples | `kubectl run`, `kubectl create deployment`, `kubectl scale --replicas=5`, `kubectl set image`, `kubectl expose` | `kubectl apply -f` / `-k`, `kubectl diff` |
| Re-running | Depends on current state; may fail with `AlreadyExists` | Idempotent: applying the same manifest again changes nothing |
| Where intent lives | Shell history, runbooks | Files under version control |
| Drift | Invisible | Detectable by diffing desired vs live |
| GitOps fit | Not suitable | Required (principle 1) |

```yaml
# Declarative: committed to Git and applied with kubectl apply -f deployment.yaml.
# The imperative equivalent (kubectl create deployment + kubectl scale) leaves no record in Git.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 3
  selector:
    matchLabels: { app: web }
  template:
    metadata:
      labels: { app: web }
    spec:
      containers:
        - name: web
          image: nginx:1.27
```

**Helm and Kustomize** package declarative configuration:

- **Helm:** templated charts plus `values.yaml`, rendered into plain manifests. In GitOps the chart version and values files are committed. Argo CD renders charts with `helm template` and manages the output itself, whereas Flux's helm-controller performs real Helm releases.
- **Kustomize:** template-free; a shared base plus per-environment overlays containing patches, for example `apps/checkout/base/` with `apps/checkout/overlays/staging/` (1 replica) and `apps/checkout/overlays/prod/` (4 replicas, higher limits). It is built into kubectl (`kubectl apply -k`).

## 4. Continuous Reconciliation

The agent runs a control loop, the same pattern Kubernetes controllers use: compare the **desired state** (Git) with the **actual, live state** (cluster) and act on the difference, indefinitely.

```text
        +------------------------------+
        |  Git repo: desired state     |
        +--------------+---------------+
                       | 1. fetch (poll interval or webhook)
                       v
        +------------------------------+   2. observe live state (watch)
        |  GitOps agent (Argo CD/Flux) |<--------------------------------+
        |  3. diff desired vs live     |                                 |
        +--------------+---------------+                                 |
                       | 4. apply changes, prune removed objects,        |
                       |    revert drift (self-heal)                     |
                       v                                                 |
        +------------------------------+                                 |
        |  Cluster: actual/live state  |---------------------------------+
        +------------------------------+
                  5. repeat continuously
```

- **Triggers:** periodic polling (Argo CD's default reconciliation timeout is 3 minutes; Flux sets an `interval` on each object), Git webhooks for an immediate refresh, and watches on cluster resources.
- **Drift detection:** drift is any difference between Git and the cluster, caused by manual `kubectl` changes, another tool, or deleted resources. Argo CD reports it as `OutOfSync`.
- **Self-heal:** the agent reverts live changes to match Git (Argo CD `selfHeal: true`; Flux re-applies on every interval). Fields owned by other controllers, such as `replicas` under an HPA, should be left out of the manifest or ignored (Argo CD `ignoreDifferences`).
- **Prune:** resources deleted from Git are deleted from the cluster (Argo CD `prune: true`, Flux Kustomization `prune: true`). Without pruning, removed resources linger as orphans.

Example: someone runs `kubectl scale deployment web --replicas=10` while Git says `replicas: 3`. With self-heal, the agent scales it back to 3 on the next reconciliation; without it, the application stays `OutOfSync` until someone syncs it.

## 5. GitOps Workflow

Most teams split code and configuration into two repositories:

| | App repo | Config repo (environment or deployment repo) |
|---|---|---|
| Contains | Source code, tests, Dockerfile, CI pipeline | Kubernetes manifests, Helm values, Kustomize overlays per environment |
| Changed by | Developers | CI (image tag bumps) and platform or release engineers |
| Watched by | CI system | GitOps agent |

The split keeps deployment history clean, allows different access rules, lets configuration (such as replica count) change without rebuilding an image, and stops CI from triggering itself when it commits tag updates. Argo CD's best-practices guide recommends it.

1. A developer opens a pull request in the app repo.
2. CI runs tests, linting and security scans; reviewers approve and the PR is merged.
3. CI builds the image, tags it immutably (commit SHA or semantic version) and pushes it to the registry.
4. CI updates the image tag in the config repo: a direct commit for dev, a pull request for gated environments such as prod. Argo CD Image Updater or Flux image automation can perform this step instead.
5. The GitOps agent detects the new commit (poll or webhook).
6. It renders the manifests and syncs them: applies changes, prunes removed objects and respects ordering (sync waves).
7. The Deployment rolls out and the kubelet pulls the new image.
8. The agent assesses health (`Progressing` -> `Healthy`, or `Degraded`) and sends notifications. Rollback is a `git revert` in the config repo.

```text
  APP REPO <- (1) PR       CI PIPELINE                   IMAGE REGISTRY
 +--------------+   (2)    +---------------------+  (3)  +--------------------+
 | source code, |  merge   | test, build image,  | push  | checkout:3f2c1ab   |
 | Dockerfile   |--------->| tag = commit SHA    |------>|                    |
 +--------------+          +----------+----------+       +---------+----------+
                                      | (4) commit new image tag   |
                                      v     (direct or via PR)     |
                           +---------------------+                 |
  CONFIG REPO              | manifests, Helm     |                 |
  (desired state)          | values, overlays    |                 |
                           +----------+----------+                 |
                                      ^ (5) pull: poll or webhook  |
 - - - - - - - - - - - - - - - - - - -|- - - cluster boundary - - -|- - - - - - - -
                           +----------+----------+  (6)  +---------v------------+
                           | GitOps agent        | sync  | Deployment, pods     |
                           | (Argo CD / Flux)    |------>| (7) kubelet pulls    |
                           |                     |<------| the new image        |
                           +---------------------+  (8)  +----------------------+
                                                  health
```

```bash
# Illustrative CI step after the image push: bump the tag in the config repo
cd config-repo/apps/checkout/overlays/staging
kustomize edit set image ghcr.io/example-org/checkout=ghcr.io/example-org/checkout:${GIT_SHA}
git commit -am "checkout: deploy ${GIT_SHA} to staging" && git push
```

## 6. Push-Based CI/CD vs Pull-Based GitOps

```text
Push:  CI pipeline --(kubectl/helm, holds cluster credentials)--> cluster API     inbound to the cluster
Pull:  Git repo <--(read-only fetch)-- agent inside the cluster --> cluster API   outbound only
```

| Aspect | Push-based CI/CD | Pull-based GitOps |
|---|---|---|
| Who deploys | CI pipeline runs `kubectl apply` / `helm upgrade` | Agent inside the cluster |
| Credentials location | Cluster credentials (kubeconfig, tokens) stored in the CI system | Cluster credentials stay in the cluster; the agent needs only read access to Git and the registry |
| Network exposure | API server must be reachable from CI | Agent makes outbound connections only; the cluster API can stay private |
| Drift handling | Not detected; persists until the next pipeline run | Continuously detected; optionally corrected automatically |
| Source of truth | Whatever the last pipeline run applied | The Git repository |
| Rollback | Re-run an old pipeline or run manual commands | `git revert`, then automatic sync |
| Audit | Pipeline logs (often short retention) | Git history plus agent events |
| Impact of a CI compromise | Attacker can change clusters directly | Attacker can only push commits, which are still review-gated |
| Examples | Jenkins, GitHub Actions or GitLab CI running kubectl/helm | Argo CD, Flux |

A central Argo CD instance that manages remote clusters does connect to their API servers and holds their credentials. It is still GitOps, because desired state is pulled from Git and continuously reconciled.

## 7. Kubernetes + GitOps: Argo CD and Flux

### 7.1 Argo CD architecture

| Component | Workload | Role |
|---|---|---|
| API server (`argocd-server`) | Deployment | gRPC/REST API behind the web UI and `argocd` CLI; authentication, RBAC, SSO; receives Git webhooks; triggers sync and rollback |
| Repository server (`argocd-repo-server`) | Deployment | Clones and caches Git repositories; renders manifests (plain YAML, Helm, Kustomize, Jsonnet, plugins) for a given repo, revision and path |
| Application controller (`argocd-application-controller`) | StatefulSet | Compares live state with rendered desired state, computes sync and health status, performs syncs and runs hooks |
| ApplicationSet controller | Deployment | Generates many `Application` objects from one template plus generators (list, cluster, Git directories or files, pull requests, matrix) |
| Redis | Deployment | Disposable cache for rendered manifests and live state |
| Dex, notifications controller | Deployments | Optional SSO connector; notifications to Slack, email or webhooks |

### 7.2 The Application CRD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: checkout-prod
  namespace: argocd                  # Applications live in the Argo CD namespace by default
spec:
  project: default                   # AppProject: restricts allowed repos, clusters, namespaces
  source:
    repoURL: https://github.com/example-org/config-repo.git
    targetRevision: main             # branch, tag or commit SHA
    path: apps/checkout/overlays/prod
  destination:
    server: https://kubernetes.default.svc   # the cluster Argo CD runs in
    namespace: checkout
  syncPolicy:
    automated:
      prune: true                    # delete resources removed from Git
      selfHeal: true                 # revert manual changes made in the cluster
    syncOptions:
      - CreateNamespace=true         # create the destination namespace if missing
```

Without `syncPolicy.automated`, Argo CD only reports differences and waits for a manual sync (UI or `argocd app sync checkout-prod`). When automated sync is enabled, `prune` and `selfHeal` still default to `false` as a safety measure.

### 7.3 Sync status vs health status

The two statuses are independent: sync status compares Git with the cluster, while health status describes whether the running resources actually work.

| Status type | Value | Meaning |
|---|---|---|
| Sync | `Synced` | Live state matches the desired state at the target revision |
| Sync | `OutOfSync` | Live state differs: a new commit is not applied yet, drift occurred, or a resource is missing or extra |
| Sync | `Unknown` | Comparison failed, for example the repository is unreachable or rendering failed |
| Health | `Healthy` | Resources work as intended, for example a Deployment fully rolled out with all replicas available |
| Health | `Progressing` | Not healthy yet but still moving towards it, for example a rollout in progress |
| Health | `Degraded` | Failed or unable to become healthy, for example a Deployment past its progress deadline because pods crash-loop |
| Health | `Suspended` | Paused or waiting, for example a suspended CronJob |
| Health | `Missing` | Defined in Git but not present in the cluster |
| Health | `Unknown` | Health could not be assessed |

`Synced` + `Degraded` means Git was applied correctly but the application is broken (bad image or configuration). `OutOfSync` + `Healthy` means the application runs but differs from Git (a pending change or drift).

### 7.4 Sync waves and hooks

A sync runs in phases: `PreSync`, `Sync`, `PostSync`, plus `SyncFail` when a sync fails. **Hooks** are resources, usually Jobs, that run in a given phase, such as a database migration in `PreSync`. **Sync waves** order resources within a phase: lower waves are applied first (the default is `0`), and Argo CD waits for each wave to become healthy before starting the next.

```yaml
metadata:
  annotations:
    argocd.argoproj.io/hook: PreSync                    # run before the main sync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
    argocd.argoproj.io/sync-wave: "-1"                  # applied before wave 0 resources
```

### 7.5 Flux CD

Flux (v2, CNCF graduated) is built as the **GitOps Toolkit**: a set of single-purpose controllers, each with its own CRDs. `flux bootstrap` installs Flux and commits Flux's own manifests to the repository, so Flux is managed through GitOps too.

| Controller | CRDs | Role |
|---|---|---|
| source-controller | `GitRepository`, `OCIRepository`, `HelmRepository`, `HelmChart`, `Bucket` | Fetches and verifies sources and serves them as artifacts to the other controllers |
| kustomize-controller | `Kustomization` | Builds Kustomize overlays or plain YAML from a source and applies them; prune, health checks, `dependsOn`, SOPS decryption |
| helm-controller | `HelmRelease` | Installs, upgrades, tests and rolls back Helm releases using the Helm SDK |
| notification-controller | `Provider`, `Alert`, `Receiver` | Outbound alerts (Slack, Teams) and inbound webhooks that trigger reconciliation |
| image-reflector and image-automation controllers | `ImageRepository`, `ImagePolicy`, `ImageUpdateAutomation` | Scan registries for new tags and commit tag updates back to Git |

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization                  # Flux CRD, not Kustomize's kustomization.yaml file
metadata:
  name: checkout-prod
  namespace: flux-system
spec:
  interval: 10m                      # reconcile (and correct drift) every 10 minutes
  sourceRef:
    kind: GitRepository              # defined separately and fetched by source-controller
    name: config-repo
  path: ./apps/checkout/overlays/prod
  prune: true                        # delete objects removed from Git
```

| Aspect | Argo CD | Flux |
|---|---|---|
| Design | Central application with API server, UI and controllers | Composable set of controllers (GitOps Toolkit) |
| Web UI | Built in, with resource tree, diffs and logs | None in core Flux; CLI-first, with third-party UIs available |
| Core CRDs | `Application`, `AppProject`, `ApplicationSet` | `GitRepository`, `Kustomization`, `HelmRelease` |
| Helm handling | Renders with `helm template`; Argo CD tracks the resources | Native Helm releases via the Helm SDK (visible to `helm list`) |
| Multi-tenancy | AppProjects plus Argo CD RBAC and SSO | Kubernetes RBAC with service-account impersonation |
| Multi-cluster | One instance can manage many registered clusters | Usually one Flux per cluster; remote targets possible via kubeconfig |
| Image automation | Separate Argo CD Image Updater project | Built-in image controllers |
| SOPS secrets | Through plugins (for example KSOPS) | Native decryption in kustomize-controller |
| Project status | CNCF graduated (as part of Argo) | CNCF graduated |

## 8. Secrets in GitOps

A Kubernetes `Secret` is only base64-encoded, not encrypted. Committing one exposes it to everyone with repository access, permanently, because Git history keeps it even after the file is deleted. A leaked secret must be rotated, not just removed.

| Approach | How it works | What is stored in Git |
|---|---|---|
| **Sealed Secrets** | The `kubeseal` CLI encrypts a Secret with the in-cluster controller's public key; only the controller's private key can decrypt the resulting `SealedSecret` into a normal Secret | Encrypted `SealedSecret` (bound to a namespace and name by default) |
| **SOPS** | Encrypts the values (not the keys) of YAML/JSON files with age, PGP or a cloud KMS; decrypted at apply time | Encrypted file with a readable structure |
| **External Secrets Operator** | An `ExternalSecret` references an entry in an external manager (AWS Secrets Manager, HashiCorp Vault, Azure Key Vault, GCP Secret Manager); the operator creates and refreshes the Kubernetes Secret | Only a reference; no secret material |

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: checkout-db
  namespace: checkout
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: aws-secrets-manager        # configured once by the platform team
  target: { name: checkout-db }      # Kubernetes Secret created by the operator
  data:
    - secretKey: password
      remoteRef: { key: prod/checkout/db, property: password }
```

Supporting practices: secret scanning in CI and pre-commit hooks (for example gitleaks), push protection on the Git host, and backups of the Sealed Secrets controller key or SOPS keys for disaster recovery. Argo CD's documentation favours approaches that create Secrets inside the cluster (such as an operator) over injecting secrets while rendering manifests.

## 9. Key Takeaways

- GitOps rests on four OpenGitOps principles: declarative, versioned and immutable, pulled automatically, continuously reconciled.
- Git becomes the audit log, the change-approval process and the rollback mechanism (`git revert`).
- Only declarative, idempotent configuration can be reconciled; Helm and Kustomize package it.
- An in-cluster agent continuously compares desired and live state, detects drift and, with self-heal and prune, corrects it.
- CI builds and publishes images and updates the config repo; it never needs cluster credentials.
- Argo CD provides a central server and UI around the `Application` CRD; Flux provides composable controllers. Sync status (Git vs cluster) and health status (does it work) answer different questions.
- Plain Secrets never go into Git; use Sealed Secrets, SOPS or External Secrets Operator instead.

## 10. References

- OpenGitOps principles: <https://opengitops.dev/>, <https://github.com/open-gitops/documents/blob/main/PRINCIPLES.md>
- Argo CD documentation, architecture, declarative setup, automated sync: <https://argo-cd.readthedocs.io/en/stable/>, <https://argo-cd.readthedocs.io/en/stable/operator-manual/architecture/>, <https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/>, <https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/>
- Argo CD health, sync waves, best practices, secret management: <https://argo-cd.readthedocs.io/en/stable/operator-manual/health/>, <https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/>, <https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/>, <https://argo-cd.readthedocs.io/en/stable/operator-manual/secret-management/>
- Flux concepts, components, SOPS guide: <https://fluxcd.io/flux/concepts/>, <https://fluxcd.io/flux/components/>, <https://fluxcd.io/flux/guides/mozilla-sops/>
- Kubernetes object management and Secrets: <https://kubernetes.io/docs/concepts/overview/working-with-objects/object-management/>, <https://kubernetes.io/docs/concepts/configuration/secret/>; Sealed Secrets, SOPS, External Secrets Operator: <https://github.com/bitnami-labs/sealed-secrets>, <https://getsops.io/>, <https://external-secrets.io/>
