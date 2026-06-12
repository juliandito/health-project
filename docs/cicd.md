# CI/CD Pipeline — triage-engine

This documents the CI/CD pipeline design decisions and configuration for the `triage-engine` service.

---

## Pipeline Overview

The pipeline has 6 stages that run in sequence. Each stage must pass before the next one starts.

```
[Lint & Scan] → [Test] → [Build & Push] → [Image Scan] → [Deploy Staging] → [Deploy Prod]
     1               2           3               4                5                  6
```

| # | Stage | What Happens | Fails When |
|---|-------|-------------|------------|
| 1 | Lint & Scan | `ruff` checks Python style; `detect-secrets` and `gitleaks` check for leaked credentials | Lint errors or secrets found |
| 2 | Test | `pytest` runs unit tests with a **70% coverage gate** | Coverage < 70% |
| 3 | Build & Push | Builds the Docker image and pushes it to GHCR tagged with the git SHA | Build or push fails |
| 4 | Image Scan | Trivy scans the image for CVEs and blocks on any **CRITICAL** vulnerability | Any CRITICAL CVE found |
| 5 | Deploy Staging | Spins up an ephemeral kind cluster in CI, deploys the new image, runs a smoke test | Rollout fails or `/health` returns non-200 |
| 6 | Deploy Prod | **Manual approval** in GitHub → rolling update on the local kind cluster | Approval denied or rollout times out |

---

## Branch Strategy

Which branches trigger which stages:

| Branch | Stages | Notes |
|--------|--------|-------|
| `feature/*` | 1–4 | No deploy. Safe for WIP. |
| `hotfix/*` | 1–4 | Same as feature. PR opened to `main` when ready. |
| `develop` | 1–5 | Auto-deploys to staging on every push. |
| `main` | 1–6 | Full pipeline. Stage 6 is triggered manually. |
| PR → `main` or `develop` | 1–2 | Fast feedback — lint + test only, no build. |

### Day-to-Day Flow
1. Work on a `feature/*` branch. Pushing triggers lint + test + build + scan (stages 1–4).
2. Merging into `develop` auto-deploys to staging for end-to-end validation.
3. When `develop` is stable, a PR is opened from `develop` → `main`.
4. After merging to `main`, stages 1–5 run automatically. Stage 6 (production) is triggered manually via `deploy-prod.yml`.

---

## Hotfix Procedure

For critical bugs that need to bypass the `develop` queue and go straight to production.

1. Branch off `main`, fix, and push:
   ```bash
   git checkout main && git pull
   git checkout -b hotfix/describe-the-fix
   # ... make fix ...
   git push origin hotfix/describe-the-fix
   ```
2. PR opened from `hotfix/...` → `main` and merged. The pipeline runs stages 1–5.
3. Production deploy triggered manually via **Actions → Deploy to Production → Run workflow** with the new SHA.
4. A second PR from `hotfix/...` → `develop` keeps both branches in sync.

---

## Image Tagging Convention

Every image is pushed to `ghcr.io/juliandito/health-triage/triage-engine`.

| Tag | When Applied | Purpose |
|-----|-------------|---------|
| `<full-git-sha>` (e.g. `abc1234def5...`) | Every push to any branch | Immutable. Uniquely identifies exactly what code is running. |
| `latest` | Push to `main` only | Convenience pointer. Never deploy `latest` to production; always use the SHA. |

SHA tags are used for rollbacks — they allow pinning any deployment to the exact image that was built for a given commit.

---

## Rollback Procedure

**Option 1 — Quick (revert to previous deploy):**
```bash
kubectl rollout undo deployment/triage-engine -n healthcare-triage-dev
```

**Option 2 — Precise (pin to a known good SHA):**  
The SHA is found in the GitHub Actions run logs or the GHCR package page:
```bash
kubectl set image deployment/triage-engine \
  triage-engine=ghcr.io/juliandito/health-triage/triage-engine:<previous-sha> \
  -n healthcare-triage-dev
```

**Verify:**
```bash
kubectl rollout status deployment/triage-engine -n healthcare-triage-dev
curl http://localhost:8002/health  # after port-forwarding
```

---

## Triggering the Pipeline

### Automatic (Stages 1–5)

The pipeline will run automatically on push,  currently monorepo config:
- Push to `feature/*` or `hotfix/*` → stages 1–4
- Push to `develop` → stages 1–5
- Push to `main` → stages 1–5
- Open/update PR to `main` or `develop` → stages 1–2

### Manual (Stage 6 — Production Deploy)

After stages 1–5 pass on `main`:

1. Go to **Actions** → **Deploy to Production**
2. Click **Run workflow**
3. Paste the git SHA from the stage 3 logs (visible in the completed `ci-cd.yml` run)
4. Set `confirmed` to `true`
5. Click **Run workflow**

The self-hosted runner (on WSL) will perform the rolling update on the local kind cluster.

---

## Design Decisions & Constraints

### Self-Hosted Runner for Production

Production runs on a **local kind cluster** (WSL). GitHub's cloud runners (`ubuntu-latest`) have no network access to a local machine, so stage 6 is configured to run on a self-hosted runner registered on the same machine as the cluster. The runner requires `docker`, `kind`, and `kubectl` with `~/.kube/config` pointing to the kind cluster.

### Stage 6 as a Separate Workflow

The ideal solution would be a **GitHub Environment with Required Reviewers** — a built-in approval gate inside `ci-cd.yml`. This feature is only available on paid GitHub plans and is not available on the free plan used here.

The workaround is `.github/workflows/deploy-prod.yml`, a separate workflow triggered only via `workflow_dispatch` (manual). After stages 1–5 pass, the production deploy is initiated through **Actions → Deploy to Production → Run workflow**, entering the SHA from the stage 3 logs and setting `confirmed: true`. The manual trigger acts as the approval gate; the `confirmed` input guards against accidental runs.

### No Secrets Required

`GITHUB_TOKEN` is injected automatically by GitHub Actions with permission to push/pull from GHCR. No additional secrets need to be configured.