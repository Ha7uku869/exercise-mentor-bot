# 運動メンターBot

運動の記録を自然な会話でLINEに送るだけで、LLMが内容を構造化して保存し、エビデンスベースの知識と過去の記録を踏まえてトレーニング提案を返すパーソナルメンターAIです。

## 機能概要

| 機能 | 説明 |
|---|---|
| **自然言語での運動記録** | 「今日ベンチ80kg×5×3やった」と送ると Function Calling で自動保存 |
| **文脈記憶** | 怪我・目標・生活変化などをコンテキストノートとして保持し、提案に反映 |
| **RAGによる知識検索** | スポーツ科学のメタ分析・レビュー論文を構造化した知識ベースから関連情報を取得 |
| **部位バランス分析** | 直近の記録から種目→筋肉部位のマッピングを行い、不足部位を検出 |
| **Webダッシュボード** | ワークアウト量の時系列グラフ、チャット履歴をブラウザで確認 |
| **LINE Bot** | LINE Messaging API 経由でスマートフォンから利用可能 |

## アーキテクチャ

```
[LINE] ──────────────────────────────────────────────────────
  ユーザー発話
    └─► /callback (FastAPI)
          ├─ 署名検証
          ├─ respond() → RAG検索 + Groq API (Llama 3.3 70B)
          └─ 返信

[Web UI (React/Vite)] ──────────────────────────────────────
  チャット入力
    └─► /api/chat (FastAPI)
          ├─ Function Calling → save_workout / save_context_note
          │       └─► Supabase (workout_logs, context_notes, chat_logs)
          ├─ _build_chat_system_prompt() → context_notesを注入
          └─ Groq API → 返信テキスト

[ダッシュボード] ────────────────────────────────────────────
  /api/dashboard/{user_id}
    ├─ トレーニング履歴 (Supabase)
    ├─ 部位バランス分析 (training_analyzer)
    └─ 会話履歴 (SQLite)
```

## Tech Stack

| レイヤー | 技術 |
|---|---|
| バックエンド | Python 3.12, FastAPI |
| LLM | Groq API (Llama 3.3 70B) |
| RAG | BAAI/bge-small-en-v1.5（英語埋め込み + 日本語テキストの二重構造） |
| ストレージ | SQLite（会話履歴）/ Supabase（ワークアウトログ・コンテキストノート） |
| フロントエンド | React, Vite, Recharts |
| LINE連携 | LINE Messaging API (linebot-sdk v3) |
| ホスティング | Render |

## セットアップ

### 1. 環境変数

```bash
cp .env.example .env
```

`.env` に以下を設定:

| 変数名 | 取得先 |
|---|---|
| `LINE_CHANNEL_SECRET` | [LINE Developers Console](https://developers.line.biz/console/) |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Developers Console |
| `GROQ_API_KEY` | [Groq Console](https://console.groq.com/) |
| `SUPABASE_URL` | Supabase プロジェクト設定 |
| `SUPABASE_KEY` | Supabase プロジェクト設定 |

### 2. インストール・起動

```bash
pip install -e ".[dev]"
cd frontend && npm install && cd ..
.\dev.ps1        # PowerShell: バックエンドとフロントを同時起動
```

バックエンドのみ:
```bash
uvicorn src.api.main:app --reload
```

### 3. LINE Bot との接続（開発時）

```bash
ngrok http 8000
```

発行されたURLを LINE Developers Console の Webhook URL に設定:
`https://xxxx.ngrok-free.dev/callback`

## プロジェクト構成

```
src/
├── api/main.py              # FastAPI + LINE Webhook + /api/chat
├── llm/client.py            # Groq API クライアント（Function Calling対応）
├── bias/
│   ├── prompts.py           # システムプロンプト定義
│   └── detector.py          # LINE Bot 応答生成
├── rag/
│   ├── knowledge_data.py    # エビデンスベースの筋トレ知識データ
│   ├── embedder.py          # テキスト埋め込み
│   ├── retriever.py         # ベクトル検索
│   └── store.py             # 知識ストア管理
├── storage/
│   ├── memory.py            # SQLite 会話履歴
│   ├── supabase_client.py   # Supabase CRUD
│   ├── profile_extractor.py # ユーザープロフィール抽出
│   └── training_analyzer.py # 部位バランス分析
├── training/                # トレーニング関連ロジック
└── config.py                # 環境変数管理 (pydantic-settings)
frontend/
├── src/App.jsx              # チャットUI + ワークアウトグラフ (Recharts)
└── ...
```

## 設計上の工夫

- **Function Callingによる構造化**: 「今日スクワット60kg×10×4やった」のような自然文から、date/exercise_name/weight/reps/sets を自動抽出してSupabaseに保存。
- **RAGの英日二重構造**: 埋め込みモデル(BAAI/bge-small-en-v1.5)が英語特化のため、検索用に英語サマリー・LLMへの入力に日本語テキストを使い分けることで検索精度と応答品質を両立。
- **コンテキストノートのシステムプロンプト注入**: 怪我・目標などの長期情報をSupabaseに保存し、毎回のシステムプロンプトに挿入することで、LLMが個人文脈を保持した提案を継続的に行える。
- **ユーザー識別**: 表示名とパスフレーズのSHA-256ハッシュでuser_idを生成し、認証基盤なしでユーザー分離を実現。

## Roadmap

- [x] Phase 1: LINE Bot + LLM対話 + RAG知識検索
- [x] Phase 2: Function Calling によるワークアウト記録 / Supabase 永続化
- [x] Phase 2.5: Webダッシュボード + 会話ログ復元 + 部位バランス分析
- [ ] Phase 3: 記憶カードUI（AIが何を覚えているか可視化）
- [ ] Phase 4: ユーザー文脈グラフ（提案根拠の可視化）
- [ ] Phase 5: Multi-Agent化（Extractor / Retriever / Coach / Safety の責務分離）
