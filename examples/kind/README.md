# kind walkthrough

This walkthrough uses a disposable, local kind cluster and the included Helm
chart. It shows real commands alongside three state-language plans. As the
library is only a language, it offers a plan preview, but does not run Helm 
or kubectl, observe the cluster, take backups, or generate executable shell 
commands. These steps must be performed manually or by a helper library. Previews 
assume each stage starts in the documented state and completes successfully.

## Prerequisites and isolation

Install Docker, [kind](https://kind.sigs.k8s.io/docs/user/quick-start/),
[kubectl](https://kubernetes.io/docs/tasks/tools/), Helm 3, and this Python
package as described in the [main README](../../README.md). 

```sh
kind get clusters                 # verify st8-example is not listed
export KUBECONFIG="$(mktemp -d)/kubeconfig"
export ST8_BACKUP_DIR="$(mktemp -d)"
kind create cluster --name st8-example --kubeconfig "$KUBECONFIG"
kubectl config current-context   # must be kind-st8-example
```

In the same shell, preview the plans:

```sh
pyenv exec python examples/kind/preview.py
```

`install.yaml` models the release only. The other plans start with the
manually supplied release, ConfigMap message and deployment replica count in
`preview.py`; those are separate projections, not a discovery of every
resource created by Helm. Hashes are meaningful only within a particular
projection. Inspect the YAML, printed inverses, and hashes before proceeding.

## 1. Install and reverse a chart

The local chart creates a ConfigMap and an nginx Deployment; the message is
example configuration and is not mounted into nginx.

```sh
helm lint examples/kind/chart
helm install st8-demo examples/kind/chart --namespace default --wait --timeout 5m
kubectl rollout status deployment/st8-demo --namespace default --timeout=5m
kubectl get configmap st8-demo-config --namespace default -o jsonpath='{.data.message}'; echo
helm list --namespace default
```

The preview for `install.yaml` describes deleting the previously absent
release. Do it manually and verify that both chart resources are gone:

```sh
helm uninstall st8-demo --namespace default --wait
kubectl get deployment/st8-demo configmap/st8-demo-config --namespace default --ignore-not-found
helm list --namespace default
```

The empty release projection has its original hash again. This is a
compensation: uninstalling resources cannot undo all real-world effects.

## 2. Change and reverse configuration and scale

Reinstall the chart to establish the baseline used by `changes.yaml`:

```sh
helm install st8-demo examples/kind/chart --namespace default --wait --timeout 5m
kubectl patch configmap st8-demo-config --namespace default --type merge \
  -p '{"data":{"message":"goodbye from st8"}}'
kubectl scale deployment/st8-demo --namespace default --replicas=2
kubectl rollout status deployment/st8-demo --namespace default --timeout=5m
kubectl get configmap st8-demo-config --namespace default -o jsonpath='{.data.message}'; echo
kubectl get deployment st8-demo --namespace default -o jsonpath='{.spec.replicas}'; echo
```

The expected values are `goodbye from st8` and `2`. Follow the preview's
reverse order and verify the baseline:

```sh
kubectl scale deployment/st8-demo --namespace default --replicas=1
kubectl rollout status deployment/st8-demo --namespace default --timeout=5m
kubectl patch configmap st8-demo-config --namespace default --type merge \
  -p '{"data":{"message":"hello from st8"}}'
kubectl get configmap st8-demo-config --namespace default -o jsonpath='{.data.message}'; echo
kubectl get deployment st8-demo --namespace default -o jsonpath='{.spec.replicas}'; echo
```

Expected values are `hello from st8` and `1`. Applied to the supplied
projection, those inverse values return its hash to the initial hash. Scaling
back is compensatable, not a guarantee that workload effects were undone.
These direct patches change live objects but not Helm's stored values; a later
Helm upgrade can overwrite them.

## 3. Irreversible action and recovery from an external backup

Deleting the only copy of a value cannot be reversed from the post-deletion
state alone. `destructive.yaml` declares this operation irreversible and
requires a snapshot. Here the snapshot is an explicit JSON export outside the
cluster—not an automated or whole-cluster snapshot. Save it and verify that
the data contains `message` **before** continuing:

```sh
kubectl get configmap st8-demo-config --namespace default -o json > "$ST8_BACKUP_DIR/configmap.json"
pyenv exec python -c 'import json,sys; print(json.load(open(sys.argv[1]))["data"]["message"])' \
  "$ST8_BACKUP_DIR/configmap.json"
```

Now remove the key and verify its absence:

```sh
kubectl patch configmap st8-demo-config --namespace default --type json \
  -p '[{"op":"remove","path":"/data/message"}]'
kubectl get configmap st8-demo-config --namespace default -o json
```

The recovery preview stops at the `manual` boundary. Restore the saved
ConfigMap data with a merge patch, independently of the state-language
inverse:

```sh
RESTORE_PATCH="$(pyenv exec python -c 'import json,sys; print(json.dumps({"data": json.load(open(sys.argv[1]))["data"]}))' "$ST8_BACKUP_DIR/configmap.json")"
kubectl patch configmap st8-demo-config --namespace default --type merge -p "$RESTORE_PATCH"
kubectl get configmap st8-demo-config --namespace default -o jsonpath='{.data.message}'; echo
```

The restored message should match the saved value. This restores only this
ConfigMap's saved data, not cluster state, external effects, or persistent
volumes; a real recovery needs a tested backup appropriate to the affected
data. The example backup can contain sensitive data; protect or remove it
when finished.

## Cleanup

Only after verifying the cluster name and context, delete **this example
cluster** (all data in it will be lost):

```sh
kubectl config current-context   # must be kind-st8-example
kind delete cluster --name st8-example --kubeconfig "$KUBECONFIG"
```

The temporary kubeconfig and backup directory remain on disk. Remove those
specific files/directories yourself after confirming you no longer need them.
