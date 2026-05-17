"""RAG（検索拡張生成）のメインモジュール。

embedder と store を組み合わせて、会話の保存と類似検索を行う。

--- 技術解説: RAG（Retrieval-Augmented Generation）とは ---
LLM に質問を投げる前に、関連する情報をデータベースから検索（Retrieval）し、
その情報をプロンプトに追加（Augmented）して応答を生成（Generation）する手法。

通常の LLM は学習データに含まれない情報は回答できないが、
RAG を使うと外部データベースの情報を活用できる。

このプロジェクトでは、過去の会話を検索して LLM のプロンプトに追加することで、
「以前の会話を踏まえた応答」を実現する。

例: ユーザーが「ベンチプレスが伸びない」と言った時、
過去に「胸トレでフォームを見直した」という会話があれば、
それを参考にした応答を生成できる。
"""

import logging

from src.rag.embedder import embed
from src.rag.store import search, search_knowledge, upsert

logger = logging.getLogger(__name__)

# --- 日本語 → 英語キーワードマッピング ---
# 英語埋め込みモデルでの検索精度を向上させるため、
# よく使われる日本語キーワードを英語に変換して検索クエリに追加する。
_JA_TO_EN_KEYWORDS: dict[str, str] = {
    "ベンチプレス": "bench press",
    "スクワット": "squat",
    "デッドリフト": "deadlift",
    "タンパク質": "protein intake how much",
    "プロテイン": "protein intake how much",
    "たんぱく質": "protein intake how much",
    "カロリー": "calories bulking cutting",
    "増量": "bulking calories surplus",
    "減量": "cutting calories deficit fat loss",
    "筋肉痛": "muscle soreness DOMS",
    "フォーム": "form technique",
    "怪我": "injury prevention",
    "停滞": "plateau stuck not improving",
    "伸びない": "plateau stuck not improving strength",
    "伸び悩": "plateau stuck not improving",
    "サボ": "skip gym rest day motivation",
    "休み": "rest day recovery",
    "やる気": "motivation consistency habit",
    "モチベ": "motivation consistency habit",
    "睡眠": "sleep recovery growth hormone",
    "寝不足": "sleep deprivation tired",
    "セット": "sets volume training",
    "頻度": "frequency how often train",
    "比較": "comparing others genetics social media",
    "才能": "genetics talent natural ability",
    "食事": "nutrition diet protein calories",
    "栄養": "nutrition diet protein calories",
}


def _augment_query_with_english(query: str) -> str:
    """日本語クエリに英語キーワードを追加して検索精度を向上させる。

    --- 技術解説: クエリ拡張（Query Expansion） ---
    英語特化の埋め込みモデルで日本語テキストを検索する場合、
    日本語 → 英語の変換をクエリ側で行うことで検索精度が向上する。
    完全な翻訳は不要で、キーワードレベルの対応で十分な効果がある。
    """
    en_parts = []
    for ja_keyword, en_keyword in _JA_TO_EN_KEYWORDS.items():
        if ja_keyword in query:
            en_parts.append(en_keyword)

    if en_parts:
        return query + " " + " ".join(en_parts)
    return query


async def store_message(user_id: str, text: str, role: str) -> None:
    """会話メッセージを埋め込みベクトル化して Qdrant に保存する。

    Args:
        user_id: LINE ユーザーID
        text: メッセージのテキスト
        role: "user" または "assistant"

    --- 技術解説: 非同期での保存 ---
    ベクトルの生成と保存は応答速度に影響するため、
    本番環境ではバックグラウンドタスクとして実行するのが理想的。
    ただし MVP では簡潔さを優先して同期的に実行する。
    """
    try:
        vector = await embed(text)
        upsert(user_id, text, role, vector)
    except Exception:
        # RAG の保存失敗はユーザー体験に直接影響しないため、
        # ログに記録して処理を継続する
        logger.exception("RAG への会話保存に失敗（user_id=%s, role=%s）", user_id, role)


async def retrieve_similar(
    user_id: str, query: str, limit: int = 3
) -> list[str]:
    """クエリに類似する過去の会話を検索して返す。

    Args:
        user_id: 検索対象のユーザーID
        query: 検索クエリ（通常はユーザーの最新メッセージ）
        limit: 返す結果の最大数

    Returns:
        類似度が高い過去の会話テキストのリスト。
        検索に失敗した場合は空リストを返す。

    --- 技術解説: なぜ空リストを返す？ ---
    RAG は応答の品質を向上させる「補助機能」であるため、
    RAG が失敗しても基本的な応答は生成できるべき。
    エラー時に空リストを返すことで、RAG なしでも動作を継続できる。
    これは「graceful degradation（優雅な劣化）」パターンと呼ばれる。
    """
    try:
        vector = await embed(query)
        results = search(vector, user_id, limit=limit)
        return [r["text"] for r in results]
    except Exception:
        logger.exception("RAG からの類似会話検索に失敗（user_id=%s）", user_id)
        return []


async def retrieve_knowledge(query: str, limit: int = 2) -> list[dict]:
    """クエリに関連する知識をベクトル検索で取得する。

    Args:
        query: 検索クエリ（通常はユーザーの最新メッセージ）
        limit: 返す結果の最大数

    Returns:
        類似度が高い知識エントリのリスト。
        各要素は {"text": str, "category": str, "source": str, "score": float}。
        検索に失敗した場合は空リストを返す。

    --- 技術解説: 知識検索 vs 会話検索 ---
    会話検索は user_id でフィルターして個人の過去の会話を取得するが、
    知識検索はフィルターなしで全ユーザー共通の知識ベースを検索する。
    limit=2 にしているのは、プロンプトが長くなりすぎないようにするため。
    """
    try:
        augmented_query = _augment_query_with_english(query)
        vector = await embed(augmented_query)
        results = search_knowledge(vector, limit=limit)
        return results
    except Exception:
        logger.exception("知識ベースの検索に失敗")
        return []
