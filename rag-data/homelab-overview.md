# O7 Homelab Infrastructure Overview

## Hardware
- 3-node cluster:
  - 2x Dell R730XD (dual Xeon E5-2697v4, 512GB RAM each)
  - 1x GPU Node (dual Xeon Silver, NVIDIA RTX 4000 Ada)
- Networking: 10GbE backbone, Cisco 3750 switches, MikroTik CRS326
- Storage: Ceph distributed storage (3x replication), ZFS pools
- Hypervisor: Proxmox VE 8.2 on all 3 nodes

## Kubernetes Stack
- k3s Kubernetes cluster (v1.29) with automatic HA via etcd embedded
- Helm charts for deployment
- ArgoCD for GitOps pipelines
- Drone CI and Woodpecker CI for continuous integration
- Cilium CNI for networking with eBPF overlay
- cert-manager for automatic TLS certificate provisioning

## Private AI Platform
- Ollama API serving LLaMA 3.1 70B, CodeLlama 34B, Mistral 7B
- vLLM with NVIDIA GPU for production inference
- LocalAI OpenAI-compatible API endpoint
- Zero data egress (all inference stays on-premise)
- GPU scheduling with NVIDIA MIG for isolating tasks
- Embedding models: nomic-embed-text, mxbai-embed-large

## Infrastructure Services
- PostgreSQL HA (streaming replication, pgBouncer)
- Redis Cluster (3-node sentinel)
- ClickHouse analytics database
- MinIO S3-compatible object storage
- Vault secret management by HashiCorp
- Monitoring: Prometheus plus Grafana plus Loki plus Tempo plus AlertManager
- Logging: ELK Stack (Elasticsearch, Logstash, Kibana)
- Load balancing: HAProxy plus keepalived VIP, Nginx reverse proxy