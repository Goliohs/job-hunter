#!/usr/bin/env python3
# Run RAG with technical questions an interviewer would ask
import os
from rag_homelab import load_index, ask

QUESTIONS = [
    "What is the architecture of your private RAG pipeline?",
    "How do you partition your NVIDIA GPU for multiple workloads?",
    "What vector database do you use and why?",
    "How does your homelab ensure data privacy for AI workloads?",
    "What is your Kubernetes setup and what CNI do you use?",
    "How do you handle TLS certificates in your infrastructure?",
    "What monitoring stack do you run in your homelab?",
    "What models do you serve on Ollama and what is the performance?",
    "Explain your CI/CD pipeline from commit to deployment.",
    "What is your network architecture for the homelab?",
]

def main():
    vs = load_index()
    print("=" * 80)
    print("RAG INTERVIEW PREP - Technical Q&A from homelab knowledge base")
    print("=" * 80 + "\n")
    
    results = []
    for i, q in enumerate(QUESTIONS, 1):
        print(f"### Question {i}:")
        print(f"Q: {q}\n")
        a = ask(q, vs)
        print(f"A: {a}\n")
        print("-" * 80 + "\n")
        results.append({"q": q, "a": a})
    
    print(f"\nTotal: {len(results)} Q&A pairs generated")
    return results

if __name__ == "__main__":
    main()