
## Kubernetes Assignment Automation

Use the automation below to deploy and verify Task 1B/1C quickly.
Environment: Kind on Docker

### Makefile workflow

```bash
make create-cluster
make build
make load
make deploy
make verify
```

Cleanup:

```bash
make clean
```

### One-shot workflow

```bash
./scripts/setup.sh
```

### Script breakdown

- `scripts/01-create-cluster.sh`: creates Kind cluster and installs ingress-nginx
- `scripts/02-build-images.sh`: builds local Docker images
- `scripts/03-load-images.sh`: loads images into Kind
- `scripts/04-deploy.sh`: applies manifests and sets deployment images to local tags
- `scripts/05-verify.sh`: checks pod readiness, E2E flow, NetworkPolicy block, graceful degradation
- `scripts/06-cleanup.sh`: deletes Kind cluster
