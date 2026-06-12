# PATCHING.md

Patch deployment runbook for production changes.

## 1. Purpose and Scope

This document explains the standard process for:
- hotfix deployment
- security patch deployment
- blue-green rollout
- rollback
- verification and communication

Applies to all triage-engine production patch releases.

## 2. Hotfix Deployment (Emergency Path)

Use this path when there is active production impact and the fix must be released quickly.

1. Create a hotfix branch from current production baseline.
2. Apply the minimal safe code change.
3. Run quick checks:
   - unit tests
   - lint if available
4. Build and push image with immutable tag (`<service>:<version-or-sha>`).
5. Deploy patch to inactive color first (green).
6. Wait until rollout is healthy.
7. Run smoke tests on green.
8. Switch traffic to green.
9. Monitor for 10-15 minutes.

## 3. Security Patch Deployment (Planned Path)

Use this path for CVEs or dependency issues found by CI or vulnerability scanning.

1. Identify vulnerable package and approved patched version.
2. Update dependency files consistently across runtime and dev/test.
3. Rebuild and push patched image.
4. Run tests.
5. Re-run vulnerability scan (Trivy/CI).
6. Confirm the finding is fixed and no new critical issue appears.
7. Deploy using blue-green rollout flow.
8. Record patch evidence (scanner result, image tag, deployment time).

## 4. Zero-Downtime Strategy: Blue-Green

Chosen strategy: **Blue-Green**.

Reason:
- easier rollback because traffic can switch back quickly

Current implementation:
- Blue deployment: `k8s/deployment-triage.yaml` (`track: blue`)
- Green deployment: `k8s/deployment-triage-green.yaml` (`track: green`)
- Traffic switch: `k8s/service-triage.yaml` selector (`track: blue/green`)

How it works:
1. Deploy new version to green.
2. Wait until green pods are Ready.
3. Switch Service selector from blue to green.
4. Keep blue running for fast rollback.

## 5. Rollback Procedure (Step-by-Step)

Trigger rollback if pods fail to start, health checks fail, or errors increase after deployment.

1. Confirm the failure from pod status, rollout status, or monitoring.
2. Route traffic back to previous stable color (blue).
3. Undo failed rollout on green deployment.
4. Wait until blue is stable and serving traffic.
5. Re-run smoke tests.
6. Announce rollback completion.

Reference commands:

```bash
kubectl -n healthcare-triage-dev patch service triage-engine \
  -p '{"spec":{"selector":{"app":"triage-engine","track":"blue"}}}'

kubectl -n healthcare-triage-dev rollout undo deployment/triage-engine-green
kubectl -n healthcare-triage-dev rollout status deployment/triage-engine-green --timeout=180s
```

### 5.1 Task 4D Reproducible Rollback Drill (Script)

Use script: `scripts/08-rollback-drill.sh`

This script automatically performs the full 4D scenario:
1. deploys a deliberately broken image tag
2. waits for Kubernetes failure signal (`ImagePullBackOff` or `ErrImagePull`)
3. runs `kubectl rollout undo`
4. verifies service health and recovery time (target: <= 2 minutes)

Run:

```bash
./scripts/08-rollback-drill.sh
```

Evidence to capture:
- terminal output showing `ImagePullBackOff` or `ErrImagePull`
- terminal output showing `rollout undo` success
- health response from `/health` after rollback
- recovery duration in seconds (must be <= 120)

## 6. Patch Verification Checklist

Run after every deployment and after rollback if rollback is used:

1. Deployment health
   - pods are Running/Ready
   - rollout status is successful
2. Smoke tests
   - health endpoint returns 200
   - readiness endpoint returns expected state
   - main API happy path returns success
   - validation/error path still behaves correctly
3. Monitoring checks
   - request error rate is normal
   - latency stays within baseline
   - no unusual downstream failures
4. Security checks (for dependency patches)
   - vulnerability scan passes required threshold

## 7. Communication Plan

Who to notify:
- engineering/on-call
- QA or test owner
- product/incident coordinator (for customer-impacting patches)

When to notify:
1. Before deployment: scope, target version/tag, start time.
2. During deployment: green ready, cutover started, cutover completed.
3. If rollback occurs: reason, rollback start, service restored confirmation.
4. After completion: final status, validation result, follow-up actions.

Suggested status format:
- Change: `<patch-id>`
- Service: `<service-name>`
- Version: `<image-tag>`
- Strategy: `blue-green`
- Status: `in-progress | completed | rolled-back`
- Notes: short summary and next action
