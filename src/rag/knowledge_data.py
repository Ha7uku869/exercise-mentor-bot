"""エビデンスベースの筋トレ知識データ。

論文やレビュー記事の知見を構造化して格納する。
各エントリは以下のフィールドを持つ:
- category: カテゴリ名
- text: LLM に渡す日本語テキスト
- embed_text: ベクトル検索用の英語テキスト（英語モデルでの検索精度向上のため）
- source: 出典

--- 技術解説: 英語埋め込み + 日本語テキストの二重構造 ---
使用している埋め込みモデル（BAAI/bge-small-en-v1.5）は英語特化のため、
日本語テキストの意味検索精度が低い。
そこで検索用には英語のサマリーを使い、LLM に渡すテキストは日本語のまま保持する。
これにより検索精度と応答の自然さを両立できる。

--- 出典について ---
知識はスポーツ科学の主要なメタ分析・レビュー論文に基づく。
個人の経験則ではなく、複数の研究を統合した知見を優先している。
"""

KNOWLEDGE_ENTRIES: list[dict[str, str]] = [
    # === トレーニングボリュームと頻度 ===
    {
        "category": "トレーニングボリューム",
        "embed_text": (
            "How many sets per week for muscle growth? "
            "Training volume sets reps hypertrophy. "
            "10 to 20 sets per muscle group per week is recommended."
        ),
        "text": (
            "筋肥大には週あたりのトータルボリューム（セット数×レップ数×重量）が重要。"
            "1部位あたり週10〜20セットが推奨される。"
            "週10セット未満では効果が減少し、週20セット以上では回復が追いつかない可能性がある。"
        ),
        "source": "Schoenfeld et al., 2017 - Dose-response relationship between weekly resistance training volume and increases in muscle mass",
    },
    {
        "category": "トレーニング頻度",
        "embed_text": (
            "How often should I train each muscle? "
            "Training frequency muscle protein synthesis. "
            "Training each muscle twice per week is better than once."
        ),
        "text": (
            "同じ部位を週2回以上トレーニングすると、週1回よりも筋肥大効果が高い。"
            "これは筋タンパク質合成（MPS）が刺激後24〜48時間でピークに達するため。"
            "週の総ボリュームが同じなら、分割して頻度を上げた方が効果的。"
        ),
        "source": "Schoenfeld et al., 2016 - Effects of Resistance Training Frequency on Measures of Muscle Hypertrophy",
    },
    # === プログレッシブオーバーロード ===
    {
        "category": "プログレッシブオーバーロード",
        "embed_text": (
            "How to get stronger and increase weight? "
            "Progressive overload strength gains. "
            "Gradually increase weight, reps, or sets over time."
        ),
        "text": (
            "筋力・筋肥大の継続的な向上には漸進的過負荷（プログレッシブオーバーロード）が不可欠。"
            "重量、レップ数、セット数のいずれかを段階的に増やしていく。"
            "毎回重量を増やす必要はなく、レップ数を1回増やすだけでも過負荷になる。"
        ),
        "source": "ACSM Position Stand, 2009 - Progression Models in Resistance Training for Healthy Adults",
    },
    {
        "category": "停滞期の対処",
        "embed_text": (
            "Strength plateau not getting stronger stuck stalled. "
            "How to break through a training plateau. "
            "Deload week, change exercises, review sleep and nutrition."
        ),
        "text": (
            "筋力の停滞（プラトー）は正常な適応反応であり、才能がないことを意味しない。"
            "対策として: (1)ディロード週（負荷を40〜60%に落とす回復期間）を設ける、"
            "(2)トレーニング変数（種目、レップレンジ、テンポ）を変更する、"
            "(3)睡眠・栄養を見直す。停滞は成長の通過点。"
        ),
        "source": "Pritchard et al., 2015 - Tapering Practices of Strength Athletes",
    },
    # === 休息とリカバリー ===
    {
        "category": "休息の重要性",
        "embed_text": (
            "Is it ok to skip the gym? Rest day recovery overtraining. "
            "Skipping a workout is not failure. "
            "Muscles grow during rest, not during training. 48-72 hours rest between sessions."
        ),
        "text": (
            "筋肉はトレーニング中ではなく休息中に成長する。"
            "同じ部位のトレーニング間に48〜72時間の休息を取ることが推奨される。"
            "オーバートレーニングは筋力低下、疲労蓄積、免疫低下を引き起こす。"
            "休息日を取ることはサボりではなく、成長のための戦略的な選択。"
        ),
        "source": "Kreher & Schwartz, 2012 - Overtraining Syndrome: A Practical Guide",
    },
    {
        "category": "睡眠と筋肉",
        "embed_text": (
            "Sleep and muscle growth. Not sleeping enough tired. "
            "Growth hormone is released during sleep. "
            "Less than 6 hours reduces testosterone and muscle protein synthesis. 7-9 hours recommended."
        ),
        "text": (
            "睡眠中に成長ホルモンが分泌され、筋肉の修復と成長が促進される。"
            "睡眠不足（6時間未満）はテストステロンの低下や筋タンパク質合成の減少を招く。"
            "7〜9時間の睡眠が筋トレの効果を最大化するために推奨される。"
        ),
        "source": "Dattilo et al., 2011 - Sleep and muscle recovery",
    },
    # === 栄養 ===
    {
        "category": "タンパク質摂取",
        "embed_text": (
            "How much protein should I eat per day? "
            "Protein intake grams per kg for muscle building. "
            "1.6 to 2.2 grams per kg body weight. Spread across 3-4 meals."
        ),
        "text": (
            "筋肥大を目的とする場合、体重1kgあたり1.6〜2.2gのタンパク質摂取が推奨される。"
            "一度に吸収できるタンパク質量に上限はあるが（約40g程度）、"
            "余剰分も時間をかけて利用されるため、1食の量を過度に気にする必要はない。"
            "タンパク質を3〜4回の食事に分散させるのが理想的。"
        ),
        "source": "Morton et al., 2018 - A systematic review of protein requirements for muscle mass",
    },
    {
        "category": "カロリーと体組成",
        "embed_text": (
            "Can I build muscle and lose fat at the same time? "
            "Body recomposition bulking cutting calories. "
            "Possible for beginners, harder for advanced lifters. Separate bulk and cut phases."
        ),
        "text": (
            "筋肉を増やしながら脂肪を減らす（ボディリコンポジション）は、"
            "初心者やトレーニング再開者では可能だが、上級者では難しい。"
            "増量期（カロリー余剰）と減量期（カロリー不足）を分けるのが効率的。"
            "減量中も十分なタンパク質摂取と筋トレを継続することで筋量の維持が可能。"
        ),
        "source": "Barakat et al., 2020 - Body Recomposition: Can Trained Individuals Build Muscle and Lose Fat at the Same Time?",
    },
    # === フォームとケガ予防 ===
    {
        "category": "フォームの重要性",
        "embed_text": (
            "Proper form technique injury prevention range of motion. "
            "Good form prevents injury and targets muscles effectively. "
            "Don't obsess over perfect form but maintain safe range of motion."
        ),
        "text": (
            "正しいフォームは怪我の予防と対象筋への効果的な刺激の両方に重要。"
            "ただし「完璧なフォーム」に固執しすぎると重量の進歩を妨げることがある。"
            "多少のフォームの崩れは許容範囲で、重要なのは安全な可動域の確保。"
            "フォームが大きく崩れる重量は扱うべきではない。"
        ),
        "source": "Schoenfeld & Grgic, 2020 - Evidence-Based Guidelines for Resistance Training",
    },
    {
        "category": "ケガへの対応",
        "embed_text": (
            "Muscle soreness DOMS pain after workout. "
            "Is soreness a sign of a good workout? "
            "DOMS is normal but not an indicator of effectiveness. Joint pain needs medical attention."
        ),
        "text": (
            "軽度の筋肉痛（DOMS）は正常な反応であり、トレーニングの効果の指標ではない。"
            "筋肉痛がなくても筋肥大は起きる。筋肉痛が強すぎる場合はボリュームの増やしすぎ。"
            "関節の痛みや鋭い痛みは筋肉痛とは異なり、休息や医療相談が必要。"
        ),
        "source": "Schoenfeld & Contreras, 2013 - Is DOMS an accurate indicator of muscle damage?",
    },
    # === メンタルと継続性 ===
    {
        "category": "モチベーション",
        "embed_text": (
            "No motivation to go to gym. Skipped workout feel lazy. "
            "How to stay consistent with training. "
            "Build habits, 50% effort days are fine, don't aim for perfection."
        ),
        "text": (
            "モチベーションは波があるのが普通。やる気がない日もトレーニングを続けるには、"
            "「習慣化」が鍵。週3回など決まった日に行く仕組みを作る。"
            "完璧を求めず、「今日は軽くやるだけでもOK」というマインドセットが継続に繋がる。"
            "0か100かではなく、50%の日があっても全く問題ない。"
        ),
        "source": "Lally et al., 2010 - How are habits formed: Modelling habit formation in the real world",
    },
    {
        "category": "他者との比較",
        "embed_text": (
            "Comparing myself to others on social media. "
            "Everyone is stronger than me, no talent genetics. "
            "Growth rate depends on genetics. Compare only to your past self."
        ),
        "text": (
            "SNSで見る筋トレ上級者と自分を比較するのは非生産的。"
            "筋肉の成長速度は遺伝（筋繊維組成、テストステロンレベル等）に大きく影響される。"
            "比較すべきは過去の自分のみ。1ヶ月前の自分より進歩していれば順調。"
            "初心者は最初の1年で最も大きな伸びが期待でき、その後は徐々に緩やかになる（対数的成長）。"
        ),
        "source": "Ericsson et al., 1993 - The Role of Deliberate Practice; Hubal et al., 2005 - Variability in muscle size and strength gain",
    },
    # === ベンチプレス特化 ===
    {
        "category": "ベンチプレス",
        "embed_text": (
            "How to increase bench press weight. Bench press plateau chest. "
            "Train bench 2+ times per week, use 5x5 or 3x3, "
            "add accessories like close-grip bench, dips, shoulder press, pause reps."
        ),
        "text": (
            "ベンチプレスの重量を伸ばすには: "
            "(1)週2回以上の頻度でベンチプレスを行う、"
            "(2)5×5や3×3などの低レップ高重量セットを組み込む、"
            "(3)補助種目（ナローベンチ、ディップス、ショルダープレス）で弱点を補強する、"
            "(4)パウズベンチ（胸の上で一時停止）でボトムの強さを鍛える。"
        ),
        "source": "Greg Nuckols, Stronger By Science - How to Bench Press",
    },
    # === スクワット特化 ===
    {
        "category": "スクワット",
        "embed_text": (
            "Squat depth form legs plateau. "
            "How to improve squat. Full range of motion is best for hypertrophy. "
            "Use front squat and pause squat variations to overcome weaknesses."
        ),
        "text": (
            "スクワットの深さはフルレンジ（大腿が水平以下）が筋肥大に最も効果的。"
            "ただし個人の柔軟性に応じて深さを調整すべき。"
            "重量が停滞した場合はフロントスクワットやポーズスクワットなどの"
            "バリエーションを取り入れることで弱点を克服できる。"
        ),
        "source": "Schoenfeld, 2010 - Squatting kinematics and kinetics; Hartmann et al., 2012 - Analysis of the load on the knee joint",
    },
    # === デッドリフト特化 ===
    {
        "category": "デッドリフト",
        "embed_text": (
            "Deadlift technique back lower back belt. "
            "Conventional vs sumo deadlift. "
            "Keep back straight, use belt for heavy sets, manage weekly volume."
        ),
        "text": (
            "デッドリフトは全身の筋力を最も効率的に鍛えられる種目の一つ。"
            "コンベンショナルとスモウの両スタイルがあり、体格に応じて選ぶべき。"
            "腰を丸めないことが最重要で、ベルトの使用は高重量時に推奨される。"
            "週の総ボリュームを管理し、回復に十分な時間を取ること。"
        ),
        "source": "Cholewicki et al., 1991 - Lumbar spine loads during the deadlift",
    },
]
