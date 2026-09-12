"""
Retriever RAG real sobre el índice ChromaDB construido en el PI de M2.

Reutiliza la colección `nubbix_docs_structural` (chunking por headers,
21 chunks) generada por `ingest/ingest.py` de PIM2. Cada chunk tiene metadata
`source` con el nombre del archivo de origen (hr_policies.md, it_manual.md,
finance_processes.md), lo que permite filtrar la búsqueda vectorial por
dominio sin mezclar contexto de otras áreas.

Lo que se hace es embedding de la query -> búsqueda
vectorial en Chroma -> top-k chunks relevantes a esa consulta.
"""
import os
from pathlib import Path
from typing import List, Dict, Any

import chromadb

# Cliente OpenAI instrumentado por Langfuse (drop-in): cada llamada de
# embeddings queda registrada automáticamente como una "generation"
# dentro del trace activo (ver agents/orchestrator.py).
from langfuse.openai import OpenAI

DOMAIN_TO_SOURCE = {
    "hr": "hr_policies.md",
    "it": "it_manual.md",
    "finance": "finance_processes.md",
}

DEFAULT_COLLECTION = "nubbix_docs_structural"


class DomainRetriever:
    """Retrieval vectorial (Chroma) filtrado por dominio."""

    def __init__(
        self,
        openai_client: OpenAI | None = None,
        collection_name: str = DEFAULT_COLLECTION,
        top_k: int = 3,
    ):
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", str(Path(__file__).parent.parent / "data" / "chroma_db"))
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection_name = collection_name
        self.top_k = top_k
        self.openai_client = openai_client or OpenAI()
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    def _embed_query(self, query: str) -> List[float]:
        res = self.openai_client.embeddings.create(input=[query], model=self.embedding_model)
        return res.data[0].embedding

    def retrieve(self, domain: str, query: str) -> List[Dict[str, Any]]:
        """Devuelve los top_k chunks más relevantes para `query`, acotados a `domain`."""
        source_file = DOMAIN_TO_SOURCE.get(domain.lower())
        try:
            collection = self.client.get_collection(name=self.collection_name)
        except Exception:
            return []

        query_embedding = self._embed_query(query)
        where_filter = {"source": source_file} if source_file else None

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=self.top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        if results and results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                chunks.append({
                    "chunk_id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": round(1.0 - results["distances"][0][i], 4),
                })
        return chunks

    def build_context(self, domain: str, query: str) -> str:
        """Arma el bloque de contexto RAG (con cita de fuente) para el prompt del agente."""
        chunks = self.retrieve(domain, query)
        if not chunks:
            return f"No se encontró contexto indexado para el dominio {domain.upper()}."

        parts = []
        for c in chunks:
            header = c["metadata"].get("header", "")
            parts.append(f"[Fuente: {c['metadata'].get('source')} · {header} · score={c['score']}]\n{c['content']}")
        return "\n\n---\n\n".join(parts)