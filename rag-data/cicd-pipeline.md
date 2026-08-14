# CI/CD Pipeline Architecture

## GitOps Pipeline - Commit to Production
The pipeline runs entirely on the O7 homelab with GitLab CI plus ArgoCD.

### Phase 1: Commit and Build
- Developer commits code to GitLab repository
- GitLab CI webhook triggers pipeline
- Pipeline stages: lint, test, build Docker image, push to internal registry
- Docker image tagged with commit SHA plus branch name
- Internal registry: Harbor on homelab MinIO backend

### Phase 2: Deploy via GitOps
- GitLab CI updates manifest repository with new image tag
- ArgoCD detects manifest change via webhook polling
- ArgoCD syncs manifests to k3s Kubernetes cluster
- Deployment rolls out with health checks and rollback on failure
- Total commit-to-prod time: 3 to 8 minutes depending on image size

### Phase 3: Verification
- ArgoCD shows sync status and diff
- Prometheus alerts fire if deployment health fails
- Canary deployment supported via ArgoCD Rollouts for 10 percent traffic shift before full rollout

## CI/CD Tools Used
- GitLab CI: primary CI runner, Docker executor on k3s
- GitHub Actions: used for open source projects, matrix builds
- Drone CI: self-hosted, lightweight, used for quick side projects
- Woodpecker CI: open source Drone fork, Docker-native pipeline executor
- ArgoCD: GitOps controller for k3s cluster, sync wave support
- Flux: alternative GitOps controller, used for multi-cluster scenarios

## Build Optimization
- Layer caching via BuildKit plus Docker cache mount
- Multi-stage builds for smaller images (Alpine or distroless base)
- Push to registry only if tests pass (atomic stage gate)
- Concurrent matrix builds for multi-arch (amd64 plus arm64)