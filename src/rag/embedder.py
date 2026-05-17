"""HuggingFace Inference API を使ってテキストの埋め込みベクトルを生成するモジュール。

--- 技術解説: 埋め込み（Embedding）とは ---
テキストを固定長の数値ベクトル（リスト）に変換すること。
意味が近い文章は、ベクトル空間上でも近い位置に配置される。
これにより「意味的な類似度」を数値で計算できるようになる。

--- 技術解説: HuggingFace Inference API ---
HuggingFace の新しい Inference API (v2) では、
/models/{model_id} エンドポイントを使い、タスクに応じた
パラメータを送信する。
"""

import logging

import requests

from src.config import get_settings

logger = logging.getLogger(__name__)

# 使用するモデル（384次元、高速、無料）
_MODEL_ID = "BAAI/bge-small-en-v1.5"
_API_URL = f"https://router.huggingface.co/hf-inference/models/{_MODEL_ID}"


async def embed(text: str) -> list[float]:
    """テキストを埋め込みベクトルに変換する。

    Args:
        text: 埋め込みベクトルを生成したいテキスト

    Returns:
        384 次元の浮動小数点数リスト

    Raises:
        RuntimeError: API 呼び出しに失敗した場合
    """
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.hf_api_token}",
    }

    try:
        response = requests.post(
            _API_URL,
            headers=headers,
            json={"inputs": text},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("HuggingFace API 呼び出しに失敗: %s", e)
        raise RuntimeError(f"埋め込みベクトルの生成に失敗しました: {e}") from e

    result = response.json()

    # API は [[float, ...]] または [float, ...] で返す
    if isinstance(result, list) and len(result) > 0:
        if isinstance(result[0], list):
            return result[0]
        return result

    raise RuntimeError(f"HuggingFace API から予期しないレスポンス: {result}")
