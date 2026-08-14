# RAG on GPU Homelab - Document QA System
# 100% private, runs on your Ollama + NVIDIA GPU

import os
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader

PERSIST_DIR = os.path.expanduser("~/job-hunter/chroma-data")
DATA_DIR = os.path.expanduser("~/job-hunter/rag-data")
EMBED_MODEL = "nomic-embed-text"
LLM_MODEL = "gemma4:latest"

def build_index():
    if not os.path.isdir(DATA_DIR):
        raise FileNotFoundError(f"Data dir not found: {DATA_DIR}")

    os.makedirs(PERSIST_DIR, exist_ok=True)

    loaders = []
    for root, _, files in os.walk(DATA_DIR):
        for f in files:
            if f.endswith((".md", ".txt")):
                path = os.path.join(root, f)
                loaders.append(TextLoader(path, encoding="utf-8"))

    if not loaders:
        raise RuntimeError(f"No .md/.txt files found in {DATA_DIR}")

    print(f"Loading {len(loaders)} text files...")
    docs = []
    for ldr in loaders:
        docs.extend(ldr.load())

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    print(f"Split into {len(chunks)} chunks from {len(docs)} documents")

    print(f"Embedding with {EMBED_MODEL} on Ollama...")
    embedding = OllamaEmbeddings(model=EMBED_MODEL)
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embedding,
        persist_directory=PERSIST_DIR,
    )
    print("Embedding complete. Vector store saved.")
    return vectorstore

def load_index():
    embedding = OllamaEmbeddings(model=EMBED_MODEL)
    return Chroma(persist_directory=PERSIST_DIR, embedding_function=embedding)

def ask(question: str, vectorstore=None, k: int = 4):
    if vectorstore is None:
        vectorstore = load_index()

    llm = ChatOllama(model=LLM_MODEL, temperature=0.3)
    retriever = vectorstore.as_retriever(search_kwargs={"k": k})
    docs = retriever.invoke(question)

    context = "\n\n".join(d.page_content for d in docs)

    prompt = (
        "You are an AI assistant that answers questions based ONLY on the provided context. "
        "If the answer is not in the context, say 'No hay suficiente informacion en mis documentos.' "
        "Always cite which document section you used.\n\n"
        "CONTEXT:\n"
        f"{context}\n\n"
        f"QUESTION: {question}\n"
        "ANSWER (with source reference):"
    )

    answer = llm.invoke(prompt)
    return answer.content

def interactive():
    print("RAG Chat (type /quit to exit)\n")
    try:
        vs = load_index()
    except:
        print("No index found. Run --index first to build it.")
        return

    while True:
        q = input("You: ").strip()
        if q.lower() in ("/quit", "/q", ""):
            break
        print("AI: " + ask(q, vs) + "\n")

def serve_api(host="0.0.0.0", port=9090):
    import json
    from http.server import HTTPServer, BaseHTTPRequestHandler

    try:
        vectorstore = load_index()
    except Exception:
        print("No index found. Run with --index first.")
        return

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"status": "ok", "index_size": vectorstore._collection.count()})
            elif self.path.startswith("/ask"):
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(self.path).query)
                question = q.get("q", [""])[0]
                if not question:
                    self._send(400, {"error": "Missing ?q=question"})
                    return
                try:
                    answer = ask(question, vectorstore)
                    self._send(200, {"question": question, "answer": answer})
                except Exception as e:
                    self._send(500, {"error": str(e)})
            else:
                self._send(404, {"error": "Not found. Use /ask?q=question or /health"})

        def do_OPTIONS(self):
            self._send(200, {})

    print(f"RAG API running at http://{host}:{port}")
    print(f"  GET /health         -> index stats")
    print(f"  GET /ask?q=question -> RAG answer")
    HTTPServer((host, port), Handler).serve_forever()

if __name__ == "__main__":
    import sys
    if "--index" in sys.argv:
        build_index()
        print("Index built successfully at " + PERSIST_DIR)
    elif "--serve" in sys.argv:
        serve_api()
    elif "--ask" in sys.argv and len(sys.argv) > 3:
        q = sys.argv[sys.argv.index("--ask") + 1]
        print("Q: " + q)
        print("A: " + ask(q))
    elif "--test" in sys.argv:
        load_index()
        questions = [
            "What hypervisor do I use in the homelab?",
            "What is the Kubernetes distribution used?",
            "How do I handle TLS certificates?"
        ]
        for q in questions:
            print("Q: " + q + " -> " + ask(q)[:200])
    else:
        interactive()