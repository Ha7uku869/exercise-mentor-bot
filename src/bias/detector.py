"""認知バイアスの検知と応答生成を行うモジュール。

bias/prompts.py のシステムプロンプトを llm/client.py に渡して、
ユーザーの発言に対する応答を生成する。

会話履歴を受け取って LLM に渡すことで、
文脈を踏まえた応答が可能になっている。

--- 技術解説: RAG の統合 ---
RAG（検索拡張生成）を組み込むことで、直近の会話履歴だけでなく、
過去の類似する会話を参考にした応答を生成できる。
例えば1ヶ月前にベンチプレスの悩みを相談していた場合、
今回また同じ話題が出た時に過去の文脈を踏まえた応答ができる。
"""

import logging

from src.bias.prompts import SYSTEM_PROMPT
from src.llm.client import chat
from src.rag.retriever import retrieve_knowledge, retrieve_similar, store_message
import re

from src.storage.memory import (
    add_bias_detection,
    add_nutrition_log,
    add_training_log,
    get_profile,
    get_recent_nutrition_logs,
    get_recent_training_logs,
    update_profile,
)
from src.storage.profile_extractor import extract_profile
from src.storage.training_analyzer import analyze_training_balance

logger = logging.getLogger(__name__)


async def respond(
    user_message: str,
    user_id: str = "",
    history: list[dict[str, str]] | None = None,
) -> str:
    """ユーザーのメッセージに対して認知バイアスを考慮した応答を返す。

    RAG を使って過去の類似会話を検索し、コンテキストとして
    LLM に渡すことで、より文脈を踏まえた応答を生成する。

    Args:
        user_message: ユーザーが LINE で送ったテキスト
        user_id: LINE ユーザーID（RAG の検索・保存に使用）
        history: 直近の会話履歴

    Returns:
        認知バイアスの検知結果を含む応答テキスト

    --- 技術解説: RAG コンテキストの渡し方 ---
    検索で見つかった過去の会話をユーザーメッセージに付加する。
    LLM はこの追加コンテキストを参考にして応答を生成する。
    RAG が失敗しても（空リストが返っても）基本的な応答は生成できる。
    """
    # --- Step 0: ユーザープロフィールを取得 ---
    rag_context = ""
    if user_id:
        profile = get_profile(user_id)
        if profile:
            profile_lines = "\n".join(f"- {k}: {v}" for k, v in profile.items())
            rag_context += (
                "\n\n【このユーザーのプロフィール】\n"
                f"{profile_lines}\n"
                "\n※ ユーザーの体重・重量・目標などを把握した上で応答してください。\n"
            )

        # 未設定の重要情報を自然に聞くよう指示
        missing_info = []
        if not profile.get("goal"):
            missing_info.append("数値目標（例: ベンチプレス○○kg、体脂肪率○○%）")
        if not profile.get("ideal_physique"):
            missing_info.append(
                "理想の体型・見た目（例: 肩幅を広くしたい、腹筋を割りたい、"
                "細マッチョ、舐められない体など、抽象的でもOK）"
            )
        if not profile.get("body_weight"):
            missing_info.append("体重（プロテイン量や栄養の計算に必要）")
        if not profile.get("height"):
            missing_info.append("身長")
        if missing_info:
            items = "\n".join(f"- {g}" for g in missing_info)
            rag_context += (
                "\n\n【未設定: ユーザーの基本情報】\n"
                "以下がまだわかりません。応答の最後にさりげなく聞いてみてください:\n"
                f"{items}\n"
                "※ ユーザーの質問への回答を優先し、最後に軽く添える程度にしてください。\n"
                "※ 一度に全部聞かず、1〜2個ずつ自然に聞いてください。\n"
                "※ 会話の流れで不自然な場合は聞かなくて構いません。\n"
            )

        # プロテイン・栄養の相談時、体重がわかっていれば計算コンテキストを注入
        nutrition_keywords = ["プロテイン", "タンパク質", "たんぱく質", "栄養", "食事", "粉", "スクープ", "何グラム"]
        is_nutrition_question = any(kw in user_message for kw in nutrition_keywords)
        if is_nutrition_question and profile.get("body_weight"):
            rag_context += (
                "\n\n【栄養計算の参考情報】\n"
                f"ユーザーの体重: {profile['body_weight']}\n"
            )
            if profile.get("height"):
                rag_context += f"身長: {profile['height']}\n"
            if profile.get("body_fat"):
                rag_context += f"体脂肪率: {profile['body_fat']}\n"
            rag_context += (
                "\n推奨タンパク質量の計算:\n"
                "- 筋肥大目的: 体重1kgあたり1.6〜2.2g\n"
                "- 例: 70kgの場合 → 1日112〜154g\n"
                "- 一般的なホエイプロテイン: 1スクープ(約30g粉)でタンパク質約24g\n"
                "- 必要スクープ数の目安も提案してください\n"
                "※ ユーザーの体重から具体的な数値を計算して提案してください。\n"
            )

        # 直近のトレーニング記録を取得
        recent_logs = get_recent_training_logs(user_id)
        if recent_logs:
            log_lines = "\n".join(
                f"- {lg['date']}: {lg['exercise']} {lg['weight']}×{lg['reps']}回×{lg['sets']}セット"
                + (f"（{lg['note']}）" if lg.get("note") else "")
                for lg in recent_logs
            )
            rag_context += (
                "\n\n【このユーザーの直近のトレーニング記録】\n"
                f"{log_lines}\n"
                "\n※ 過去の記録を踏まえて、進捗や重量の変化に言及してください。\n"
            )

        # 直近の栄養・プロテイン記録を取得
        recent_nutrition = get_recent_nutrition_logs(user_id)
        if recent_nutrition:
            nutr_lines = "\n".join(
                f"- {n['date']}: {n['item']}"
                + (f"（{n['type']}）" if n.get("type") else "")
                + (f" {n['amount']}" if n.get("amount") else "")
                + (f" タンパク質{n['protein_g']}g" if n.get("protein_g") else "")
                + (f" {n['note']}" if n.get("note") else "")
                for n in recent_nutrition
            )
            rag_context += (
                "\n\n【このユーザーの直近のプロテイン・栄養記録】\n"
                f"{nutr_lines}\n"
                "\n※ 普段の摂取内容を踏まえてアドバイスしてください。\n"
            )

        # トレーニングメニューの相談かどうか判定し、部位バランス分析を注入
        menu_keywords = ["何やる", "何する", "メニュー", "何やろう", "何しよう", "おすすめ", "提案", "今日のトレ", "今日は何"]
        is_menu_question = any(kw in user_message for kw in menu_keywords)

        # メニュー相談時、器具情報が未登録なら聞く
        if is_menu_question:
            equipment_fields = [
                "equipment_bench", "equipment_barbell", "equipment_dumbbells",
                "equipment_weight_total", "equipment_rack", "equipment_other",
                "training_location",
            ]
            has_equipment_info = any(profile.get(f) for f in equipment_fields)
            if not has_equipment_info:
                rag_context += (
                    "\n\n【未設定: トレーニング器具・環境】\n"
                    "このユーザーの器具情報がまだわかりません。\n"
                    "種目を提案する前に、まず以下を聞いてください:\n"
                    "- トレーニング場所（自宅 or ジム）\n"
                    "- 自宅の場合: 持っている器具（ダンベルの重さ・個数、ベンチの有無、"
                    "バーベル・ラックの有無、その他の器具）\n"
                    "※ 器具がわかれば、それに合った種目を提案できます。\n"
                    "※ ジムの場合は器具の質問は不要で、そのまま種目を提案してください。\n"
                )

        # メニュー相談時、理想の体型が登録されていれば提案に反映
        if is_menu_question and profile.get("ideal_physique"):
            rag_context += (
                "\n\n【このユーザーの理想の体型】\n"
                f"{profile['ideal_physique']}\n"
                "\n※ この理想像に近づくための種目を優先的に提案してください。\n"
                "例: 「肩幅を広く」→ サイドレイズ・ショルダープレスを優先\n"
                "例: 「腹筋を割りたい」→ 腹筋種目 + 体脂肪を落とすアドバイス\n"
                "例: 「上半身メインで足は細め」→ 脚の種目は控えめに\n"
            )

        if is_menu_question:
            analysis = analyze_training_balance(user_id)
            if analysis["trained"]:
                trained_lines = "\n".join(
                    f"- {group}: {count}回" for group, count in analysis["trained"].items()
                )
                rag_context += (
                    "\n\n【直近14日間の部位別トレーニング回数】\n"
                    f"{trained_lines}\n"
                )
            if analysis["undertrained"]:
                rag_context += (
                    "\n\n【不足している部位】\n"
                    + "\n".join(f"- {s}" for s in analysis["suggestions"])
                    + "\n\n※ ユーザーがメニューを聞いているので、不足部位を優先的に提案してください。\n"
                )
            if analysis["exercises_done"]:
                ex_lines = "\n".join(
                    f"- {ex}: {count}回" for ex, count in analysis["exercises_done"].items()
                )
                rag_context += (
                    "\n\n【このユーザーがやったことのある種目】\n"
                    f"{ex_lines}\n"
                    "\n※ ユーザーが経験済みの種目を中心に提案し、新しい種目も1〜2個提案してください。\n"
                )

        logger.info("Profile: %d 件のフィールドを取得（user_id=%s）", len(profile), user_id)

    # --- Step 1: 過去の類似会話を検索 ---
    if user_id:
        similar_messages = await retrieve_similar(user_id, user_message)
        if similar_messages:
            context_lines = "\n".join(f"- {msg}" for msg in similar_messages)
            rag_context += (
                "\n\n【参考: このユーザーの過去の関連する会話】\n"
                f"{context_lines}\n"
            )
            logger.info(
                "RAG: %d 件の類似会話を取得しました（user_id=%s）",
                len(similar_messages),
                user_id,
            )

    # --- Step 1.5: 知識ベースから関連知識を検索 ---
    knowledge_results = await retrieve_knowledge(user_message)
    if knowledge_results:
        knowledge_lines = "\n".join(
            f"- [{k['category']}] {k['text']}（出典: {k['source']}）"
            for k in knowledge_results
        )
        rag_context += (
            "\n\n【参考: エビデンスベースの筋トレ知識】\n"
            f"{knowledge_lines}\n"
            "\n※ 上記の知識に含まれる具体的な数値やアドバイスを優先して使ってください。"
            "自分の知識より上記の情報を信頼し、出典を明示すると信頼性が上がります。\n"
        )
        logger.info("RAG: %d 件の関連知識を取得しました", len(knowledge_results))

    # --- Step 2: RAG コンテキストを付加してメッセージを構築 ---
    augmented_message = user_message
    if rag_context:
        augmented_message = user_message + rag_context

    # --- Step 3: LLM で応答を生成 ---
    reply = await chat(
        user_message=augmented_message,
        system_prompt=SYSTEM_PROMPT,
        history=history,
    )

    # --- Step 4: 今回の会話を RAG ストアに保存 ---
    if user_id:
        await store_message(user_id, user_message, "user")
        await store_message(user_id, reply, "assistant")

    # --- Step 4.5: 応答に認知の歪みが含まれていれば記録 ---
    if user_id:
        _BIAS_TYPES = [
            "全か無か思考", "過度の一般化", "心のフィルター", "マイナス化思考",
            "結論の飛躍", "拡大解釈と過小評価", "感情的決めつけ",
            "すべき思考", "レッテル貼り", "個人化",
        ]
        for bias_type in _BIAS_TYPES:
            if bias_type in reply:
                add_bias_detection(user_id, bias_type, user_message)
                logger.info("Bias detected: %s（user_id=%s）", bias_type, user_id)
                break  # 1応答1記録

    # --- Step 5: 会話からプロフィール・トレーニング・栄養記録を抽出・保存 ---
    if user_id:
        profile_updates, training_logs, nutrition_logs = await extract_profile(
            user_message, reply
        )
        if profile_updates:
            update_profile(user_id, profile_updates)
            logger.info("Profile updated: %s（user_id=%s）", profile_updates, user_id)
        for log in training_logs:
            add_training_log(user_id, log)
        if training_logs:
            logger.info(
                "Training logs: %d 件追加（user_id=%s）", len(training_logs), user_id
            )
        for log in nutrition_logs:
            add_nutrition_log(user_id, log)
        if nutrition_logs:
            logger.info(
                "Nutrition logs: %d 件追加（user_id=%s）", len(nutrition_logs), user_id
            )

    return reply
