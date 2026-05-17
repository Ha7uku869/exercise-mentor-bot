"""ユーザーごとの会話履歴を SQLite に永続化するモジュール。

--- 技術解説: SQLite ---
SQLite はファイルベースの軽量データベース。
サーバーが再起動しても会話履歴が消えない。
Python 標準ライブラリに含まれているため追加インストール不要。

Render の無料プランではサーバーが頻繁に再起動するが、
SQLite ファイルが残っていれば会話を復元できる。
"""

import json
import sqlite3
from pathlib import Path

MAX_HISTORY = 10  # 直近10メッセージ（5往復分）をLLMに渡す

# DB ファイルのパス（プロジェクトルートの data/ 以下に保存）
_DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DB_PATH = _DB_DIR / "conversations.db"

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    """SQLite コネクションを取得する（初回のみ DB を初期化）。"""
    global _conn
    if _conn is None:
        _DB_DIR.mkdir(exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH))
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_id ON messages (user_id)"
        )
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT NOT NULL,
                field TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, field)
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS training_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                exercise TEXT NOT NULL,
                weight TEXT NOT NULL,
                reps INTEGER,
                sets INTEGER,
                note TEXT DEFAULT '',
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_training_user ON training_logs (user_id)"
        )
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS nutrition_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                item TEXT NOT NULL,
                type TEXT DEFAULT '',
                protein_g REAL,
                amount TEXT DEFAULT '',
                note TEXT DEFAULT '',
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nutrition_user ON nutrition_logs (user_id)"
        )
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS bias_detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                bias_type TEXT NOT NULL,
                user_message TEXT NOT NULL,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bias_user ON bias_detections (user_id)"
        )
        _conn.commit()
    return _conn


def get_history(user_id: str) -> list[dict[str, str]]:
    """指定ユーザーの直近の会話履歴をリストで返す。"""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT role, content FROM messages
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, MAX_HISTORY),
    ).fetchall()
    # DESC で取得したので逆順にして時系列順にする
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def add_message(user_id: str, role: str, content: str) -> None:
    """会話履歴にメッセージを1件追加する。"""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content),
    )
    conn.commit()


def get_profile(user_id: str) -> dict[str, str]:
    """ユーザープロフィールを辞書形式で返す。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT field, value FROM user_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return {field: value for field, value in rows}


def update_profile(user_id: str, updates: dict[str, str]) -> None:
    """プロフィールを更新する（既存フィールドは上書き）。"""
    conn = _get_conn()
    for field, value in updates.items():
        conn.execute(
            """
            INSERT INTO user_profiles (user_id, field, value)
            VALUES (?, ?, ?)
            ON CONFLICT (user_id, field) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, field, value),
        )
    conn.commit()


def add_training_log(user_id: str, log: dict) -> None:
    """トレーニング記録を1件追加する。"""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO training_logs (user_id, exercise, weight, reps, sets, note)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            log.get("exercise", ""),
            log.get("weight", ""),
            log.get("reps"),
            log.get("sets"),
            log.get("note", ""),
        ),
    )
    conn.commit()


def get_recent_training_logs(user_id: str, limit: int = 20) -> list[dict]:
    """直近のトレーニング記録を返す。"""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT exercise, weight, reps, sets, note, logged_at
        FROM training_logs
        WHERE user_id = ?
        ORDER BY logged_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [
        {
            "exercise": r[0],
            "weight": r[1],
            "reps": r[2],
            "sets": r[3],
            "note": r[4],
            "date": r[5],
        }
        for r in reversed(rows)
    ]


def add_nutrition_log(user_id: str, log: dict) -> None:
    """栄養・プロテイン記録を1件追加する。"""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO nutrition_logs (user_id, item, type, protein_g, amount, note)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            log.get("item", ""),
            log.get("type", ""),
            log.get("protein_g"),
            log.get("amount", ""),
            log.get("note", ""),
        ),
    )
    conn.commit()


def get_recent_nutrition_logs(user_id: str, limit: int = 20) -> list[dict]:
    """直近の栄養・プロテイン記録を返す。"""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT item, type, protein_g, amount, note, logged_at
        FROM nutrition_logs
        WHERE user_id = ?
        ORDER BY logged_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [
        {
            "item": r[0],
            "type": r[1],
            "protein_g": r[2],
            "amount": r[3],
            "note": r[4],
            "date": r[5],
        }
        for r in reversed(rows)
    ]


def add_bias_detection(user_id: str, bias_type: str, user_message: str) -> None:
    """認知の歪みの検知記録を保存する。"""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO bias_detections (user_id, bias_type, user_message) VALUES (?, ?, ?)",
        (user_id, bias_type, user_message),
    )
    conn.commit()


def get_bias_detections(user_id: str, limit: int = 100) -> list[dict]:
    """認知の歪みの検知履歴を返す。"""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT bias_type, user_message, detected_at
        FROM bias_detections
        WHERE user_id = ?
        ORDER BY detected_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [
        {"bias_type": r[0], "user_message": r[1], "detected_at": r[2]}
        for r in reversed(rows)
    ]


def get_bias_summary(user_id: str) -> dict:
    """認知の歪みの種類別集計と時系列データを返す。"""
    conn = _get_conn()
    type_rows = conn.execute(
        """
        SELECT bias_type, COUNT(*) as cnt
        FROM bias_detections
        WHERE user_id = ?
        GROUP BY bias_type
        ORDER BY cnt DESC
        """,
        (user_id,),
    ).fetchall()
    by_type = {r[0]: r[1] for r in type_rows}

    daily_rows = conn.execute(
        """
        SELECT DATE(detected_at) as day, COUNT(*) as cnt
        FROM bias_detections
        WHERE user_id = ?
        GROUP BY DATE(detected_at)
        ORDER BY day
        """,
        (user_id,),
    ).fetchall()
    by_date = [{"date": r[0], "count": r[1]} for r in daily_rows]

    return {"by_type": by_type, "by_date": by_date, "total": sum(by_type.values())}
