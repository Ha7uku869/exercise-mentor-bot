import { useState, useEffect, useMemo, useRef } from "react"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LabelList,
} from "recharts"
import "./App.css"

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000"
const USER_ID_STORAGE_KEY = "exercise-mentor:user_id"
const DISPLAY_NAME_STORAGE_KEY = "exercise-mentor:display_name"

function sanitizeDisplayName(raw) {
  // 空白除去 + 安全な文字だけ残す（英数字とひらがな・カタカナ・漢字・ハイフン）
  const trimmed = raw.trim()
  return trimmed.replace(/[^\p{L}\p{N}\-_]/gu, "").slice(0, 30)
}

async function deriveUserId(displayName, passphrase) {
  const source = `${displayName}:${passphrase}`
  const bytes = new TextEncoder().encode(source)
  const digest = await crypto.subtle.digest("SHA-256", bytes)
  const hex = [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
  return `u_${hex.slice(0, 32)}`
}

const CHART_MARGIN = { top: 52, right: 56, left: 12, bottom: 6 }

function WorkoutVolumeLabel({ x, y, value, index, data }) {
  if (!value || typeof x !== "number" || typeof y !== "number") return null

  const lines = String(value).split(" / ")
  const isFirst = index === 0
  const isLast = index === data.length - 1
  const textAnchor = isFirst ? "start" : isLast ? "end" : "middle"
  const textX = x + (isFirst ? 8 : isLast ? -8 : 0)
  const textY = y - lines.length * 13 - 8

  return (
    <text
      x={textX}
      y={textY}
      textAnchor={textAnchor}
      fill="#cfe7c0"
      fontSize={11}
      className="chart-point-label"
    >
      {lines.map((line, lineIndex) => (
        <tspan
          key={`${line}-${lineIndex}`}
          x={textX}
          dy={lineIndex === 0 ? 0 : 13}
        >
          {line}
        </tspan>
      ))}
    </text>
  )
}

function detectActivityType(records) {
  // 直近の記録からどのフィールドが使われているか推定し、グラフ種別を決める
  const has = (k) => records.some((r) => r[k] != null)
  if (has("weight") && (has("reps") || has("sets"))) return "strength"
  if (has("distance_km")) return "running"
  if (has("duration_minutes")) return "time"
  return "other"
}

function buildSessionLabel(w) {
  const parts = []
  if (w.weight != null && w.reps != null && w.sets != null) {
    parts.push(`${w.weight}kg×${w.reps}×${w.sets}`)
  } else if (w.weight != null) {
    parts.push(`${w.weight}kg`)
  }
  if (w.distance_km != null) parts.push(`${w.distance_km}km`)
  if (w.duration_minutes != null) parts.push(`${w.duration_minutes}分`)
  if (w.intensity != null && parts.length === 0) parts.push(`強度${w.intensity}`)
  return parts.join(" ")
}

function aggregateByDate(workouts, exerciseFilter) {
  const filtered = workouts.filter((w) => w.exercise_name === exerciseFilter)
  const type = detectActivityType(filtered)
  const byDate = new Map()
  for (const w of filtered) {
    const cur = byDate.get(w.date) ?? {
      date: w.date,
      primary: 0,
      secondary: 0,
      sessions: [],
    }
    if (type === "strength") {
      cur.primary = Math.max(cur.primary, w.weight ?? 0)
      cur.secondary += (w.weight ?? 0) * (w.reps ?? 0) * (w.sets ?? 0)
    } else if (type === "running") {
      cur.primary += w.distance_km ?? 0
      cur.secondary += w.duration_minutes ?? 0
    } else if (type === "time") {
      cur.primary += w.duration_minutes ?? 0
      cur.secondary = Math.max(cur.secondary, w.intensity ?? 0)
    }
    cur.sessions.push(buildSessionLabel(w))
    byDate.set(w.date, cur)
  }
  const data = [...byDate.values()]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((d) => ({ ...d, label: d.sessions.filter(Boolean).join(" / ") }))
  return { data, type }
}

const CHART_LABELS = {
  strength: { primary: "最大重量(kg)", secondary: "ボリューム(目安)" },
  running: { primary: "距離(km)", secondary: "時間(分・目安)" },
  time: { primary: "時間(分)", secondary: "強度(目安)" },
  other: { primary: "値", secondary: "" },
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [workouts, setWorkouts] = useState([])
  const [exercise, setExercise] = useState("")
  const [userId, setUserId] = useState(() => {
    try {
      const savedUserId = localStorage.getItem(USER_ID_STORAGE_KEY) ?? ""
      const savedDisplayName = localStorage.getItem(DISPLAY_NAME_STORAGE_KEY) ?? ""
      return savedUserId && savedDisplayName ? savedUserId : ""
    } catch {
      return ""
    }
  })
  const [displayName, setDisplayName] = useState(() => {
    try {
      return localStorage.getItem(DISPLAY_NAME_STORAGE_KEY) ?? ""
    } catch {
      return ""
    }
  })
  const [nameInput, setNameInput] = useState("")
  const [passphraseInput, setPassphraseInput] = useState("")
  const [showHelp, setShowHelp] = useState(false)
  const messagesRef = useRef(null)

  async function loadWorkouts(uid) {
    if (!uid) return
    try {
      const res = await fetch(
        `${API_BASE}/workouts?user_id=${encodeURIComponent(uid)}&limit=200`,
      )
      if (!res.ok) return
      const data = await res.json()
      setWorkouts(data.workouts ?? [])
    } catch (err) {
      console.error("loadWorkouts failed", err)
    }
  }

  useEffect(() => {
    if (userId) {
      loadWorkouts(userId)
    } else {
      setWorkouts([])
      setMessages([])
    }
  }, [userId])

  async function saveName() {
    const cleaned = sanitizeDisplayName(nameInput)
    const passphrase = passphraseInput.trim()
    if (!cleaned || passphrase.length < 4) return
    const derivedUserId = await deriveUserId(cleaned, passphrase)
    try {
      localStorage.setItem(USER_ID_STORAGE_KEY, derivedUserId)
      localStorage.setItem(DISPLAY_NAME_STORAGE_KEY, cleaned)
    } catch {}
    setUserId(derivedUserId)
    setDisplayName(cleaned)
    setNameInput("")
    setPassphraseInput("")
  }

  function logout() {
    if (!confirm("ログアウトしますか？")) return
    try {
      localStorage.removeItem(USER_ID_STORAGE_KEY)
      localStorage.removeItem(DISPLAY_NAME_STORAGE_KEY)
    } catch {}
    setUserId("")
    setDisplayName("")
  }

  useEffect(() => {
    const messageList = messagesRef.current
    if (!messageList) return
    messageList.scrollTo({
      top: messageList.scrollHeight,
      behavior: "smooth",
    })
  }, [messages, loading])

  const exerciseOptions = useMemo(() => {
    const names = new Set(workouts.map((w) => w.exercise_name))
    return [...names].sort()
  }, [workouts])

  useEffect(() => {
    if (exerciseOptions.length === 0) return
    if (!exercise || !exerciseOptions.includes(exercise)) {
      setExercise(exerciseOptions[0])
    }
  }, [exerciseOptions, exercise])


  const { data: chartData, type: chartType } = useMemo(
    () => aggregateByDate(workouts, exercise),
    [workouts, exercise],
  )
  const labels = CHART_LABELS[chartType] ?? CHART_LABELS.other

  async function send() {
    const text = input.trim()
    if (!text || loading) return

    setMessages((m) => [...m, { role: "user", content: text }])
    setInput("")
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          display_name: displayName,
          message: text,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setMessages((m) => [...m, { role: "assistant", content: data.reply }])

      // workout が保存された可能性があるので一覧を再取得
      const savedWorkout = (data.saved ?? []).some(
        (s) => s.tool === "save_workout",
      )
      if (savedWorkout) {
        loadWorkouts(userId)
      }
    } catch (err) {
      console.error("chat failed", err) //ブラウザのDevToolsのConsoleタブにエラーを出すための標準API
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `一時的に応答に失敗しました。少し時間を置いてもう一度試してください。`},
      ])
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  if (!userId) {
    return (
      <div className="app">
        <header className="app-header">
          <h1>運動メンター</h1>
        </header>
        <section className="name-gate">
          <h2>はじめまして</h2>
          <p>
            あなたの記録を分けて保存するために、ニックネームと合言葉を入力してください。
            <br />
            <small>
            合言葉は保存せず、ブラウザ上で識別用IDに変換します。
            <br />
            改善のため、入力された運動記録やチャット内容を開発者が確認する場合があります。
            <br />
            個人情報や見られたくない内容は入力しないでください。
            </small>
          </p>
          <div className="name-form">
            <input
              lang="ja"
              autoComplete="nickname" 
              type="text"
              placeholder="例: haruku, alice, りんご"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  saveName()
                }
              }}
              autoFocus
            />
            <input
              type="password"
              placeholder="合言葉（4文字以上）"
              value={passphraseInput}
              onChange={(e) => setPassphraseInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  saveName()
                }
              }}
            />
            <button
              onClick={saveName}
              disabled={
                !sanitizeDisplayName(nameInput) ||
                passphraseInput.trim().length < 4
              }
            >
              はじめる
            </button>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>運動メンター</h1>
        <div className="user-tag">
          <button
            type="button"
            className="help-btn"
            aria-label="ヘルプ"
            onClick={() => setShowHelp((v) => !v)}
          >
            ?
          </button>
          <button
            type="button"
            className="link-btn"
            title="クリックでログアウト"
            onClick={logout}
          >
            {displayName}
          </button>
        </div>
      </header>

      {showHelp && (
        <>
          <div
            className="help-overlay"
            onClick={() => setShowHelp(false)}
          />
          <div className="help-tooltip" role="dialog">
            <strong>「運動メンター」とは？</strong>
            <p>
              このアプリは、運動や筋トレを頑張りたいと思っているユーザーを対象とした、記録ツールです。
            </p>
            <p>
              例えば、筋トレのベンチプレスをした後に、「今日は50kgのベンチを8回3セットできた！」のように、話しかけるようにメッセージを送ってみると、自動でグラフにして自分の頑張りを見やすく記録・表示してくれます。
            </p>
          </div>
        </>
      )}


      <section className="dashboard">
        <div className="dashboard-controls">
          <label>
            種目:
            <select
              value={exercise}
              onChange={(e) => setExercise(e.target.value)}
            >
              {exerciseOptions.length === 0 && (
                <option value="" disabled>種目がありません</option>
              )}
              {exerciseOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <span className="count-pill">
            記録: {chartData.length} 日分
          </span>
        </div>

        <div className="chart-wrap">
          {chartData.length === 0 ? (
            <p className="hint">
              {exercise
                ? `まだ ${exercise} の記録がありません。`
                : "まだ記録がありません。チャットで「ベンチ60kg×8を3セット」「30分ランニング5km」「ヨガ60分」のように送ってみてください。"}
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart
                data={chartData}
                margin={CHART_MARGIN}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis
                  dataKey="date"
                  stroke="#aaa"
                  padding={{ left: 28, right: 28 }}
                />
                <YAxis
                  yAxisId="left"
                  stroke="#5b9bd5"
                  width={48}
                  label={{
                    value: labels.primary,
                    angle: -90,
                    position: "insideLeft",
                    fill: "#5b9bd5",
                  }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  hide
                />
                <Tooltip
                  contentStyle={{
                    background: "#1e1e1e",
                    border: "1px solid #444",
                  }}
                />
                <Legend />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="primary"
                  name={labels.primary}
                  stroke="#5b9bd5"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="secondary"
                  name={labels.secondary}
                  stroke="#70ad47"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                >
                  <LabelList
                    dataKey="label"
                    content={(props) => (
                      <WorkoutVolumeLabel {...props} data={chartData} />
                    )}
                  />
                </Line>
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      <section className="messages" ref={messagesRef}>
        {messages.length === 0 && (
          <p className="hint">
            例:「今日ベンチ60kg×8を3セットやった」「30分ランニングして5km走った」「ヨガ60分」「肩痛めた、来週まで休む」
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <span className="role">{m.role === "user" ? "あなた" : "AI"}</span>
            <p>{m.content}</p>
          </div>
        ))}
        {loading && <p className="hint">考え中…</p>}
      </section>

      <div className="input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="メッセージを入力 (Enter送信 / Shift+Enter改行)"
          rows={2}
        />
        <button onClick={send} disabled={loading || !input.trim()}>
          送信
        </button>
      </div>
    </div>
  )
}
