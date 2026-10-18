# Legacy hand-written manifests (reference only)

These are the hand-written Kubernetes manifests from the first pilot. They are
**not applied and not maintained**: they drifted from Compose (images, databases).
Kubernetes is now generated from Compose by `kubernetes/generate.py`
(see `research/kubernetes-compose-parity-plan.md` and `docs/17-docker-to-kubernetes.md`).
They're kept only as a reference for the generator's overrides, and are
deleted once phase 3 of the plan lands.
