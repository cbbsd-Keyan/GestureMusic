import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from client import call_llm, TEMPLATES
from validator import validate_and_fix


# =========================
# 多样性 lint
# =========================

def opening_notes(score):

    m = sorted(
        score.get("melody", []),
        key=lambda x: (x["bar"], x["start"]),
    )

    return tuple(x["note"] for x in m[:3])


def progression_key(score):

    symbols = [
        c["symbol"]
        for c in score.get("chords", [])
    ]

    return "-".join(symbols[:4])


def lint_scores(scores):

    """
    批次多样性检查。
    返回 (问题列表, 统计文本)。
    """

    problems = []

    n = len(scores)

    if n == 0:
        return ["空批次"], ""

    # ---------- 开头三音 ----------

    openings = [
        opening_notes(s) for s in scores
    ]

    most_common = max(
        set(openings),
        key=openings.count,
    )

    open_rate = (
        openings.count(most_common) / n
    )

    # ---------- 和弦进行 ----------

    progs = [
        progression_key(s) for s in scores
    ]

    top_prog = max(
        set(progs),
        key=progs.count,
    )

    prog_rate = progs.count(top_prog) / n

    # ---------- 调性 ----------

    keys = [
        s.get("key", "?") for s in scores
    ]

    top_key = max(
        set(keys),
        key=keys.count,
    )

    key_rate = keys.count(top_key) / n

    # ---------- 密度散布 ----------

    densities = [
        len(s.get("melody", [])) / max(1, s["bars"])
        for s in scores
    ]

    if open_rate > 0.5:

        problems.append(
            f"开头三音重复率 {open_rate*100:.0f}% "
            f"({most_common})，超过50%阈值"
        )

    if prog_rate > 0.7:

        problems.append(
            f"和弦进行单一率 {prog_rate*100:.0f}% "
            f"({top_prog})，超过70%阈值"
        )

    if key_rate > 0.8:

        problems.append(
            f"调性单一率 {key_rate*100:.0f}% "
            f"({top_key})，超过80%阈值"
        )

    stats = (
        f"开头三音: {open_rate*100:.0f}%重复 | "
        f"进行: {top_prog} 占{prog_rate*100:.0f}% | "
        f"调性: {top_key} 占{key_rate*100:.0f}% | "
        f"密度: {min(densities):.1f}~{max(densities):.1f}音/小节"
    )

    return problems, stats


# =========================
# 主流程
# =========================

def main():

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "profiles",
        nargs="+",
        help="画像JSON文件（一个或多个）",
    )

    parser.add_argument(
        "--n",
        type=int,
        default=2,
        help="每个画像生成几首（默认2）",
    )

    parser.add_argument(
        "--out",
        default="reports/batch_V3",
        help="输出目录",
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="离线模式：用规则作曲器代替LLM",
    )

    args = parser.parse_args()

    out_dir = Path(args.out)

    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 收集画像 ----------

    profile_paths = []

    for p in args.profiles:

        path = Path(p)

        if path.is_dir():

            profile_paths.extend(
                sorted(path.glob("*.json"))
            )

        else:

            profile_paths.append(path)

    scores = []

    rows = []

    variation = 0

    for pp in profile_paths:

        with open(pp, encoding="utf-8") as f:

            profile = json.load(f)

        for i in range(args.n):

            t0 = time.perf_counter()

            template = TEMPLATES[
                variation % len(TEMPLATES)
            ]

            if args.mock:

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

                score = compose(
                    profile,
                    seed=variation,
                )

                meta = {
                    "latency_s": 0.05,
                    "attempts": 1,
                    "model": "mock-rule",
                }

            else:

                try:

                    score, meta = call_llm(
                        profile,
                        variation=variation,
                    )

                except RuntimeError as e:

                    rows.append(
                        {
                            "profile": pp.stem,
                            "index": i,
                            "error": str(e),
                        }
                    )

                    variation += 1

                    continue

            score, fixes, fatals = validate_and_fix(
                score
            )

            if fatals:

                rows.append(
                    {
                        "profile": pp.stem,
                        "index": i,
                        "error": f"fatal:{fatals}",
                    }
                )

                variation += 1

                continue

            name = (
                f"pV3_{pp.stem}_{i+1}.json"
            )

            path = out_dir / name

            with open(
                path,
                "w",
                encoding="utf-8",
            ) as f:

                json.dump(
                    score,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            scores.append(score)

            rows.append(
                {
                    "file": name,
                    "profile": pp.stem,
                    "variation": variation,
                    "template": template,
                    "key": score.get("key"),
                    "latency_s": meta["latency_s"],
                    "fixes": len(fixes),
                }
            )

            variation += 1

    # ---------- 汇总 ----------

    with open(
        out_dir / "summary.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            rows,
            f,
            ensure_ascii=False,
            indent=2,
        )

    for r in rows:

        if "error" in r:

            print(
                f"[失败] {r['profile']} #{r['index']}"
                f" {r['error']}"
            )

        else:

            print(
                f"[OK] {r['file']:36s} "
                f"{r['template']:14s} {r['key']:3s} "
                f"{r['latency_s']:5.1f}s "
                f"修复{r['fixes']}"
            )

    # ---------- lint ----------

    problems, stats = lint_scores(scores)

    print()

    print(f"[lint] {stats}")

    if problems:

        print("[lint] 未通过:")

        for p in problems:

            print(f"  - {p}")

        sys.exit(1)

    print("[lint] 通过")

    print(f"[输出] {out_dir}")


if __name__ == "__main__":

    main()
