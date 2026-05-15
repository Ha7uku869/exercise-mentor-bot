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
from pydantic import BaseModel, Field
from src.storage.supabase_client import (
    save_workout,
    list_workouts,
    save_context_note,
    list_context_notes,
)
from src.llm.client import chat_with_tools, chat_after_tools
from datetime import date as _date
from src.storage.supabase_client import (
    save_workout,
    list_workouts,
    save_context_note,
    list_context_notes,
    save_chat_log,
)
logger = logging.getLogger(__name__)


app = FastAPI(title="筋トレメタ認知AI")

# CORS 設定（Vite 開発サーバーおよびデプロイ先からのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(http://localhost:(3000|5173)|https://.*\.vercel\.app)",
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


@app.get("/health") #HTTPのGETメソッド
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/callback")  #HTTPのPOSTメソッド(LINEサーバーが「ユーザがMessage送ったよ」と通知してくる窓口)
async def callback(request: Request) -> dict[str, str]:
    """LINE Webhook エンドポイント。"""
    parser, messaging_api = _ensure_line_clients()

    signature = request.headers.get("X-Line-Signature", "") #X-Line-Signatureで本当にLINEからの通知か検証
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

# ① ユーザーがReactの入力欄に「肩トレどうすれば？」と入力、送信ボタン
# ② ReactのJSが fetch("http://localhost:8000/api/chat", {
#      method: "POST",
#      body: JSON.stringify({ user_id: "me", message: "肩トレどうすれば？" })
#    })
#    ↑ ここが「APIを叩く」
# ③ FastAPIの api_chat 関数が受け取る (main.py:172)
# ④ FastAPIが内部で：
#    ・履歴をDBから取得
#    ・Claude APIを呼んで応答生成
#    ・バイアス検出
#    ・DBに保存
# ⑤ FastAPI が {"reply": "..."} を返す
# ⑥ Reactが受け取って画面に表示

# ──────────────────────────────────────
# Function Calling 用ツール定義
# ──────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_workout",
            "description": (
                "ユーザーが運動・トレーニングの実績を報告したときに呼ぶ。"
                "種目に応じて関連するフィールドだけ埋める（不要なフィールドは省略）。"
                " 例: 筋トレ→weight/reps/sets、ランニング→duration_minutes/distance_km、"
                "ヨガやストレッチ→duration_minutes、リングフィットなどゲーム→duration_minutes/intensity"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD。明示が無ければ今日"},
                    "exercise_name": {
                        "type": "string",
                        "description": "種目名。自由記述（例: ベンチプレス、ランニング、ヨガ、リングフィット、腹筋、ゴルフ練習）",
                    },
                    "weight": {"type": "number", "description": "kg。重量を扱う種目のみ"},
                    "reps": {"type": "integer", "description": "1セットあたりの回数"},
                    "sets": {"type": "integer", "description": "セット数"},
                    "duration_minutes": {"type": "integer", "description": "実施時間（分）"},
                    "distance_km": {"type": "number", "description": "距離（km）。ランニング等"},
                    "intensity": {
                        "type": "integer",
                        "description": "主観的強度 1〜10。重量や距離で表せない種目用",
                    },
                    "memo": {"type": "string"},
                },
                "required": ["date", "exercise_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_context_note",
            "description": "ユーザーが筋トレの実績以外で、後の応答で参照すべき重要事項（怪我、目標変更、生活変化など）を伝えたときに呼ぶ",
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {"type": "string", "description": "保存する自由文の内容"},
                    "category": {
                        "type": "string",
                        "enum": ["injury", "goal", "lifestyle", "other"],
                    },
                    "valid_until": {
                        "type": "string",
                        "description": "YYYY-MM-DD。情報の有効期限（例: ケガの完治予定日）。期限が不明なら省略",
                    },
                },
                "required": ["note", "category"],
            },
        },
    },
]


