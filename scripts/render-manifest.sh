#!/usr/bin/env bash
# Replace {{ NAME }} placeholders in a manifest with the value of environment variable NAME.
# Fails if any referenced variable is unset, so no placeholder reaches the cluster by accident.
#
# Usage:
#   export IMAGE_REGISTRY=registry.example.com/team IMAGE_TAG=0.1.3 ...
#   scripts/render-manifest.sh k8s/deployment.single-pod.yaml > k8s/deployment.rendered.yaml
#
# Rendered files (k8s/*.rendered.yaml, k8s/secret.yaml) are git-ignored. Do not commit them.
set -euo pipefail

[[ $# -eq 1 && -f "$1" ]] || { echo "usage: $0 <manifest.yaml>" >&2; exit 2; }

missing=$( { grep -o '{{ *[A-Z0-9_]* *}}' "$1" || true; } | tr -d '{} ' | sort -u | while read -r name; do
  [[ -n "${!name+x}" ]] || echo "$name"
done)
if [[ -n "$missing" ]]; then
  echo "unset variables (export them, empty is allowed):" >&2
  echo "$missing" >&2
  exit 1
fi

perl -pe 's/\{\{\s*([A-Z0-9_]+)\s*\}\}/$ENV{$1}/g' "$1"
