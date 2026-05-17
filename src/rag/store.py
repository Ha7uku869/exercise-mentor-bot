"""Qdrant Cloud にベクトルを保存・検索するモジュール。

--- 技術解説: ベクトルデータベース（Vector DB）とは ---
通常のデータベースはキーワードの完全一致や部分一致で検索するが、
ベクトルデータベースは「意味的な近さ」で検索できる。

例えば「ベンチプレスが伸びない」で検索すると、
過去の「胸のトレーニングが停滞している」という会話もヒットする。
これは両方のテキストの埋め込みベクトルが近いため。

--- 技術解説: Qdrant ---
Qdrant はオープンソースのベクトルデータベース。
Qdrant Cloud を使えば無料枠でマネージドサービスを利用できる。
qdrant_client ライブラリで Python から簡単にアクセスできる。

--- 技術解説: コサイン距離（Cosine Distance） ---
2つのベクトルの「向き」の類似度を測る指標。
値が小さいほど類似度が高い（同じ方向を向いている）。
テキストの意味的類似度を測るのによく使われる。
"""

import logging
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.config import get_settings

logger = logging.getLogger(__name__)

# コレクション名（Qdrant のテーブルに相当）
_COLLECTION_NAME = "conversations"
_KNOWLEDGE_COLLECTION = "knowledge"

# 埋め込みベクトルの次元数（BAAI/bge-small-en-v1.5 の出力次元）
_VECTOR_DIM = 384

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    """Qdrant クライアントを取得する（初回のみ接続を確立）。

    --- 技術解説: コレクションの自動作成 ---
    コレクション（テーブルに相当）が存在しない場合は自動で作成する。
    これにより、初回デプロイ時に手動でコレクションを作る必要がなくなる。
    """
    global _client
    if _client is None:
        settings = get_settings()
        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        # コレクションが存在しない場合は作成
        _ensure_collection(_client)
    return _client


