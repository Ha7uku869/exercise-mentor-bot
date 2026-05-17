"""トレーニング記録を分析して、部位バランスや提案を行うモジュール。

種目→部位のマッピングを使い、直近の記録から
どの部位が不足しているかを判定する。
"""

from collections import defaultdict
from datetime import datetime, timedelta

from src.storage.memory import get_recent_training_logs

# 種目 → 主要ターゲット部位のマッピング
# キーは部分一致で検索する（「ベンチ」→「ベンチプレス」にマッチ）
EXERCISE_MUSCLE_MAP: dict[str, list[str]] = {
    # 胸
    "ベンチプレス": ["胸", "三頭筋", "肩(前部)"],
    "ベンチ": ["胸", "三頭筋", "肩(前部)"],
    "ダンベルプレス": ["胸", "三頭筋"],
    "ダンベルフライ": ["胸"],
    "チェストプレス": ["胸", "三頭筋"],
    "ペクフライ": ["胸"],
    "ディップス": ["胸", "三頭筋"],
    "腕立て": ["胸", "三頭筋"],
    "プッシュアップ": ["胸", "三頭筋"],
    "インクラインベンチ": ["胸(上部)", "三頭筋"],
    "インクラインプレス": ["胸(上部)", "三頭筋"],
    "インクラインダンベル": ["胸(上部)"],
    # 背中
    "デッドリフト": ["背中", "ハムストリング", "臀部"],
    "懸垂": ["背中", "二頭筋"],
    "チンニング": ["背中", "二頭筋"],
    "ラットプルダウン": ["背中", "二頭筋"],
    "ラットプル": ["背中", "二頭筋"],
    "バーベルロウ": ["背中"],
    "ベントオーバーロウ": ["背中"],
    "ダンベルロウ": ["背中"],
    "ワンハンドロウ": ["背中"],
    "シーテッドロウ": ["背中"],
    "ケーブルロウ": ["背中"],
    "Tバーロウ": ["背中"],
    # 肩
    "オーバーヘッドプレス": ["肩", "三頭筋"],
    "ショルダープレス": ["肩", "三頭筋"],
    "ミリタリープレス": ["肩", "三頭筋"],
    "サイドレイズ": ["肩(側部)"],
    "フロントレイズ": ["肩(前部)"],
    "リアレイズ": ["肩(後部)"],
    "アップライトロウ": ["肩", "僧帽筋"],
    "フェイスプル": ["肩(後部)", "僧帽筋"],
    "シュラッグ": ["僧帽筋"],
    # 腕
    "アームカール": ["二頭筋"],
    "バイセプスカール": ["二頭筋"],
    "ダンベルカール": ["二頭筋"],
    "バーベルカール": ["二頭筋"],
    "ハンマーカール": ["二頭筋", "前腕"],
    "トライセプス": ["三頭筋"],
    "スカルクラッシャー": ["三頭筋"],
    "ケーブルプレスダウン": ["三頭筋"],
    "プレスダウン": ["三頭筋"],
    "フレンチプレス": ["三頭筋"],
    # 脚
    "スクワット": ["大腿四頭筋", "臀部", "ハムストリング"],
    "フロントスクワット": ["大腿四頭筋", "体幹"],
    "レッグプレス": ["大腿四頭筋", "臀部"],
    "レッグエクステンション": ["大腿四頭筋"],
    "レッグカール": ["ハムストリング"],
    "ランジ": ["大腿四頭筋", "臀部"],
    "ブルガリアンスクワット": ["大腿四頭筋", "臀部"],
    "ヒップスラスト": ["臀部", "ハムストリング"],
    "カーフレイズ": ["ふくらはぎ"],
    "ルーマニアンデッドリフト": ["ハムストリング", "臀部"],
    "RDL": ["ハムストリング", "臀部"],
    # 体幹
    "プランク": ["体幹"],
    "クランチ": ["腹筋"],
    "シットアップ": ["腹筋"],
    "レッグレイズ": ["腹筋(下部)"],
    "アブローラー": ["腹筋", "体幹"],
    "腹筋ローラー": ["腹筋", "体幹"],
    "サイドプランク": ["体幹", "腹斜筋"],
    "ケーブルクランチ": ["腹筋"],
}