def _build_chat_system_prompt(user_id: str) -> str:
    """チャット用のシステムプロンプトを組み立てる。

    過去の context_notes を文脈として含め、LLM がそれを踏まえて応答できるようにする。
    """
    today = _date.today().isoformat()
    notes = list_context_notes(user_id, limit=10)
    notes_block = "（なし）"
    if notes:
        lines = []
        for n in notes:
            valid = f"〜{n['valid_until']}" if n.get("valid_until") else "期限なし"
            lines.append(f"- [{n['category']}] {n['note']} ({valid})")
        notes_block = "\n".join(lines)

    return f"""あなたは運動・トレーニングのメンターAIです。今日は {today}。
対応する活動: 筋トレ、ランニング、ウォーキング、ヨガ、ストレッチ、リングフィット等のフィットネスゲーム、ゴルフ練習、球技、登山など。

【役割】
- ユーザーの運動実績を記録し、メタ認知を促す
- 怪我・目標・生活変化など重要情報を覚えておく
- 必ず日本語で応答する

【ツール使用ルール（厳格に守ること）】
- save_workout: 運動・トレーニングを「実施した」報告のときだけ呼ぶ。
  対応種目: 筋トレ（重量×回数×セット）/ ランニング・ウォーキング（時間・距離）/
  ヨガ・ストレッチ・ピラティス（時間）/ リングフィット等ゲーム（時間+主観強度）/
  ゴルフ練習・球技・登山など（時間+主観強度）。
  種目に応じ、関連する数値フィールドだけ埋める（埋められないものは省略）。
- save_context_note: **将来の提案を変える** 情報のときだけ呼ぶ。
  該当例: 怪我、慢性疾患、明確な目標宣言（「3ヶ月で-5kg」等）、生活変化（妊娠、転勤、機材入手）。
  非該当: 「調子がいい」「眠い」「お腹空いた」など雑談。判断に迷ったら呼ばない。
- 上記いずれにも該当しない場合は、ツールを呼ばず応答テキストだけを返す。
- valid_until や数値フィールドが不明なときはそのフィールド自体を含めない（空文字 "" を入れない）。

【ユーザーの背景情報（過去の context_notes）】
{notes_block}

【応答スタイル】
- ツールで保存した場合は「○○として記録しました」と何を保存したか伝える
- メタ認知を促す問いかけを1つ含めると良い（毎回でなくてよい）
"""


@app.post("/api/chat")
async def api_chat(request: Request) -> dict:
    """Web ダッシュボードからのチャットエンドポイント。

    Function Calling でユーザー発話から workout / context_note を抽出・保存する。
    """
    body = await request.json()
    user_id = body.get("user_id", "")
    display_name = body.get("display_name", "")
    message = body.get("message", "")

    if not user_id or not message:
        raise HTTPException(status_code=400, detail="user_id and message are required")

    history = get_history(user_id)
    system_prompt = _build_chat_system_prompt(user_id)

    try:
        first = await chat_with_tools(
            user_message=message,
            system_prompt=system_prompt,
            tools=TOOLS,
            history=history,
        )
    except Exception:
        logger.exception("LLM (first call) failed")
        raise HTTPException(status_code=500, detail="LLM call failed")

    saved_records: list[dict] = []

    if first["type"] == "text":
        reply = first["content"]
    else:
        tool_results = []
        for call in first["calls"]:
            name = call["name"]
            # 空文字・None を除去（LLM が空欄として "" を返すことがあり、
            # date 型カラムなどで Postgres が解釈できずエラーになるため）
            args = {k: v for k, v in call["arguments"].items() if v not in ("", None)}
            try:
                if name == "save_workout":
                    args.setdefault("date", _date.today().isoformat())
                    saved = save_workout({"user_id": user_id, **args})
                elif name == "save_context_note":
                    saved = save_context_note({"user_id": user_id, **args})
                else:
                    saved = {"error": f"unknown tool: {name}"}
            except Exception as e:
                logger.exception("Tool execution failed: %s", name)
                saved = {"error": str(e)}
            saved_records.append({"tool": name, "result": saved})
            tool_results.append(saved)

        try:
            reply = await chat_after_tools(
                user_message=message,
                system_prompt=system_prompt,
                tool_calls=first["calls"],
                tool_results=tool_results,
                history=history,
            )
        except Exception:
            logger.exception("LLM (second call) failed")
            raise HTTPException(status_code=500, detail="LLM call failed")

    add_message(user_id, "user", message)
    add_message(user_id, "assistant", reply)

    save_chat_log({
        "user_id": user_id,
        "display_name": display_name,
        "user_message": message,
        "assistant_reply": reply,
        "saved_records": saved_records,
    })

    return {"reply": reply, "saved": saved_records}

# リクエストモデル
class WorkoutCreate(BaseModel):
    user_id: str
    date: str  # ISO format YYYY-MM-DD
    exercise_name: str
    weight: float | None = None
    reps: int | None = None
    sets: int | None = None
    duration_minutes: int | None = None
    distance_km: float | None = None
    intensity: int | None = Field(default=None, ge=1, le=10)
    fatigue: int | None = Field(default=None, ge=1, le=10)
    motivation: int | None = Field(default=None, ge=1, le=10)
    memo: str | None = None

@app.post("/workouts")
async def api_create_workout(payload: WorkoutCreate) -> dict:
    saved = save_workout(payload.model_dump(exclude_none=True))
    return saved

@app.get("/workouts")
async def api_list_workouts(user_id: str, limit: int = 50) -> dict:
    return {"workouts": list_workouts(user_id=user_id, limit=limit)}