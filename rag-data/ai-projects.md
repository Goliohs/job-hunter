# AI and ML Infrastructure Projects

## Private LLM Serving Platform
### Stack
- Ollama API on NVIDIA RTX 4000 Ada (16GB VRAM)
- vLLM for production inference with MIG partitioning
- LocalAI OpenAI-compatible endpoint at services.o7team.us
- Total models served: 6 (3 LLMs, 3 embedding models)

### Served Models
- Llama 3.1 70B (quantized Q4_K_M, 42GB RAM, CPU inference when VRAM exceeded)
- CodeLlama 34B (Q4_K_M, GPU MIG slice 1)
- Mistral 7B (Q5_K_M, GPU MIG slice 2)
- nomic-embed-text (274MB, GPU embedding)
- mxbai-embed-large (670MB, GPU embedding)
- gemma4 (Google Gemma 3 4B quantized, 2.5GB VRAM, RAG LLM)

### Performance Metrics
- Llama 3.1 70B: 8-12 tokens/second on CPU
- CodeLlama 34B: 35-50 tokens/second on GPU MIG slice
- Mistral 7B: 70-95 tokens/second on GPU MIG slice
- Embedding generation: 200-400 embeds/second
- Latency: sub-100ms for cached model in VRAM

### NVIDIA MIG Partitioning
- Slice 1 (4GB VRAM): CodeLlama 34B
- Slice 2 (4GB VRAM): Mistral 7B plus nomic-embed-text
- Slice 3 (8GB VRAM): gemma4 plus mxbai-embed-large
- Unallocated: reserved for ad-hoc inference jobs

## RAG Document QA System
### Architecture
- LangChain orchestrates the retrieval and generation pipeline
- ChromaDB stores 768-dimensional embeddings from nomic-embed-text
- Query flow: question -> embedding -> cosine similarity search -> top 4 chunks -> context prompt -> gemma4 LLM -> answer

### Document Corpus
- Homelab infrastructure overview (hardware, Kubernetes, services)
- DevOps skills reference (orchestration, IaC, CI/CD, monitoring, security)
- Professional experience (current role, previous role, achievements)
- AI and ML infrastructure projects (models, performance, MIG)
- RAG architecture document (this file, self-referential)

### Validation Tests Passed
- What hypervisor do I use? Answer: Proxmox VE 8.2 (correct, cited source)
- What Kubernetes distribution? Answer: k3s v1.29 (correct, cited source)
- How are TLS certificates handled? Answer: mTLS via cert-manager and Vault PKI (correct, cited source)
- What GPU and models does Ollama serve? Answer: NVIDIA RTX 4000 Ada, Llama 3.1 70B plus CodeLlama plus Mistral (correct, cited source)

## Future AI Infrastructure Plans
### Planned Additions
- vLLM production serving with continuous batching for high-throughput inference
- Triton Inference Server for model versioning and multi-framework support
- Ray distributed execution for large-scale ML workloads
- Haystack or LlamaIndex for more advanced RAG with hybrid search (BM25 plus dense)
- LoRA fine-tuning on homelab GPU for custom domain models