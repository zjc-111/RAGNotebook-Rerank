"""检索链路优化测试：两阶段精排（召回池扩展 + rerank + 阈值）与 Redis 结果缓存。"""
import pytest

from app.core.settings import settings
from app.graph.schemas.graph import ChunkHit
from app.rag.agentic_rag.evidence import format_evidence_context, merge_evidence
from app.rag.agentic_rag.local_retriever import LocalRetriever
from app.rag.agentic_rag.schemas import Evidence, RetrievalStep


def _hit(chunk_id, text, score, kind="doc", source_id="md5-1", source_name="Guide.pdf"):
    return ChunkHit(id=chunk_id, kind=kind, source_id=source_id, source_name=source_name,
                    chunk_index=0, text=text, score=score, metadata={"vector_score": score})


class FakeStore:
    def __init__(self, hits):
        self.hits = hits
        self.chunk_calls = []

    async def search_chunks(self, user_id, query_embedding, text_query, kinds, limit):
        self.chunk_calls.append({"user_id": user_id, "kinds": kinds, "limit": limit})
        return self.hits[:limit]


class FakeSession:
    def __init__(self, store=None):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeReranker:
    def __init__(self, scores=None, fail=False):
        self.scores = scores or []
        self.fail = fail
        self.calls = []

    async def score_documents(self, query, documents):
        self.calls.append({"query": query, "documents": documents})
        if self.fail:
            return None
        return self.scores[:len(documents)]


@pytest.fixture(autouse=True)
def isolate_rag_settings(monkeypatch):
    monkeypatch.setattr(settings, "RAG_RERANK_ENABLED", False)
    monkeypatch.setattr(settings, "RAG_CACHE_ENABLED", False)
    monkeypatch.setattr(settings, "RAG_RECALL_MULTIPLIER", 3)
    monkeypatch.setattr(settings, "RAG_RERANK_MAX_CANDIDATES", 30)
    monkeypatch.setattr(settings, "RAG_RERANK_MIN_SCORE", 0.0)


@pytest.fixture
def patch_store(monkeypatch):
    def _patch(store):
        import app.rag.agentic_rag.local_retriever as lm
        monkeypatch.setattr(lm, "get_graph_store", lambda session=None: store)
    return _patch


@pytest.fixture
def no_embed(monkeypatch):
    from app.core import background_init

    monkeypatch.setattr(background_init.init_manager, "embed_model", None)


@pytest.mark.asyncio
async def test_rerank_expands_recall_pool_and_reorders(patch_store, no_embed):
    store = FakeStore([
        _hit("c1", "chunk one", 0.9),
        _hit("c2", "chunk two", 0.8),
        _hit("c3", "chunk three", 0.7),
    ])
    patch_store(store)
    reranker = FakeReranker(scores=[0.1, 0.95, 0.2])
    retriever = LocalRetriever(session_factory=FakeSession, reorder_service=reranker)

    evidences = await retriever.search(
        "user-1", [RetrievalStep(tool="search_knowledge_base", query="精排", top_k=2)])

    # 召回池 = top_k × 默认倍率 3，再精排截断到 top_k
    assert store.chunk_calls[0]["limit"] == 6
    assert reranker.calls[0]["query"] == "精排"
    assert [item.id for item in evidences] == ["c2", "c3"]
    assert [item.score for item in evidences] == [0.95, 0.2]
    assert evidences[0].metadata["rrf_score"] == 0.8
    assert evidences[0].metadata["rerank_score"] == 0.95


@pytest.mark.asyncio
async def test_rerank_failure_falls_back_to_rrf_order(patch_store, no_embed):
    store = FakeStore([
        _hit("c1", "chunk one", 0.9),
        _hit("c2", "chunk two", 0.8),
    ])
    patch_store(store)
    retriever = LocalRetriever(session_factory=FakeSession, reorder_service=FakeReranker(fail=True))

    evidences = await retriever.search(
        "user-1", [RetrievalStep(tool="hybrid_search", query="降级", top_k=2)])

    assert [item.id for item in evidences] == ["c1", "c2"]
    assert [item.score for item in evidences] == [0.9, 0.8]


@pytest.mark.asyncio
async def test_rerank_threshold_filters_low_scores(patch_store, no_embed, monkeypatch):
    monkeypatch.setattr(settings, "RAG_RERANK_MIN_SCORE", 0.5, raising=False)
    store = FakeStore([
        _hit("c1", "chunk one", 0.9),
        _hit("c2", "chunk two", 0.8),
        _hit("c3", "chunk three", 0.7),
    ])
    patch_store(store)
    reranker = FakeReranker(scores=[0.1, 0.9, 0.2])
    retriever = LocalRetriever(session_factory=FakeSession, reorder_service=reranker)

    evidences = await retriever.search(
        "user-1", [RetrievalStep(tool="hybrid_search", query="阈值", top_k=2)])

    assert [item.id for item in evidences] == ["c2"]


