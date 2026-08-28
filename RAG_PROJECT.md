# Proyecto RAG en tu GPU Homelab - Roadmap

Sistema de Retrieval-Augmented Generation privado corriendo 100% en tu hardware.

## Qué construiras
Un chatbot que responde preguntas sobre documentación técnica usando tus documentos como fuente.
- Preguntas como: "¿Cómo configuro WireGuard entre el nodo 2 y 3?"
- Respuesta con fuentes: "Según tu doc 'Proxmox setup', paso 4..."

## Componentes exactos (ya tienes el HW)

| Componente | Herramienta | Estado |
|-----------|------------|--------|
| LLM | Ollama (Llama 3.1 70B) | Ya corriendo en GPU |
| DB de vectores | ChromaDB | Instalar pip install chromadb |
| Embeddings | nomic-embed-text (Ollama) | ```ollama pull nomic-embed-text``` |
| Framework RAG | LangChain Python | ```pip install langchain langchain-ollama``` |
| Documentos source | Tus proyectos, config, docs | ./data/mi-documentacion/ |
| Frontend | Chat simple en FastAPI + HTMX | servicios.o7s.us |

## Ejecucion completa

```bash
# En tu homelab:
ollama pull nomic-embed-text
pip install chromadb langchain langchain-ollama langchain-community
```

## Archivo principal - rag_app.py

```python
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_community.vectorstores import Chroma
from langchain.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain.document_loaders import DirectoryLoader, TextLoader
import os

# 1. Cargar documentos
docs = []
for folder in ["/data/homelab-docs", "/data/proyectos"]:
    if not os.path.exists(folder):
        continue
    loader = DirectoryLoader(folder, "**/*.md")
    docs.extend(loader.load())

print(f"Loaded {len(docs)} documents")

# 2. Dividir y crear embeddings
texts_to_embed = Document.page_content for doc in docs #
# split into chunks
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = text_splitter.split_documents(docs)

embedding = OllamaEmbeddings(model="nomic-embed-text")
vectorstore = Chroma.from_documents(documents=chunks, embedding=embedding, persist_directory="/app/chroma-data")
vectorstore.persist()

# 3. Pipeline de queries
llm = ChatOllama(model="llama3.1:8b", temperature=0.3)
qa = RetrievalQA(llm=llm, retriever=vectorstore.get_retriever())

# 4. API endpoint
from fastapi import FastAPI
app = FastAPI()

@app.post("/rag/query")
async def query(question: str):
    answer = qa.run(question)
    return {"answer": answer, "sources": vectorstore.highlight_get_relevant_documents(question)}
```

## Qué ganarías aplicando a CUALQUIER trabajo

- En entrevista: "Tengo un ChatGPT privado que se ejecuta en mi GPU. Cero egress de datos. RAG pipeline real."
- Portfolio: un endpoint API trabajando sobre tus docs
- Unicidad: Pocos desarrolladores tienen RAG LAB. Tu homelab VIP te da esa ventaja.

## Implementación
1. Crear carpeta `./data-documentacion` con tus notas (5-10 markdown files, puede ser tu CV, documentacion)
2. Instalar dependencias: chromadb, langchain, langchain-ollama
3. Correr script de embedding una vez (toma 5 min)
4. Exponer via FastAPI en tu servidor
5. Probar con 5 preguntas (ejemplos arriba)
6. Documentar en blog/https://your-portfolio.example.com

## Total tiempo: 2-3 horas
## Total costo: 0$ (tu GPU ya corre 24/7)
## Valor en entrevista: Incalculable (literalmente nadie lo tiene)