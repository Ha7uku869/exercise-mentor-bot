"""知識ベースを Qdrant にシード（初期投入）するスクリプト。

使い方:
    python -m scripts.seed_knowledge

--- 技術解説: シードスクリプトとは ---
データベースに初期データを投入するスクリプト。
知識データを更新したい場合はこのスクリプトを再実行すればよい。
既存の知識コレクションを一度削除してから再投入するため、
常に knowledge_data.py の内容と同期される。
"""

import asyncio
import logging
import sys

from dotenv import load_dotenv

# .env を読み込む（src.config より先に実行する必要がある）
load_dotenv()

from src.rag.embedder import embed
from src.rag.knowledge_data import KNOWLEDGE_ENTRIES
from src.rag.store import _get_client, _KNOWLEDGE_COLLECTION, upsert_knowledge

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def seed() -> None:
    """知識データを埋め込みベクトル化して Qdrant に保存する。"""
    # 既存の知識コレクションを削除して再作成（冪等性の確保）
    client = _get_client()
    try:
        client.delete_collection(collection_name=_KNOWLEDGE_COLLECTION)
        logger.info("既存の '%s' コレクションを削除しました", _KNOWLEDGE_COLLECTION)
    except Exception:
        pass  # コレクションが存在しない場合は無視

    total = len(KNOWLEDGE_ENTRIES)
    logger.info("知識エントリ %d 件を投入します...", total)

    for i, entry in enumerate(KNOWLEDGE_ENTRIES, 1):
        text = entry["text"]
        category = entry["category"]
        source = entry["source"]
        # embed_text（英語サマリー）があればそれでベクトル化、なければ text を使う
        embed_source = entry.get("embed_text", text)

        vector = await embed(embed_source)
        upsert_knowledge(text, category, source, vector)
        logger.info("  [%d/%d] %s", i, total, category)

    logger.info("完了！ %d 件の知識を Qdrant に保存しました。", total)


if __name__ == "__main__":
    asyncio.run(seed())
