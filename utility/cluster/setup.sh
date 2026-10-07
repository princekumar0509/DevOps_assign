#!/usr/bin/env bash
# setup.sh - create the local lab: registry + kind cluster + metrics-server + ingress-nginx.
# Idempotent: re-running skips whatever already exists.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER="${CLUSTER:-devops-lab}"
CONFIG="${CONFIG:-$HERE/kind-config.yaml}"
REG_NAME=kind-registry
REG_PORT=5001

# 1. local registry (CI pipelines push here, the cluster pulls from here)
if [ "$(docker inspect -f '{{.State.Running}}' "$REG_NAME" 2>/dev/null || true)" != "true" ]; then
  docker run -d --restart=always -p "127.0.0.1:${REG_PORT}:5000" --network bridge --name "$REG_NAME" registry:2
fi

# 2. the cluster
if ! kind get clusters | grep -qx "$CLUSTER"; then
  kind create cluster --config "$CONFIG" --name "$CLUSTER" --wait 120s
fi

# 3. tell every node that localhost:5001 means the registry container
for node in $(kind get nodes --name "$CLUSTER"); do
  docker exec "$node" mkdir -p "/etc/containerd/certs.d/localhost:${REG_PORT}"
  printf '[host."http://%s:5000"]\n' "$REG_NAME" |
    docker exec -i "$node" cp /dev/stdin "/etc/containerd/certs.d/localhost:${REG_PORT}/hosts.toml"
done
docker network connect kind "$REG_NAME" 2>/dev/null || true

# 3b. Docker Hub rate-limits anonymous pulls per IP (this network hits the
#     100/hour cap), so pull docker.io images through Google's public
#     mirror first and fall back to Docker Hub itself.
for node in $(kind get nodes --name "$CLUSTER"); do
  docker exec "$node" mkdir -p /etc/containerd/certs.d/docker.io
  printf 'server = "https://registry-1.docker.io"\n\n[host."https://mirror.gcr.io"]\n  capabilities = ["pull", "resolve"]\n' |
    docker exec -i "$node" cp /dev/stdin /etc/containerd/certs.d/docker.io/hosts.toml
done

# 4. advertise the registry the standard way (KEP-1755)
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:${REG_PORT}"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF

# 5. metrics-server (kubectl top + HPA). kind kubelets use self-signed certs.
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.0/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' 2>/dev/null || true

# 6. ingress-nginx, kind flavour (binds hostPort 80/443 on the ingress-ready node)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/kind/deploy.yaml

kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=300s
