import json
import sys
import time
from pathlib import Path

from client import call_llm
from validator import validate_and_fix


MOCK_SCORE = {
    "bpm": 96,
    "key": "C",
    "bars": 8,
    "chords": [
        {"bar": 0, "symbol": "C"},
        {"bar": 1, "symbol": "Am"},
        {"bar": 2, "symbol": "F"},
        {"bar": 3, "symbol": "G"},
    ],
    "melody": [
        {"bar": b, "note": n, "start": s, "dur": 2, "velocity": 70}
        for b in range(8)
        for n, s in [
            (60, 0),
            (64, 4),
            (67, 8),
            (72, 12),
        ]
    ],
    "title": "测试曲",
    "description": "离线mock输出，用于链路自检。",
}


def main():

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = sys.argv[1:]

    use_mock = "--mock" in args

    paths = [
        a for a in args if not a.startswith("--")
    ]

    if not paths:

        print(
            "用法: demo.py <画像.json> [--mock]"
        )

        sys.exit(1)

    with open(paths[0], encoding="utf-8") as f:

        profile = json.load(f)

    # ---------- 生成 ----------

    t0 = time.perf_counter()

    if use_mock:

        time.sleep(0.1)

        score = dict(MOCK_SCORE)

        meta = {
            "latency_s": 0.1,
            "attempts": 1,
            "model": "mock",
        }

    else:

        try:

            score, meta = call_llm(profile)

        except RuntimeError as e:

            print(f"[LLM失败] {e}")

            print("回退规则作曲...")

            sys.path.insert(
                0,
                str(
                    Path(__file__)
                    .resolve()
                    .parent.parent
                    / "music"
                ),
            )

            from composer_rule import compose

            score = compose(profile, seed=42)

            meta = {
                "latency_s": round(
                    time.perf_counter() - t0, 2
                ),
                "attempts": 1,
                "model": "rule-fallback",
            }

    # ---------- 校验 ----------

    score, fixes, fatals = validate_and_fix(
        score
    )

    if fatals:

        print(f"[致命错误] {fatals}，需人工介入")

        sys.exit(1)

    # ---------- 输出 ----------

    out = Path(paths[0]).with_name(
        "llm_score.json"
    )

    with open(
        out,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            score,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"[来源] {meta['model']} "
          f"| 延迟 {meta['latency_s']}s "
          f"| 尝试 {meta['attempts']}次")

    print(f"[音符] {len(score['melody'])}个 "
          f"| {score['bars']}小节 "
          f"| {score['bpm']}BPM")

    print(f"[曲名] {score['title']}")

    if fixes:

        print(f"[修复] {len(fixes)}处: {fixes[:5]}")

    print(f"[已保存] {out}")


if __name__ == "__main__":

    main()
