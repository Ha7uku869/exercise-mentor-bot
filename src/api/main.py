"""FastAPI アプリケーションのエントリーポイント。

LINE Bot の Webhook を受け取り、認知バイアス検知の応答を返す。
ダッシュボード用の REST API も提供する。
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from src.bias.detector import respond
from src.config import get_settings
from src.storage.memory import (
    add_message,
    get_bias_summary,
    get_history,
    get_profile,
    get_recent_nutrition_logs,
    get_recent_training_logs,
)
from src.storage.training_analyzer import analyze_training_balance

logger = logging.getLogger(__name__)

app = FastAPI(title="筋トレメタ認知AI")

# CORS 設定（Next.js ダッシュボードからのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(http://localhost:3000|https://.*\.vercel\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────
# LINE Bot
# ──────────────────────────────────────

_parser: WebhookParser | None = None
_messaging_api: MessagingApi | None = None


def _ensure_line_clients() -> tuple[WebhookParser, MessagingApi]:
    """LINE クライアントを遅延初期化する。"""
    global _parser, _messaging_api
    if _parser is None or _messaging_api is None:
        settings = get_settings()
        _parser = WebhookParser(channel_secret=settings.line_channel_secret)
        config = Configuration(access_token=settings.line_channel_access_token)
        api_client = ApiClient(configuration=config)
        _messaging_api = MessagingApi(api_client)
    return _parser, _messaging_api


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/callback")
async def callback(request: Request) -> dict[str, str]:
    """LINE Webhook エンドポイント。"""
    parser, messaging_api = _ensure_line_clients()

    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue

        user_id = event.source.user_id
        user_text = event.message.text
        logger.info("Received message from %s: %s", user_id, user_text)

        history = get_history(user_id)

        try:
            reply_text = await respond(user_text, user_id=user_id, history=history)
        except Exception:
            logger.exception("Failed to generate response")
            reply_text = "すみません、応答の生成に失敗しました。もう一度お試しください。"

        add_message(user_id, "user", user_text)
        add_message(user_id, "assistant", reply_text)

        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )

    return {"status": "ok"}


# ──────────────────────────────────────
# Dashboard API
# ──────────────────────────────────────

@app.get("/api/dashboard/{user_id}")
async def get_dashboard(user_id: str) -> dict:
    """ダッシュボードに必要な全データをまとめて返す。

    フロントエンドから1回のリクエストで全データを取得できるようにする。
    """
    profile = get_profile(user_id)
    training_logs = get_recent_training_logs(user_id, limit=50)
    nutrition_logs = get_recent_nutrition_logs(user_id, limit=50)
    bias_summary = get_bias_summary(user_id)
    training_balance = analyze_training_balance(user_id)

    return {
        "profile": profile,
        "training_logs": training_logs,
        "nutrition_logs": nutrition_logs,
        "bias_summary": bias_summary,
        "training_balance": training_balance,
    }


@app.get("/api/profile/{user_id}")
async def api_get_profile(user_id: str) -> dict:
    """ユーザープロフィールを返す。"""
    return get_profile(user_id)


@app.get("/api/training/{user_id}")
async def api_get_training(user_id: str, limit: int = 50) -> list[dict]:
    """トレーニング記録を返す。"""
    return get_recent_training_logs(user_id, limit=limit)


@app.get("/api/nutrition/{user_id}")
async def api_get_nutrition(user_id: str, limit: int = 50) -> list[dict]:
    """栄養記録を返す。"""
    return get_recent_nutrition_logs(user_id, limit=limit)


@app.get("/api/bias/{user_id}")
async def api_get_bias(user_id: str) -> dict:
    """認知の歪みの集計データを返す。"""
    return get_bias_summary(user_id)


@app.get("/api/balance/{user_id}")
async def api_get_balance(user_id: str) -> dict:
    """部位別トレーニングバランスを返す。"""
    return analyze_training_balance(user_id)


@app.post("/api/chat")
async def api_chat(request: Request) -> dict:
    """Web ダッシュボードからのチャットエンドポイント。

    LINE を経由せず、Web UI から直接 LLM と会話できる。
    """
    body = await request.json()
    user_id = body.get("user_id", "")
    message = body.get("message", "")

    if not user_id or not message:
        raise HTTPException(status_code=400, detail="user_id and message are required")

    history = get_history(user_id)

    try:
        reply = await respond(message, user_id=user_id, history=history)
    except Exception:
        logger.exception("Failed to generate response")
        raise HTTPException(status_code=500, detail="Response generation failed")

    add_message(user_id, "user", message)
    add_message(user_id, "assistant", reply)

    return {"reply": reply}
