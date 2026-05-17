"""アプリケーション設定を環境変数から読み込むモジュール。

pydantic-settings の BaseSettings を使うことで、
.env ファイルや環境変数から自動的に値を読み込める。
型バリデーションも自動で行われるため、設定ミスを早期に検出できる。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数をマッピングするクラス。

    BaseSettings を継承すると、クラス変数名と同じ名前の環境変数を
    自動的に読み込む。例: LINE_CHANNEL_SECRET → self.line_channel_secret

    model_config で .env ファイルのパスやエンコーディングを指定している。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # LINE Messaging API の認証情報（Web版では未設定でも動作）
    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    # Groq API のキー
    groq_api_key: str

    # Qdrant（ベクトルDB）の接続情報
    qdrant_url: str = ""
    qdrant_api_key: str = ""

    # HuggingFace Inference API のトークン（埋め込みベクトル生成に使用）
    hf_api_token: str = ""
    
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""


# シングルトン的に1つのインスタンスを使い回す。
# ただし、テスト時に差し替えやすいよう関数経由で取得する。
_settings: Settings | None = None


def get_settings() -> Settings:
    """設定のシングルトンインスタンスを返す。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
