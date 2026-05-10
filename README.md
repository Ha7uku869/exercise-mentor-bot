# 筋トレメタ認知AI

筋トレに取り組む人が陥りがちな**認知バイアス（認知の歪み）**を対話を通じて検知し、より柔軟な考え方を提案する LINE Bot です。

## コンセプト

「今日サボったから全部台無しだ」「自分はいつもダメだ」——筋トレを続ける中で、こうした思考パターンに陥ったことはありませんか？

このBotは認知行動療法（CBT）の「10の認知の歪み」（David Burns, 1980）をベースに、ユーザーの発言から認知バイアスを検知し、リフレーミング（より柔軟な考え方）を提案します。

### 検知できる認知の歪み

| # | 歪みの種類 | 筋トレでの例 |
|---|---|---|
| 1 | 全か無か思考 | 「1日サボったら全部台無し」 |
| 2 | 過度の一般化 | 「いつも三日坊主だ」 |
| 3 | 心のフィルター | 成果を無視し、できなかったことだけに注目 |
| 4 | マイナス化思考 | 「ベンチプレスが伸びたのはたまたま」 |
| 5 | 結論の飛躍 | 「周りは自分のフォームが変だと思っている」 |
| 6 | 拡大解釈と過小評価 | 「1回休んだ = 筋肉が全部落ちる」 |
| 7 | 感情的決めつけ | 「やる気が出ない = 自分は怠け者」 |
| 8 | すべき思考 | 「毎日ジムに行くべきだ」 |
| 9 | レッテル貼り | 「サボった自分はダメ人間」 |
| 10 | 個人化 | 「仲間が来なくなったのは自分のせい」 |

## Tech Stack

- **Chat UI**: LINE Bot（Messaging API）
- **LLM**: Llama 3.3 70B（Groq API 経由）
- **Backend**: Python, FastAPI
- **Hosting**: Render

## Architecture

```
User (LINE) --> LINE Platform --> /callback (FastAPI)
    --> 署名検証 --> テキスト抽出 --> respond() (bias/detector)
    --> chat() (llm/client) --> Groq API (Llama 3.3 70B)
    --> 応答テキスト --> LINE に返信
```

## Setup

### 1. 環境変数の設定

```bash
cp .env.example .env
```

`.env` に以下を設定:

| 変数名 | 取得先 |
|---|---|
| `LINE_CHANNEL_SECRET` | [LINE Developers Console](https://developers.line.biz/console/) |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Developers Console |
| `GROQ_API_KEY` | [Groq Console](https://console.groq.com/) |

### 2. インストール

```bash
pip install -e ".[dev]"
cd frontend
npm install
```

### 3. 開発サーバーの起動

PowerShell でリポジトリルートから以下を実行:

```powershell
.\dev.ps1
```

バックエンドとフロントエンドが別々の PowerShell ウィンドウで起動します。

手動で起動する場合:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload

cd frontend
npm run dev
```

### 4. LINE Bot と接続（開発時）

```bash
ngrok http 8000
```

表示された URL を LINE Developers Console の Webhook URL に設定:
`https://xxxx.ngrok-free.dev/callback`

## Project Structure

```
src/
├── api/main.py        # FastAPI + LINE Webhook
├── llm/client.py      # Groq API client (OpenAI互換)
├── bias/
│   ├── prompts.py     # CBTベースのシステムプロンプト
│   └── detector.py    # バイアス検知の応答生成
├── config.py          # 環境変数管理 (pydantic-settings)
├── rag/               # Phase 2: RAGパイプライン
└── storage/           # Phase 2: 会話履歴保存
```

## Roadmap

- [x] Phase 1: LINE Bot + LLM対話 + 認知バイアス検知
- [ ] Phase 2: RAG による会話履歴の活用・バイアス分類の構造化
- [ ] Phase 3: 改善度可視化ダッシュボード

## References

- Burns, D. D. (1980). *Feeling Good: The New Mood Therapy*
- Wei, J. et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models"
