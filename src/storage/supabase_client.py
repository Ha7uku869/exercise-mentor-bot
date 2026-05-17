from supabase import create_client, Client
from src.config import get_settings


settings = get_settings()
# 型注釈つきの代入文 （settings から必要な値を取り出してクライアントを初期化）
client: Client = create_client(settings.supabase_url,settings.supabase_service_role_key)


def save_workout(record: dict) -> dict:
    """workouts テーブルに1件保存。保存後のレコード（id付き）を返す"""
    response = client.table("workouts").insert(record).execute()
    return response.data[0]  # 挿入後のレコードが配列で返るので、最初の要素を返す

def list_workouts(user_id: str | None = None, limit: int = 50) -> list[dict]:
    """新しい順に最大 limit 件取得。user_id 指定でユーザーごとに絞り込む。"""
    query = client.table("workouts").select("*")
    if user_id:
        query = query.eq("user_id", user_id)
    response = query.order("date", desc=True).limit(limit).execute()
    return response.data


def save_context_note(record: dict) -> dict:
    """context_notes テーブルに1件保存。保存後のレコードを返す。

    workout 以外の重要情報（怪我・目標・生活変化など）を記録する。
    """
    response = client.table("context_notes").insert(record).execute()
    return response.data[0]


def list_context_notes(user_id: str, limit: int = 20) -> list[dict]:
    """ユーザーごとに新しい順に最大 limit 件取得。

    LLM が応答を作るときの背景情報として使う。
    """
    response = (
        client.table("context_notes")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data

def save_chat_log(record: dict) -> dict:
    """chat_logs テーブルに1件保存。友人テストの改善分析用。"""
    response = client.table("chat_logs").insert(record).execute()
    return response.data[0]

if __name__ == "__main__":
    # 簡単な動作確認
    new_record = {
        "date": "2026-05-02",
        "exercise_name": "ベンチプレス",
        "weight": 60.0,
        "reps": 10,
        "sets": 3,
        "fatigue": 7,
        "motivation": 8,
        "memo": "重量UP"
    }
    saved = save_workout(new_record)
    print("Saved workout:", saved)

    workouts = list_workouts()
    print("Recent workouts:", workouts)