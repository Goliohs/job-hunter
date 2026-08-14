# DevOps Skills Reference

## Container Orchestration
- Kubernetes, k3s, k0s, Rancher
- Helm charts, Kustomize
- ArgoCD and Flux for GitOps
- Cilium CNI, eBPF networking extensions

## Infrastructure as Code
- Terraform, Ansible, Packer, Cloud-init
- Pulumi (Python/Go)
- Crossplane (Kubernetes controller for AWS/GCP)

## CI/CD
- GitLab CI (full pipeline with Docker build/push/deploy)
- GitHub Actions (matrix builds, release automation)
- Drone CI (self-hosted, lightweight pipeline runner)
- Woodpecker CI (open-source Drone fork, uses Docker)

## Monitoring
- Prometheus for metrics collection
- Grafana for dashboards and alerting visualization
- Loki for log aggregation
- Tempo for distributed tracing
- VictoriaMetrics for long-term metric storage
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Alertmanager for alert routing and deduplication

## Security
- HashiCorp Vault for secrets management
- mTLS everywhere enforced by cert-manager and Vault PKI
- Zero Trust networking (no service accessible from public internet)
- CIS Benchmark compliance via automated Ansible auditing
- SOPS with Age for encrypted secrets in repositories
- WireGuard for VPN and service mesh

## Networking Fundamentals
- 10GbE routing and switching on Cisco and MikroTik hardware
- BGP and OSPF routing between core service VLANs
- VLAN and VXLAN segmentation for service isolation
- IPSec and WireGuard for site-to-site VPN tunnels
- HAProxy and Nginx for layer-7 load balancing

## AI and ML Infrastructure
- Ollama serving LLaMA, CodeLlama, Mistral on GPU
- vLLM for GPU optimization with MIG partitioning
- LocalAI for embedding and RAG endpoints
- NVIDIA GPU scheduling with MIG for task isolation
- Private RAG pipeline for document QA on homelab