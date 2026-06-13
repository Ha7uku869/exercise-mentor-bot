"""経路A（Function Calling）の保存判定テスト。"""
import pytest
import asyncio
from src.api.main import _build_chat_system_prompt, TOOLS
from src.llm.client import chat_with_tools

_THROTTLE_SECONDS = 5  # Groq無料枠のTPM(12000)を超えないよう間隔を空ける


def _decision(result: dict) -> str:
    """LLMの返り値を判定ラベルに変換する純粋関数（DB・API不要）。"""
    if result["type"] == "text":
        return "none"
    return result["calls"][0]["name"]


async def _run(message: str) -> str:
    await asyncio.sleep(_THROTTLE_SECONDS)
    system_prompt = _build_chat_system_prompt("test_user", notes=[])
    result = await chat_with_tools(
        user_message=message, system_prompt=system_prompt, tools=TOOLS,
    )
    return _decision(result)


# ---- 決定的ユニットテスト（APIを呼ばない＝必ず緑・一瞬） ----
def test_decision_maps_text_to_none():
    assert _decision({"type": "text", "content": "x"}) == "none"


def test_decision_maps_tool_to_name():
    assert _decision({"type": "tool_call", "calls": [{"name": "save_workout"}]}) == "save_workout"


# ---- LLM評価テスト（本物のAPIを呼ぶ＝多少揺れる） ----
CASES = [
    pytest.param("今日ベンチ60kgを8回3セットやった", "save_workout", id="W1"),
    pytest.param("スクワット80kgを5回5セット完了", "save_workout", id="W2"),
    pytest.param("朝に腕立て30回を3セットやった", "save_workout", id="W3"),
    pytest.param("30分ランニングして5km走った", "save_workout", id="W4"),
    pytest.param("昨日5km走ったよ", "save_workout", id="W5"),
    pytest.param("今日は1時間ウォーキングした", "save_workout", id="W6"),
    pytest.param("寝る前に20分ヨガした", "save_workout", id="W7"),
    pytest.param("リングフィット40分やった", "save_workout", id="W8"),
    pytest.param("右肩を痛めたので来週まで休む", "save_context_note", id="C1"),
    pytest.param("腰が痛い気がするけど多分大丈夫", "save_context_note", id="C2"),
    pytest.param("膝の手術明けでしばらく走れない", "save_context_note", id="C3"),
    pytest.param("ベンチ60kg挙がるようになりたい", "save_context_note", id="C4"),
    pytest.param("3ヶ月で5kg減量したい", "save_context_note", id="C5"),
    pytest.param("来週からジムに通い始める", "save_context_note", id="C6"),
    pytest.param("自宅にダンベル20kgペア買った", "save_context_note", id="C7"),
    pytest.param("プロテイン飲み始めた", "save_context_note", id="C8"),
    pytest.param("来月から夜勤シフトになる", "save_context_note", id="C9"),
    pytest.param("ベンチプレスってどう伸ばす?", "none", id="N1"),
    pytest.param("プロテインって必要?", "none", id="N2"),
    pytest.param("筋肉痛のときは休むべき?", "none", id="N3"),
    pytest.param("今日は疲れた", "none", id="N4"),
    pytest.param("今日はやる気でない", "none", id="N5"),
    pytest.param("今日の天気いいね", "none", id="N6"),
    pytest.param("最近よく眠れてて調子いい", "save_context_note", id="X1",
                 marks=pytest.mark.xfail(reason="現プロンプトは睡眠/体調を拾わない（論点1/方針b）")),
]


@pytest.mark.parametrize("message, expected", CASES)
async def test_extraction(message, expected):
    assert await _run(message) == expected