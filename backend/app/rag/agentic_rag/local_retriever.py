"""本地检索器：全部走 Neo4j 图存储（种子 = Chunk 向量+全文，图扩展 = 实体/关系/提及 chunk）。

- search_notes          → search_chunks(kinds=["note"])
- search_knowledge_base → search_chunks(kinds=["doc"])
- hybrid_search         → search_chunks(kinds=None)（单次调用，RRF 已融合笔记与文档）
- search_graph          → 实体候选词匹配 → 实体证据 + 命中实体的 chunk 片段补充

工具名保持不变，执行层为图存储检索。
"""
import asyncio
import hashlib
import re
import time
from collections.abc import Callable
from typing import Any

from app.core.logger_handler import logger
from app.core.settings import settings
from app.db.db_config import AsyncSessionLocal
from app.db.redis_config import get_redis_cache_json, set_redis_cache
from app.graph.schemas.graph import ChunkHit
from app.graph.storage import get_graph_store
from app.graph.storage.neo4j_graph_store import Neo4jGraphStore
from app.rag.agentic_rag.query_entity_extractor import QueryEntityExtractor
from app.rag.agentic_rag.schemas import Evidence, RetrievalStep

_CACHE_PREFIX = "rag:search"

_NORMALIZE_RE = re.compile(r"[\s，。！？!?、；：:;，,．.、'\"“”‘’（）()【】\[\]]+")


def _normalize_query(query: str) -> str:
    """与 search_rag 护栏一致的口径：去空白/标点 + 小写，提升缓存命中率。"""
    return _NORMALIZE_RE.sub("", query or "").lower()


