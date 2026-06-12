CLUSTER_NAME ?= healthcare-triage
NAMESPACE ?= healthcare-triage-dev
INGRESS_HOST ?= triage.127.0.0.1.nip.io

.PHONY: create-cluster build load deploy verify monitoring clean setup

create-cluster:
	CLUSTER_NAME=$(CLUSTER_NAME) ./scripts/01-create-cluster.sh

build:
	./scripts/02-build-images.sh

load:
	CLUSTER_NAME=$(CLUSTER_NAME) ./scripts/03-load-images.sh

deploy:
	NAMESPACE=$(NAMESPACE) ./scripts/04-deploy.sh

verify:
	NAMESPACE=$(NAMESPACE) INGRESS_HOST=$(INGRESS_HOST) ./scripts/05-verify.sh

monitoring:
	./scripts/07-install-monitoring.sh

clean:
	CLUSTER_NAME=$(CLUSTER_NAME) ./scripts/06-cleanup.sh

setup: create-cluster build load deploy verify