# 主要な部位グループ（バランスチェック用）
MAJOR_MUSCLE_GROUPS = {
    "胸": ["胸", "胸(上部)"],
    "背中": ["背中"],
    "肩": ["肩", "肩(前部)", "肩(側部)", "肩(後部)"],
    "腕": ["二頭筋", "三頭筋"],
    "脚": ["大腿四頭筋", "ハムストリング", "臀部", "ふくらはぎ"],
    "体幹": ["体幹", "腹筋", "腹筋(下部)", "腹斜筋"],
}


def _match_exercise(exercise_name: str) -> list[str]:
    """種目名から部位リストを返す。部分一致で検索。"""
    exercise_name = exercise_name.strip()
    # 完全一致を優先
    if exercise_name in EXERCISE_MUSCLE_MAP:
        return EXERCISE_MUSCLE_MAP[exercise_name]
    # 部分一致
    for key, muscles in EXERCISE_MUSCLE_MAP.items():
        if key in exercise_name or exercise_name in key:
            return muscles
    return []


def analyze_training_balance(user_id: str, days: int = 14) -> dict:
    """直近 N 日間のトレーニング記録から部位バランスを分析する。

    Returns:
        {
            "trained": {"胸": 3, "背中": 2, ...},  # 部位ごとのセッション数
            "undertrained": ["脚", "体幹"],          # 不足している部位
            "exercises_done": {"ベンチプレス": 3, ...},  # 種目ごとの実施回数
            "last_trained": {"胸": "2026-03-21", ...},  # 各部位の最終トレ日
            "suggestions": ["脚のトレーニング（スクワット、レッグプレスなど）", ...],
        }
    """
    logs = get_recent_training_logs(user_id, limit=100)

    # 期間でフィルタ
    cutoff = datetime.now() - timedelta(days=days)
    recent_logs = []
    for lg in logs:
        try:
            log_date = datetime.fromisoformat(lg["date"].replace("Z", "+00:00"))
            if log_date.replace(tzinfo=None) >= cutoff:
                recent_logs.append(lg)
        except (ValueError, TypeError):
            recent_logs.append(lg)  # 日付パースできない場合は含める

    # 部位ごとのトレーニング回数を集計
    muscle_count: dict[str, int] = defaultdict(int)
    last_trained: dict[str, str] = {}
    exercises_done: dict[str, int] = defaultdict(int)

    for lg in recent_logs:
        exercise = lg["exercise"]
        exercises_done[exercise] += 1
        muscles = _match_exercise(exercise)
        for muscle in muscles:
            muscle_count[muscle] += 1
            last_trained[muscle] = lg["date"]

    # 大部位グループごとの集計
    group_count: dict[str, int] = {}
    for group, muscles in MAJOR_MUSCLE_GROUPS.items():
        group_count[group] = sum(muscle_count.get(m, 0) for m in muscles)

    # 不足部位の判定（0回 or 他の部位の平均の半分以下）
    undertrained = []
    if group_count:
        avg = sum(group_count.values()) / len(group_count) if group_count else 0
        threshold = max(avg * 0.5, 1)
        for group, count in group_count.items():
            if count < threshold:
                undertrained.append(group)

    # 不足部位に対する種目提案
    SUGGESTIONS = {
        "胸": "胸のトレーニング（ベンチプレス、ダンベルフライなど）",
        "背中": "背中のトレーニング（デッドリフト、ラットプルダウンなど）",
        "肩": "肩のトレーニング（ショルダープレス、サイドレイズなど）",
        "腕": "腕のトレーニング（アームカール、プレスダウンなど）",
        "脚": "脚のトレーニング（スクワット、レッグプレスなど）",
        "体幹": "体幹のトレーニング（プランク、アブローラーなど）",
    }
    suggestions = [SUGGESTIONS[g] for g in undertrained if g in SUGGESTIONS]

    return {
        "trained": dict(group_count),
        "undertrained": undertrained,
        "exercises_done": dict(exercises_done),
        "last_trained": last_trained,
        "suggestions": suggestions,
    }
