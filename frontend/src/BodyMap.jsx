import Model from "react-body-highlighter"

// 自前タクソノミー(11) → ライブラリ筋肉slug の変換表（フロント専用）
export const PART_TO_MUSCLES = {
  chest:      ["chest"],
  shoulders:  ["front-deltoids", "back-deltoids"],
  back:       ["trapezius", "upper-back", "lower-back"],
  biceps:     ["biceps"],
  triceps:    ["triceps"],
  forearms:   ["forearm"],
  abs:        ["abs", "obliques"],
  glutes:     ["gluteal"],
  quads:      ["quadriceps"],
  hamstrings: ["hamstring"],
  calves:     ["calves"],
}

// 逆引き：ライブラリ筋肉slug → 自前slug（クリック判定で使う）
const MUSCLE_TO_PART = {}
for (const [part, muscles] of Object.entries(PART_TO_MUSCLES)) {
  for (const m of muscles) MUSCLE_TO_PART[m] = part
}

export default function BodyMap({ soreParts = [], onSelectPart }) {
  // 筋肉痛の部位を data として渡すと、その筋肉が色付く
  const data = soreParts.map((part) => ({
    name: part,
    muscles: PART_TO_MUSCLES[part] ?? [],
  }))

  function handleClick({ muscle }) {
    const part = MUSCLE_TO_PART[muscle]   // ライブラリ名 → 自前slugへ翻訳
    if (part) onSelectPart?.(part)
  }

  return (
    <div className="body-map">
      <Model data={data} onClick={handleClick} type="anterior"
             highlightedColors={["#e53935"]} />
      <Model data={data} onClick={handleClick} type="posterior"
             highlightedColors={["#e53935"]} />
    </div>
  )
}
export const PART_LABELS = {
  chest: "胸", shoulders: "肩", back: "背中", biceps: "二頭",
  triceps: "三頭", forearms: "前腕", abs: "腹", glutes: "臀",
  quads: "前もも", hamstrings: "裏もも", calves: "ふくらはぎ",
}