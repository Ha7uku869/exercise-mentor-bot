# セッション進捗メモ 2026-06-09

## このセッションでやったこと

Phase 2「LLM抽出テスト・評価基盤」の**設計と基盤を完成**させた。
経路A（Web `/api/chat` の Function Calling）を対象に、24ケースのpytest評価スイートを作り、
**完走したLLM判定23件で正答率100%**、既知の失敗1件(X1)を xfail として明示した。

---

## 決めたこと（設計判断）

1. **テスト対象 = 経路A（Function Calling）**
   - `chat_with_tools` + `TOOLS` が `save_workout` / `save_context_note` を「呼ぶ/呼ばない」を判定。
   - 経路B（LINE の `extract_profile`）ではなく、デモ・友人FB・Phase1で触った本番経路を選択。
2. **判断は2択でなく3分類**: `save_workout` / `save_context_note` / なし(text)。
3. **境界の軸**: 「質問かどうか」ではなく **「持続性・将来の提案への影響があるか」**。
   一時的な気分（疲れた・眠い・今日は調子いい）は運動に関係しても保存しない。
4. **論点1（睡眠/体調）= 方針(b)**: 期待値は `save_context_note` のまま残し、
   テストを意図的に失敗(xfail)させ「プロンプト改善の宿題」としてREADMEに記録する方針。

詳細な判断仕様・24ケース表は `docs/phase2-extraction-spec.md`。

---

## 作った/変えたもの

| ファイル | 内容 |
|---|---|
| `docs/phase2-extraction-spec.md` | 判断仕様＋24ケース表＋論点（新規） |
| `tests/test_extraction.py` | 評価スイート（純粋ユニット2件＋LLM24ケース）（新規） |
| `pyproject.toml` | `pytest-asyncio` 追加、`[tool.pytest.ini_options]`（asyncio_mode=auto, testpaths）追加 |
| `src/llm/client.py` | `chat_with_tools` に `temperature=0` 追加（判定を決定的に） |
| `src/api/main.py` | `_build_chat_system_prompt(user_id, notes=None)` に変更（DB取得と整形を分離＝テスト可能化） |

---

## 結果

```
25 passed, 1 xfailed in 149.16s
```
- 純粋ユニットテスト2件（`_decision`）: 即緑。
- LLM判定23件（W1-W8 / C1-C9 / N1-N6）: **全件正解（正答率100%）**。
- X1（最近よく眠れてて調子いい）: 設計通り **XFAIL**。
- 初回実行ではC6・N2が `RateLimitError(429)` で落ちたが、これは分類ミスではなく
  Groq無料枠の **TPM(12000 tokens/min) 超過**。`_run` に `asyncio.sleep(5)` のthrottleを入れて解消。

---

## なぜこの実装か（面接で聞かれたとき用）

- **再現性の3点セット**（設計質問#5への答え）:
  1. `temperature=0` で源流の揺れを抑える（判定は決定的にしたい。ユーザー向け返答 `chat`/`chat_after_tools` は自然さ優先で既定値のまま＝用途で温度を使い分け）。
  2. LLMを呼ばない純粋ロジック(`_decision`)は決定的テストに分離（落ちたら自分のバグと断定できる）。
  3. LLM判定は「二値の合否ゲート」でなく**正答率の評価**として扱い、既知の失敗は xfail で明示。
- **テスト可能化のための責務分離**: `_build_chat_system_prompt` を「DB取得」と「文字列組み立て」に分け、テストは `notes=[]` を渡してDBに触れずに本番プロンプトを検証。
- **テストが意図とプロンプトのズレを暴いた(X1)**: 「保存したい」意図とプロンプトの指示がズレていることをテストで発見＝評価データを持つ価値の実例。

---

## このセッションで学んだこと

- LLMテストの失敗は3種類ある: ①アプリのバグ ②LLMの気まぐれ(非決定性) ③インフラ制約(レート制限)。混同しないことが重要。
- `429 RateLimitError` は「残量ゼロ」ではなく「1分あたりの速度超過(TPM)」。鍵を替えるのではなく、throttle/retry/backoff で対処する。これは友人Tの「API利用量制限」指摘を実体験したもの。
- マルチPython環境では `python -m pip` を使い、インストール先とテスト実行先のpythonを一致させる。
- `pytest.mark.parametrize` で1関数に複数データを流し、`pytest.param(..., id=)` でケースIDを付けると、どのケースが落ちたか特定できる。
- `xfail` は「落ちて当然」を宣言する印。将来直って通ると `XPASS` で気づける。

---

## 既知のTODO（今後・今回は未着手）

- **Phase 2仕上げ候補**: categoryレベル(injury/goal/lifestyle)の検証 / 1発話で複数tool呼ぶケース /
  `@pytest.mark.llm` でCIゲート(決定的)と評価スイート(LLM)を分離 / README に失敗ケース記録。
- **コードの小整理（Phase 6）**: `src/api/main.py` 34-49行の重複import、`docs/` の重複ファイル
  （`feedback-v1 (1).md`, `session-progress-2026-06-08 (1).md`）削除、venv化。
- **将来の改善（要件に書く価値あり）**: context_notes の retrieval を「新しい順10件」から
  RAG意味検索/グラフ(Phase 4)へ。`valid_until` 期限切れnoteのフィルタはLLM任せ→コードで処理。

---

## 次セッション最初にやること

`docs/current-task.md` の選択肢から1つ選ぶ:
- A. Phase 2仕上げ（上記TODOのどれか）
- B. Phase 3「記憶カードUI」へ進む

着手前に、今回の **面接30秒説明を自分の言葉で言えるか** を1回声に出して確認する。