def _ensure_collection(client: QdrantClient) -> None:
    """コレクションが存在しなければ作成する。"""
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if _COLLECTION_NAME not in collection_names:
        logger.info("Qdrant コレクション '%s' を作成します", _COLLECTION_NAME)
        client.create_collection(
            collection_name=_COLLECTION_NAME,
            vectors_config=VectorParams(
                size=_VECTOR_DIM,
                distance=Distance.COSINE,
            ),
        )
        logger.info("コレクション '%s' を作成しました", _COLLECTION_NAME)

    # user_id フィールドにインデックスを作成（フィルター検索に必要）
    client.create_payload_index(
        collection_name=_COLLECTION_NAME,
        field_name="user_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )


def _ensure_knowledge_collection(client: QdrantClient) -> None:
    """知識ベースコレクションが存在しなければ作成する。

    --- 技術解説: 会話と知識を別コレクションにする理由 ---
    会話データは user_id でフィルターし、知識データは全ユーザー共通。
    コレクションを分けることで、検索時のフィルター条件がシンプルになり、
    将来的に知識だけを更新・リセットすることも容易になる。
    """
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if _KNOWLEDGE_COLLECTION not in collection_names:
        logger.info("Qdrant コレクション '%s' を作成します", _KNOWLEDGE_COLLECTION)
        client.create_collection(
            collection_name=_KNOWLEDGE_COLLECTION,
            vectors_config=VectorParams(
                size=_VECTOR_DIM,
                distance=Distance.COSINE,
            ),
        )
        logger.info("コレクション '%s' を作成しました", _KNOWLEDGE_COLLECTION)

    # category フィールドにインデックスを作成
    client.create_payload_index(
        collection_name=_KNOWLEDGE_COLLECTION,
        field_name="category",
        field_schema=PayloadSchemaType.KEYWORD,
    )


def upsert_knowledge(
    text: str, category: str, source: str, vector: list[float]
) -> None:
    """知識エントリをベクトルと一緒に Qdrant に保存する。

    Args:
        text: 知識のテキスト
        category: カテゴリ（例: "トレーニングボリューム"）
        source: 出典（論文名等）
        vector: テキストの埋め込みベクトル（384次元）
    """
    client = _get_client()
    _ensure_knowledge_collection(client)

    point = PointStruct(
        id=uuid.uuid4().hex,
        vector=vector,
        payload={
            "text": text,
            "category": category,
            "source": source,
            "timestamp": int(time.time()),
        },
    )

    client.upsert(
        collection_name=_KNOWLEDGE_COLLECTION,
        points=[point],
    )


def search_knowledge(vector: list[float], limit: int = 3) -> list[dict]:
    """クエリに類似する知識をベクトル検索で取得する。

    Args:
        vector: 検索クエリの埋め込みベクトル
        limit: 返す結果の最大数

    Returns:
        類似度が高い順に並んだ知識データのリスト。
        各要素は {"text": str, "category": str, "source": str, "score": float} の辞書。

    --- 技術解説: 知識検索にフィルターがない理由 ---
    会話検索では user_id でフィルターするが、知識は全ユーザー共通なので
    フィルターなしで純粋にベクトルの類似度だけで検索する。
    """
    client = _get_client()
    _ensure_knowledge_collection(client)

    results = client.query_points(
        collection_name=_KNOWLEDGE_COLLECTION,
        query=vector,
        limit=limit,
    )

    return [
        {
            "text": hit.payload["text"],
            "category": hit.payload.get("category", ""),
            "source": hit.payload.get("source", ""),
            "score": hit.score,
        }
        for hit in results.points
    ]


def upsert(user_id: str, text: str, role: str, vector: list[float]) -> None:
    """会話メッセージをベクトルと一緒に Qdrant に保存する。

    Args:
        user_id: LINE ユーザーID
        text: メッセージのテキスト
        role: メッセージの種類（"user" または "assistant"）
        vector: テキストの埋め込みベクトル（384次元）

    --- 技術解説: ポイント（Point）とペイロード（Payload） ---
    Qdrant ではデータの1件を「ポイント」と呼ぶ。
    各ポイントは以下で構成される:
    - id: ユニークな識別子（UUID を使用）
    - vector: 埋め込みベクトル（検索に使用）
    - payload: メタデータ（user_id, text, role 等の付随情報）
    """
    client = _get_client()

    point = PointStruct(
        id=uuid.uuid4().hex,
        vector=vector,
        payload={
            "user_id": user_id,
            "text": text,
            "role": role,
            "timestamp": int(time.time()),
        },
    )

    client.upsert(
        collection_name=_COLLECTION_NAME,
        points=[point],
    )


def search(vector: list[float], user_id: str, limit: int = 3) -> list[dict]:
    """類似する過去の会話をベクトル検索で取得する。

    Args:
        vector: 検索クエリの埋め込みベクトル
        user_id: 検索対象のユーザーID（他のユーザーの会話は検索しない）
        limit: 返す結果の最大数

    Returns:
        類似度が高い順に並んだ会話データのリスト。
        各要素は {"text": str, "role": str, "timestamp": int, "score": float} の辞書。

    --- 技術解説: フィルター付きベクトル検索 ---
    ベクトル検索にフィルターを組み合わせることで、
    「意味的に近い」かつ「同じユーザーの」会話だけを取得できる。
    これにより、ユーザー A の会話がユーザー B の検索結果に
    混入することを防ぐ（プライバシー保護）。
    """
    client = _get_client()

    results = client.query_points(
        collection_name=_COLLECTION_NAME,
        query=vector,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id),
                )
            ]
        ),
        limit=limit,
    )

    return [
        {
            "text": hit.payload["text"],
            "role": hit.payload["role"],
            "timestamp": hit.payload.get("timestamp", 0),
            "score": hit.score,
        }
        for hit in results.points
    ]
