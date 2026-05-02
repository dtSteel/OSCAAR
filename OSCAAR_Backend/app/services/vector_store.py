import structlog
from app.core.config import settings

log = structlog.get_logger()

_store = None


def get_vector_store():
    global _store
    if _store is None:
        if settings.VECTOR_STORE == "chroma":
            _store = ChromaStore()
        else:
            _store = QdrantStore()
    return _store


class ChromaStore:
    def __init__(self):
        import chromadb
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self.collection = self.client.get_or_create_collection(
            name=settings.QDRANT_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("chroma_store_initialised", collection=settings.QDRANT_COLLECTION)

    async def add_chunks(self, document_id: str, chunks: list[dict]):
        ids = [f"{document_id}_{i}" for i in range(len(chunks))]
        embeddings = [c["embedding"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [{
            "document_id": document_id,
            "chunk_index": i,
            "filename": chunks[i].get("filename", ""),
        } for i in range(len(chunks))]

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        log.info("chunks_added", document_id=document_id, count=len(chunks))

    async def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i]
                relevance_score = 1 - distance
                metadata = results["metadatas"][0][i]
                chunks.append({
                    "document_id": metadata.get("document_id", ""),
                    "chunk_index": metadata.get("chunk_index", i),
                    "filename": metadata.get("filename", ""),
                    "text": results["documents"][0][i],
                    "relevance_score": round(relevance_score, 4),
                })
        return chunks

    async def delete_document(self, document_id: str):
        results = self.collection.get(
            where={"document_id": document_id},
            include=[],
        )
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
        log.info("document_deleted_from_store", document_id=document_id)

    async def health_check(self) -> dict:
        count = self.collection.count()
        return {"status": "ok", "documents": count}


class QdrantStore:
    def __init__(self):
        from qdrant_client import QdrantClient
        from qdrant_client.models import VectorParams, Distance

        kwargs = {"url": settings.QDRANT_HOST}
        if settings.QDRANT_API_KEY:
            kwargs["api_key"] = settings.QDRANT_API_KEY

        self.client = QdrantClient(**kwargs)
        self.collection = settings.QDRANT_COLLECTION

        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection not in collections:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
            )
        log.info("qdrant_store_initialised", collection=self.collection)

    async def add_chunks(self, document_id: str, chunks: list[dict]):
        from qdrant_client.models import PointStruct
        points = [
            PointStruct(
                id=f"{document_id}_{i}".replace("-", "")[:32],
                vector=chunks[i]["embedding"],
                payload={
                    "document_id": document_id,
                    "chunk_index": i,
                    "filename": chunks[i].get("filename", ""),
                    "text": chunks[i]["text"],
                },
            )
            for i in range(len(chunks))
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    async def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        results = self.client.search(
            collection_name=self.collection,
            query_vector=query_embedding,
            limit=top_k,
            with_payload=True,
        )
        return [
            {
                "document_id": r.payload.get("document_id", ""),
                "chunk_index": r.payload.get("chunk_index", 0),
                "filename": r.payload.get("filename", ""),
                "text": r.payload.get("text", ""),
                "relevance_score": round(r.score, 4),
            }
            for r in results
        ]

    async def delete_document(self, document_id: str):
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )

    async def health_check(self) -> dict:
        info = self.client.get_collection(self.collection)
        return {"status": "ok", "documents": info.points_count}
