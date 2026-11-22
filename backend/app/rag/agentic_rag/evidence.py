import re

from app.rag.agentic_rag.schemas import Evidence

_SOURCE_LABELS = {
    "note": "笔记",
    "knowledge_base": "知识库",
    "graph": "知识图谱",
    "web": "外部搜索",
}

# 近重复阈值：字符二元组 Jaccard ≥ 0.9 视为同义片段（检索/图谱扩展常召回近似重叠块）
_NEAR_DUP_THRESHOLD = 0.9
_NEAR_DUP_MIN_CHARS = 30


def _normalized_content(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip().lower()


def _char_bigrams(text: str) -> frozenset[str]:
    """按字符二元组建集合（中文无需分词，对改写/标点差异更鲁棒）。"""
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 2:
        return frozenset()
    return frozenset(compact[i:i + 2] for i in range(len(compact) - 1))


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def merge_evidence(evidences: list[Evidence], limit: int = 8) -> list[Evidence]:
    merged: list[Evidence] = []
    seen_source_ids: set[tuple[str, str]] = set()
    seen_content: set[str] = set()
    kept_bigrams: list[frozenset[str]] = []

    for evidence in evidences:
        source_id = (evidence.source, evidence.id)
        if source_id in seen_source_ids:
            continue

        content_key = _normalized_content(evidence.content)
        if content_key and content_key in seen_content:
            continue

        # 近重复过滤：同一事实被不同来源/切片重复召回时只保留首条，节省上下文预算
        grams: frozenset[str] = frozenset()
        if len(content_key) >= _NEAR_DUP_MIN_CHARS:
            grams = _char_bigrams(content_key)
            if any(_jaccard(grams, previous) >= _NEAR_DUP_THRESHOLD for previous in kept_bigrams):
                continue

        seen_source_ids.add(source_id)
        if content_key:
            seen_content.add(content_key)
        if grams:
            kept_bigrams.append(grams)
        merged.append(evidence)

        if len(merged) >= limit:
            break

    return merged


def format_evidence_context(
    evidences: list[Evidence],
    max_chars: int = 6000,
    per_evidence_chars: int = 1500,
) -> str:
    parts: list[str] = []
    used = 0

    for index, evidence in enumerate(evidences, start=1):
        label = _SOURCE_LABELS[evidence.source]
        header = f"[{index}] 来源：{label}《{evidence.title}》"
        lines = [header]
        if evidence.url:
            lines.append(f"URL：{evidence.url}")
        content = evidence.content
        # 单条预算：超长切片截断，避免一条证据吃满总预算、挤掉其他来源
        if per_evidence_chars > 0 and len(content) > per_evidence_chars:
            content = content[:per_evidence_chars] + "…（内容已截断）"
        lines.append(content)
        block = "\n".join(lines)
        separator = "\n\n" if parts else ""

        if used + len(separator) + len(block) > max_chars:
            break

        parts.append(block)
        used += len(separator) + len(block)

    return "\n\n".join(parts)
