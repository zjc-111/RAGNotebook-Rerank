"""本地 Embedding + Rerank 服务，兼容项目现有 OpenAI/Rerank 客户端。"""
import asyncio
import os
from contextlib import asynccontextmanager

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import CrossEncoder, SentenceTransformer

MODEL_ROOT = os.getenv("LOCAL_MODEL_ROOT", r"D:\RAGNotebookWork\models\models")
EMBED_MODEL = os.getenv(
    "LOCAL_EMBED_MODEL",
    os.path.join(MODEL_ROOT, "BAAI--bge-small-zh-v1.5", "snapshots", "master"),
)
RERANK_MODEL = os.getenv(
    "LOCAL_RERANK_MODEL",
    os.path.join(MODEL_ROOT, "BAAI--bge-reranker-base", "snapshots", "master"),
)
EMBED_NAME = os.path.basename(EMBED_MODEL) if os.path.isdir(EMBED_MODEL) else EMBED_MODEL
RERANK_NAME = os.path.basename(RERANK_MODEL) if os.path.isdir(RERANK_MODEL) else RERANK_MODEL
DEVICE = os.getenv("LOCAL_MODEL_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")

embedder: SentenceTransformer | None = None
reranker: CrossEncoder | None = None
model_lock = asyncio.Lock()


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str | None = None


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    model: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global embedder, reranker
    print(f"[startup] embedding={EMBED_MODEL} rerank={RERANK_MODEL} device={DEVICE}", flush=True)
    embedder = SentenceTransformer(EMBED_MODEL, device=DEVICE)
    reranker = CrossEncoder(
        RERANK_MODEL,
        device=DEVICE,
        max_length=512,
        activation_fn=torch.nn.Sigmoid(),
    )
    print(f"[ready] dimensions={embedder.get_sentence_embedding_dimension()}", flush=True)
    yield


app = FastAPI(title="RAGNotebook Local Models", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok" if embedder is not None and reranker is not None else "loading",
        "device": DEVICE,
        "embedding_model": EMBED_NAME,
        "rerank_model": RERANK_NAME,
        "dimensions": embedder.get_sentence_embedding_dimension() if embedder else None,
    }


@app.post("/v1/embeddings")
async def create_embeddings(request: EmbeddingRequest):
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedding model is not ready")
    texts = [request.input] if isinstance(request.input, str) else request.input
    if not texts:
        return {"object": "list", "data": [], "model": EMBED_NAME}

    async with model_lock:
        vectors = await asyncio.to_thread(
            embedder.encode,
            texts,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": vector.tolist()}
            for index, vector in enumerate(vectors)
        ],
        "model": request.model or EMBED_NAME,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@app.post("/reranks")
async def rerank_documents(request: RerankRequest):
    if reranker is None:
        raise HTTPException(status_code=503, detail="Rerank model is not ready")
    if not request.documents:
        return {"results": [], "model": request.model or RERANK_NAME}

    pairs = [(request.query, document) for document in request.documents]
    async with model_lock:
        scores = await asyncio.to_thread(
            reranker.predict,
            pairs,
            batch_size=16,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    return {
        "results": [
            {"index": index, "relevance_score": float(score)}
            for index, score in enumerate(scores)
        ],
        "model": request.model or RERANK_NAME,
    }


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("LOCAL_MODEL_HOST", "127.0.0.1"),
        port=int(os.getenv("LOCAL_MODEL_PORT", "18090")),
        log_level="info",
    )
