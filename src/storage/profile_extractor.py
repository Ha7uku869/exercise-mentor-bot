"""会話からユーザーのトレーニングプロフィール情報とトレーニング記録を抽出するモジュール。

ユーザーとアシスタントの会話を LLM に渡し、
体重・トレーニング歴・各種目の重量・目標などの
構造化データを JSON で抽出する。
また、具体的なトレーニング記録（種目・重量・回数・セット数）も抽出する。
"""

import json
import logging

from src.llm.client import chat

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
あなたはユーザーの会話からトレーニング関連の情報を抽出するアシスタントです。

以下の会話を読み、2種類の情報を JSON で返してください。

## 1. プロフィール情報（profile）

該当するフィールドのみ抽出:

- height: 身長（例: "170cm"）
- body_weight: 体重（例: "70kg"）
- body_fat: 体脂肪率（例: "15%", "20%"）
- age: 年齢（例: "22歳"）
- gender: 性別（例: "男性", "女性"）
- training_experience: トレーニング歴（例: "3ヶ月", "2年"）
- goal: 数値目標（例: "ベンチプレス100kg", "体重65kgまで減量"）
- ideal_physique: 理想の体型・見た目（ユーザーの言葉をそのまま記録。例: "肩幅を広くしたい", "腹筋を割りたい", "上半身メインで足は細めがいい", "舐められない体", "細マッチョ", "逆三角形の体型"）
- bench_press_max: ベンチプレスMAX重量（例: "80kg"）
- squat_max: スクワットMAX重量（例: "100kg"）
- deadlift_max: デッドリフトMAX重量（例: "120kg"）
- training_frequency: トレーニング頻度（例: "週3回"）
- training_split: トレーニング分割（例: "上半身/下半身", "PPL"）
- injuries: 怪我・制限（例: "腰痛持ち", "右肩痛"）
- equipment_bench: ベンチの有無（例: "あり", "インクラインベンチあり", "なし"）
- equipment_barbell: バーベルの有無（例: "あり", "なし"）
- equipment_dumbbells: ダンベル情報（例: "可変式20kgペア", "固定10kg・15kg・20kg"）
- equipment_weight_total: プレート・重量の合計（例: "合計60kg", "片側20kg"）
- equipment_rack: ラック・スタンドの有無（例: "パワーラックあり", "スクワットスタンドあり", "なし"）
- equipment_other: その他の器具（例: "チンニングスタンド", "ケーブルマシン", "腹筋ローラー"）
- training_location: トレーニング場所（例: "自宅", "ジム", "自宅+ジム"）

## 2. トレーニング記録（training_logs）

ユーザーが実際に行ったトレーニングの記録を抽出:

- exercise: 種目名（例: "ベンチプレス", "スクワット"）
- weight: 重量（例: "42.5kg", "自重"）
- reps: 回数（数値、例: 8）
- sets: セット数（数値、例: 3）
- note: 補足（例: "フォーム不安定", "楽にできた"）

## 3. 栄養・プロテイン記録（nutrition_logs）

ユーザーが実際に摂取したプロテインやサプリメントの記録を抽出:

- item: 品名（例: "プロテイン", "BCAA", "クレアチン"）
- type: 種類（例: "ホエイ", "ソイ", "カゼイン", "WPI"）
- protein_g: タンパク質量（数値、グラム単位、例: 24）
- amount: 粉の量や摂取量（例: "30g", "1スクープ", "200ml"）
- note: 補足（例: "トレ後", "朝食時", "チョコ味"）

## ルール

1. 会話に含まれる情報のみ抽出する。推測しない。
2. ユーザーの発言から抽出する。アシスタントの提案は抽出しない。
3. 以下の JSON 形式のみを返す。説明文は不要。

```json
{
  "profile": {},
  "training_logs": [],
  "nutrition_logs": []
}
```

例:
- 「今日ベンチ42.5kgを8回3セットやった」→ training_logs に追加
- 「体重70kgです」→ profile に body_weight を追加
- 「トレ後にホエイプロテイン30g飲んだ、タンパク質24g」→ nutrition_logs に追加
- 「肩幅広くしてナメられない体になりたい」→ profile に ideal_physique を追加
- 「家にダンベル20kgペアとインクラインベンチがある」→ profile に equipment_dumbbells, equipment_bench を追加
- 「タンパク質ってどれくらい摂ればいい？」→ すべて空
"""


async def extract_profile(
    user_message: str,
    assistant_reply: str,
) -> tuple[dict[str, str], list[dict], list[dict]]:
    """会話のやりとりからプロフィール情報・トレーニング記録・栄養記録を抽出する。

    Args:
        user_message: ユーザーが送ったテキスト
        assistant_reply: アシスタントの応答テキスト

    Returns:
        (プロフィール辞書, トレーニング記録リスト, 栄養記録リスト) のタプル
    """
    conversation = f"ユーザー: {user_message}\nアシスタント: {assistant_reply}"

    try:
        raw = await chat(
            user_message=conversation,
            system_prompt=EXTRACTION_PROMPT,
        )
        # LLM の応答から JSON 部分を抽出
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)
        if not isinstance(result, dict):
            return {}, [], []

        profile = result.get("profile", {})
        if not isinstance(profile, dict):
            profile = {}
        profile = {k: v for k, v in profile.items() if v}

        training_logs = result.get("training_logs", [])
        if not isinstance(training_logs, list):
            training_logs = []
        training_logs = [lg for lg in training_logs if lg.get("exercise") and lg.get("weight")]

        nutrition_logs = result.get("nutrition_logs", [])
        if not isinstance(nutrition_logs, list):
            nutrition_logs = []
        nutrition_logs = [lg for lg in nutrition_logs if lg.get("item")]

        return profile, training_logs, nutrition_logs
    except (json.JSONDecodeError, Exception):
        logger.exception("プロフィール抽出に失敗")
        return {}, [], []
