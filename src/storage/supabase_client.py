from supabase import create_client, Client
from src.config import get_settings


settings = get_settings()
# 型注釈つきの代入文 （settings から必要な値を取り出してクライアントを初期化）
client: Client = create_client(settings.supabase_url,settings.supabase_service_role_key)


def save_workout(record: dict) -> dict:
    """workouts テーブルに1件保存。保存後のレコード（id付き）を返す"""
    response = client.table("workouts").insert(record).execute()
    return response.data[0]  # 挿入後のレコードが配列で返るので、最初の要素を返す

def list_workouts(limit: int=50) -> list[dict]:
    """新しい順に最大 limit 件取得"""
    response = client.table("workouts").select("*").order("date", desc=True).limit(limit).execute()
    return response.data  # 取得したレコードのリストを返す

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