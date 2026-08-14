# Private RAG Pipeline Architecture

## Overview
The Retrieval-Augmented Generation pipeline runs entirely on the O7 homelab GPU infrastructure. Zero data egress, zero cloud dependency, zero API costs.

## Components

### Embedding Model
- Model: nomic-embed-text (274 MB, 768-dimensional vectors)
- Runtime: Ollama API on localhost port 11434
- GPU accelerated via NVIDIA RTX 4000 Ada
- Used for document chunk embedding and query embedding

### Vector Database
- ChromaDB persistent local storage at chroma-data directory
- Cosine similarity search
- Stores 768-dim embeddings plus document text plus metadata (source file path)
- Current corpus: 5 markdown files covering homelab infrastructure, DevOps skills, professional experience, AI projects, RAG architecture

### Language Model
- Model: gemma4 (Google Gemma 3 4B quantized)
- Runtime: Ollama API on localhost port 11434
- GPU accelerated via NVIDIA RTX 4000 Ada
- Temperature: 0.3 for factual answers, 0.7 for creative tasks
- Context window: handles 8K tokens

### Framework
- LangChain 1.3.14 for orchestration
- langchain-ollama 1.1.0 for Ollama integration
- langchain-chroma 1.1.0 for ChromaDB vector store
- langchain-text-splitters for chunking

### Document Processing Pipeline
1. Load markdown and text files from rag-data directory using TextLoader
2. Split into 800-character chunks with 100-character overlap using RecursiveCharacterTextSplitter
3. Generate 768-dim embeddings via Ollama nomic-embed-text
4. Store in ChromaDB with metadata (source file path)
5. On query: embed question, retrieve top 4 chunks by cosine similarity
6. Feed context plus question to gemma4 LLM
7. Return answer with source citation

## Query Flow
Question -> Ollama embed -> ChromaDB cosine search -> top 4 chunks -> context + question -> gemma4 LLM -> answer with source

## Privacy Guarantees
- No data leaves the homelab network
- No external API calls during inference
- No telemetry or usage tracking
- All documents stored locally on ZFS pool with encryption-at-rest
- Network isolated via VLAN and WireGuard only access

## Use Cases
- Internal knowledge base for homelab operations
- Technical interview preparation (ask about own infrastructure)
- Documentation assistant for onboarding new team members
- Proof-of-concept for client AI solutions (privacy-preserving)