@pytest.mark.asyncio
async def test_rerank_threshold_never_returns_empty(patch_store, no_embed, monkeypatch):
    monkeypatch.setattr(settings, "RAG_RERANK_MIN_SCORE", 0.99, raising=False)
    store = FakeStore([_hit("c1", "chunk one", 0.9), _hit("c2", "chunk two", 0.8)])
    patch_store(store)
    retriever = LocalRetriever(
        session_factory=FakeSession, reorder_service=FakeReranker(scores=[0.1, 0.2]))

    evidences = await retriever.search(
        "user-1", [RetrievalStep(tool="hybrid_search", query="兜底", top_k=2)])

    # 全被阈值过滤时兜底返回精排后的 top_k，避免无证据
    assert [item.id for item in evidences] == ["c2", "c1"]


@pytest.mark.asyncio
async def test_without_rerank_keeps_original_top_k(patch_store, no_embed):
    store = FakeStore([_hit("c1", "chunk one", 0.9), _hit("c2", "chunk two", 0.8)])
    patch_store(store)
    retriever = LocalRetriever(session_factory=FakeSession)

    await retriever.search(
        "user-1", [RetrievalStep(tool="hybrid_search", query="原链路", top_k=2)])

    assert store.chunk_calls[0]["limit"] == 2


@pytest.mark.asyncio
async def test_cache_hit_skips_store_search(patch_store, no_embed, monkeypatch):
    import app.rag.agentic_rag.local_retriever as lm

    cache: dict[str, list[dict]] = {}

    async def fake_get(key):
        return cache.get(key)

    async def fake_set(key, value, expire=3600):
        cache[key] = value
        return True

    monkeypatch.setattr(lm, "get_redis_cache_json", fake_get)
    monkeypatch.setattr(lm, "set_redis_cache", fake_set)

    store = FakeStore([_hit("c1", "cached chunk", 0.9)])
    patch_store(store)
    retriever = LocalRetriever(session_factory=FakeSession, cache_enabled=True)
    step = RetrievalStep(tool="hybrid_search", query="同一 个 问题", top_k=2)

    first = await retriever.search("user-1", [step])
    second = await retriever.search("user-1", [step])

    assert len(store.chunk_calls) == 1
    assert [item.id for item in first] == [item.id for item in second] == ["c1"]
    assert first[0].content == second[0].content == "cached chunk"


@pytest.mark.asyncio
async def test_cache_is_isolated_by_user(patch_store, no_embed, monkeypatch):
    import app.rag.agentic_rag.local_retriever as lm

    cache: dict[str, list[dict]] = {}

    async def fake_get(key):
        return cache.get(key)

    async def fake_set(key, value, expire=3600):
        cache[key] = value
        return True

    monkeypatch.setattr(lm, "get_redis_cache_json", fake_get)
    monkeypatch.setattr(lm, "set_redis_cache", fake_set)

    store = FakeStore([_hit("c1", "chunk", 0.9)])
    patch_store(store)
    retriever = LocalRetriever(session_factory=FakeSession, cache_enabled=True)
    step = RetrievalStep(tool="hybrid_search", query="隔离", top_k=2)

    await retriever.search("user-1", [step])
    await retriever.search("user-2", [step])

    assert len(store.chunk_calls) == 2


def test_merge_evidence_drops_near_duplicate_chunks():
    base = "RAG 检索增强生成通过向量召回与重排序提升回答准确性，本项目在检索层引入两阶段精排策略。"
    variant = "RAG 检索增强生成通过向量召回与重排序提升回答准确性，本项目在检索层引入两阶段精排策略！"
    evidences = [
        Evidence(id="1", source="knowledge_base", title="Guide.pdf", content=base),
        Evidence(id="2", source="note", title="笔记", content=variant),
        Evidence(id="3", source="note", title="其他", content="MySQL 负责持久化笔记与对话历史，Neo4j 存储知识图谱。"),
    ]

    merged = merge_evidence(evidences)

    assert [item.id for item in merged] == ["1", "3"]


def test_format_context_truncates_single_long_evidence():
    evidences = [
        Evidence(id="1", source="knowledge_base", title="Long.pdf", content="长" * 400),
        Evidence(id="2", source="note", title="Short", content="短证据"),
    ]

    context = format_evidence_context(evidences, max_chars=600, per_evidence_chars=100)

    assert "…（内容已截断）" in context
    assert "[1] 来源：知识库《Long.pdf》" in context
    # 单条截断后仍能容纳第二条证据，而不是整条被预算挤掉
    assert "[2] 来源：笔记《Short》" in context
    assert len(context) <= 600