class LocalRetriever:
    def __init__(
        self,
        note_service: Any | None = None,
        session_factory: Callable[[], Any] = AsyncSessionLocal,
        query_entity_extractor: QueryEntityExtractor | None = None,
        reorder_service: Any | None = None,
        cache_enabled: bool | None = None,
    ):
        self.note_service = note_service
        self.session_factory = session_factory
        self.query_entity_extractor = query_entity_extractor
        self.reorder_service = reorder_service
        self.cache_enabled = cache_enabled

    async def search(self, user_id: str, steps: list[RetrievalStep]) -> list[Evidence]:
        evidences: list[Evidence] = []

        for step in steps:
            try:
                if step.tool == "search_notes":
                    evidences.extend(await self._search_chunks(user_id, step, kinds=["note"]))
                elif step.tool == "search_knowledge_base":
                    evidences.extend(await self._search_chunks(user_id, step, kinds=["doc"]))
                elif step.tool == "search_graph":
                    evidences.extend(await self._search_graph(user_id, step))
                elif step.tool == "hybrid_search":
                    evidences.extend(await self._search_chunks(user_id, step, kinds=None))
            except Exception as e:
                # 单步检索失败（含 Neo4j 不可用）不阻塞其余步骤：聊天主流程功能降级
                logger.warning(f"检索步骤 {step.tool} 失败，已跳过: {e}")

        return evidences

    async def _search_chunks(self, user_id: str, step: RetrievalStep,
                             kinds: list[str] | None) -> list[Evidence]:
        """种子检索：向量 + 全文（store 内 RRF 融合）→ rerank 精排 → 截断 top_k。"""
        t0 = time.perf_counter()
        cache_key = self._cache_key(user_id, step, kinds)
        if self._cache_on():
            cached = await self._cache_get(cache_key)
            if cached is not None:
                logger.info(
                    f"【RAG耗时】search_chunks tool={step.tool} cache=hit "
                    f"total={(time.perf_counter() - t0) * 1000:.0f}ms hits={len(cached)}"
                )
                return [self._chunk_to_evidence(hit) for hit in cached]

        async with self.session_factory() as db:
            store = get_graph_store(db)
            t_emb = time.perf_counter()
            embedding = await self._query_embedding(step.query)
            emb_ms = (time.perf_counter() - t_emb) * 1000
            t_search = time.perf_counter()
            recall_limit = self._recall_limit(step.top_k)
            hits = await store.search_chunks(user_id, embedding, step.query, kinds, recall_limit)
            search_ms = (time.perf_counter() - t_search) * 1000
            t_rerank = time.perf_counter()
            hits = await self._rerank_hits(step.query, hits, step.top_k)
            rerank_ms = (time.perf_counter() - t_rerank) * 1000
            total_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                f"【RAG耗时】search_chunks tool={step.tool} kinds={kinds} total={total_ms:.0f}ms "
                f"embed={emb_ms:.0f}ms store_search={search_ms:.0f}ms rerank={rerank_ms:.0f}ms "
                f"recall={recall_limit} hits={len(hits)} embed_none={embedding is None}"
            )
            if self._cache_on():
                await self._cache_set(cache_key, hits)
            return [self._chunk_to_evidence(hit) for hit in hits]

    def _rerank_available(self) -> bool:
        """显式注入重排器（测试/自定义）或配置了云端 rerank 才启用。"""
        if self.reorder_service is not None:
            return True
        return bool(
            settings.RAG_RERANK_ENABLED
            and settings.RERANKER_API_BASE_URL
            and settings.RERANKER_API_KEY
        )

    def _recall_limit(self, top_k: int) -> int:
        """精排开启时扩大召回池（top_k×倍率），否则维持原 top_k。"""
        if not self._rerank_available():
            return top_k
        multiplier = max(1, settings.RAG_RECALL_MULTIPLIER)
        max_candidates = max(top_k, settings.RAG_RERANK_MAX_CANDIDATES)
        return min(top_k * multiplier, max_candidates)

    async def _rerank_hits(self, query: str, hits: list[ChunkHit], top_k: int) -> list[ChunkHit]:
        """对 RRF 召回结果做 cross-encoder 精排；任何失败都按原顺序降级。"""
        if len(hits) <= 1 or not self._rerank_available():
            return hits[:top_k]

        service = self.reorder_service
        if service is None:
            from app.core.background_init import init_manager

            service = init_manager.reorder_service
        if service is None:
            return hits[:top_k]

        documents = [(hit.text or "")[:2000] for hit in hits]
        scores = await service.score_documents(query, documents)
        if scores is None or len(scores) != len(hits):
            return hits[:top_k]

        reranked: list[ChunkHit] = []
        for hit, score in zip(hits, scores):
            metadata = {**hit.metadata, "rrf_score": hit.score, "rerank_score": score}
            reranked.append(hit.model_copy(update={"score": score, "metadata": metadata}))
        reranked.sort(key=lambda item: item.score if item.score is not None else 0.0, reverse=True)

        threshold = settings.RAG_RERANK_MIN_SCORE
        kept = [hit for hit in reranked if hit.score is None or hit.score >= threshold]
        # 阈值过严导致全被过滤时兜底，避免整轮检索无证据
        return (kept or reranked)[:top_k]

    def _cache_on(self) -> bool:
        return self.cache_enabled if self.cache_enabled is not None else settings.RAG_CACHE_ENABLED

    def _cache_key(self, user_id: str, step: RetrievalStep, kinds: list[str] | None) -> str:
        raw = "|".join([
            _normalize_query(step.query),
            str(step.top_k),
            ",".join(sorted(kinds)) if kinds else "all",
            "rerank" if self._rerank_available() else "raw",
        ])
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        return f"{_CACHE_PREFIX}:{user_id}:{digest}"

    @staticmethod
    async def _cache_get(cache_key: str) -> list[ChunkHit] | None:
        try:
            payload = await get_redis_cache_json(cache_key)
            if payload is None:
                return None
            return [ChunkHit.model_validate(item) for item in payload]
        except Exception as e:
            logger.warning(f"检索缓存读取失败，回源检索: {e}")
            return None

    @staticmethod
    async def _cache_set(cache_key: str, hits: list[ChunkHit]) -> None:
        try:
            await set_redis_cache(cache_key, [hit.model_dump() for hit in hits],
                                  expire=settings.RAG_CACHE_TTL_S)
        except Exception as e:
            logger.warning(f"检索缓存写入失败，忽略: {e}")

    async def _search_graph(self, user_id: str, step: RetrievalStep) -> list[Evidence]:
        """从知识图谱检索：先抽实体候选词匹配实体（证据=描述+类型+别名+关联来源），
        Neo4j 主路径再补命中实体所在的 chunk 片段，让图谱证据有正文可引。"""
        evidences: list[Evidence] = []
        t0 = time.perf_counter()
        t_extract = time.perf_counter()
        names = await self._entity_candidates(step.query)
        extract_ms = (time.perf_counter() - t_extract) * 1000
        matched_entity_ids: list[str] = []
        async with self.session_factory() as db:
            store = get_graph_store(db)
            seen_entity_ids: set[str] = set()
            for name in names:
                entities = await store.search_entities(user_id, name, limit=step.top_k)
                for entity in entities:
                    if entity.id in seen_entity_ids:
                        continue
                    seen_entity_ids.add(entity.id)
                    matched_entity_ids.append(entity.id)
                    links = await store.get_entity_notes(user_id, entity.id)
                    noted: set[str] = set()
                    notes: list[str] = []
                    for link in links:
                        label = link.source_name or link.note_id
                        if label in noted:
                            continue
                        noted.add(label)
                        notes.append(label)
                    title = entity.display_name or entity.name
                    content = entity.description or ""
                    if content:
                        content = f"{content}（类型：{entity.type_id or '未分类'}；别名：{', '.join(entity.aliases) if entity.aliases else '—'}）"
                    if notes:
                        content = f"{content}\n关联来源：{'、'.join(notes)}" if content else "关联来源：" + "、".join(notes)
                    evidences.append(Evidence(
                        id=entity.id,
                        source="graph",
                        title=title,
                        content=content or title,
                        metadata={"type_id": entity.type_id, "aliases": entity.aliases},
                    ))

            if isinstance(store, Neo4jGraphStore) and matched_entity_ids:
                try:
                    chunk_hits = await store.get_chunks_mentioning(
                        user_id, matched_entity_ids, limit=6)
                except NotImplementedError:
                    chunk_hits = []
                evidences.extend(self._chunk_to_evidence(hit) for hit in chunk_hits)
        graph_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            f"【RAG耗时】search_graph total={graph_ms:.0f}ms entity_extract={extract_ms:.0f}ms "
            f"names={names} entities={len(matched_entity_ids)} evidences={len(evidences)}"
        )
        return evidences

    async def _entity_candidates(self, query: str) -> list[str]:
        """从问句抽实体候选词。优先 LLM，失败回落规则拆词。"""
        extractor = self.query_entity_extractor or QueryEntityExtractor()
        try:
            return await extractor.extract(query)
        except Exception as e:
            from app.core.logger_handler import logger

            logger.warning(f"查询实体抽取失败，回落规则: {query}: {e}")
            return QueryEntityExtractor._fallback_candidates(query)

    @staticmethod
    async def _query_embedding(query: str) -> list[float] | None:
        """query 向量实时计算（失败返回 None，退化为纯全文检索）。"""
        from app.core.background_init import init_manager

        model = init_manager.embed_model
        if model is None or not query:
            return None
        try:
            return await asyncio.to_thread(model.embed_query, query)
        except Exception:
            return None

    @staticmethod
    def _chunk_to_evidence(hit: ChunkHit) -> Evidence:
        return Evidence(
            id=hit.id,
            source="note" if hit.kind == "note" else "knowledge_base",
            title=hit.source_name or ("笔记" if hit.kind == "note" else "知识库文档"),
            content=hit.text,
            score=hit.score,
            metadata={"source_id": hit.source_id, "chunk_index": hit.chunk_index, **hit.metadata},
        )
