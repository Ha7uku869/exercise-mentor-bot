"""Groq API とやりとりするクライアントモジュール。

Groq は OpenAI 互換の API を提供しているため、openai ライブラリの
base_url を変えるだけで接続できる。Llama 3 等のオープンソースモデルを
無料で高速に利用できる。

--- 技術解説: OpenAI 互換 API ---
多くの LLM プロバイダ（Groq, Together AI, Ollama 等）が
OpenAI の Chat Completions API と同じインターフェースを採用している。
これにより、openai ライブラリの base_url を差し替えるだけで
異なるプロバイダに接続でき、コードの変更が最小限で済む。
"""

from openai import AsyncOpenAI

from src.config import get_settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Groq クライアントを取得する（初回のみ生成）。

    AsyncOpenAI に base_url を指定することで、
    リクエスト先を OpenAI ではなく Groq に向ける。
    """
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
    return _client


async def chat(
    user_message: str,
    system_prompt: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """ユーザーのメッセージに対して LLM の応答を返す。

    Args:
        user_message: ユーザーが送ったテキスト
        system_prompt: LLM の振る舞いを制御するシステムプロンプト
        history: 過去の会話履歴。[{"role": "user", "content": "..."}, ...] の形式

    Returns:
        LLM が生成した応答テキスト

    --- 技術解説: 会話履歴の渡し方 ---
    Chat Completions API の messages は「会話全体」をリストで渡す。
    [system, 過去user, 過去assistant, 過去user, 過去assistant, ..., 今回のuser]
    LLM はこのリスト全体を見て応答を生成するので、
    過去の会話を含めると文脈を踏まえた応答ができる。
    """
    client = _get_client()

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
    )
    return response.choices[0].message.content


async def chat_with_tools(
    user_message: str,
    system_prompt: str,
    tools: list[dict],
    history: list[dict[str, str]] | None = None,
) -> dict:
    """ツール呼び出しに対応したチャット応答。

    LLM が「workout を保存したい」「context_note を残したい」と判断したら
    tool_calls を返す。判断しなければ通常のテキスト応答を返す。

    Returns:
        {"type": "tool_call", "calls": [{"name": str, "arguments": dict, "id": str}, ...]}
        または
        {"type": "text", "content": str}
    """
    import json

    client = _get_client()

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    msg = response.choices[0].message

    if msg.tool_calls:
        calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": json.loads(tc.function.arguments),
            }
            for tc in msg.tool_calls
        ]
        return {"type": "tool_call", "calls": calls}

    return {"type": "text", "content": msg.content}


async def chat_after_tools(
    user_message: str,
    system_prompt: str,
    tool_calls: list[dict],
    tool_results: list[dict],
    history: list[dict[str, str]] | None = None,
) -> str:
    """ツール実行結果を踏まえた最終応答を LLM に生成させる。

    chat_with_tools が tool_call を返した後、
    呼び出し元でツールを実行し、その結果をこの関数に渡すと、
    LLM が「記録しました。〜」のような自然な応答を作る。
    """
    import json

    client = _get_client()

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    messages.append(
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {
                        "name": c["name"],
                        "arguments": json.dumps(c["arguments"], ensure_ascii=False),
                    },
                }
                for c in tool_calls
            ],
        }
    )
    for c, r in zip(tool_calls, tool_results):
        messages.append(
            {
                "role": "tool",
                "tool_call_id": c["id"],
                "content": json.dumps(r, ensure_ascii=False, default=str),
            }
        )

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
    )
    return response.choices[0].message.content
