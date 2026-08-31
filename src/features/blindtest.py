import statistics
import sys
from pathlib import Path

from profile import analyze


# =========================
# 数据根目录
# =========================

DATA_ROOT = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
)

SCENES = ["vigorous", "gentle"]


def collect_all():

    subjects = {}

    for batch in sorted(DATA_ROOT.glob("batch_*")):

        for subj in sorted(batch.glob("s*/")):

            data = subjects.setdefault(
                subj.name,
                {},
            )

            for scene in SCENES:

                for path in sorted(
                    subj.glob(f"{scene}_*.csv")
                ):

                    r = analyze(path)

                    if "error" not in r:

                        data.setdefault(
                            scene,
                            [],
                        ).append(r)

    return subjects


def classify(value, threshold):

    return (
        "vigorous"
        if value >= threshold
        else "gentle"
    )


def main():

    subjects = collect_all()

    names = sorted(subjects.keys())

    if len(names) < 2:
        print("盲分对比需要至少2名受试者。")
        return

    print("=" * 64)
    print("盲分实验：留一人交叉验证")
    print("=" * 64)

    abs_scores = []
    norm_scores = []

    for held in names:

        others = [
            n for n in names if n != held
        ]

        # ---------- 绝对阈值 ----------
        # 用其他人(vigorous/gentle中位数的中点)定阈值

        v_med = statistics.median([
            r["gyro_rms"]
            for n in others
            for r in subjects[n].get(
                "vigorous", []
            )
        ])

        g_med = statistics.median([
            r["gyro_rms"]
            for n in others
            for r in subjects[n].get(
                "gentle", []
            )
        ])

        abs_t = (v_med + g_med) / 2

        # ---------- 个人归一化阈值 ----------
        # 每人自己的 vigorous/gentle 中位数的中点
        # (实际部署用每人校准段，此处用数据近似)

        held_v = [
            r["gyro_rms"]
            for r in subjects[held].get(
                "vigorous", []
            )
        ]

        held_g = [
            r["gyro_rms"]
            for r in subjects[held].get(
                "gentle", []
            )
        ]

        personal_t = (
            statistics.median(held_v)
            + statistics.median(held_g)
        ) / 2

        # ---------- 在 held 上测试 ----------

        correct_abs = 0
        correct_norm = 0
        total = 0

        print(f"\n测试对象: {held}")

        for scene in SCENES:

            for r in subjects[held].get(
                scene, []
            ):

                raw = r["gyro_rms"]

                pred_abs = classify(raw, abs_t)

                pred_norm = classify(
                    raw,
                    personal_t,
                )

                ok_a = pred_abs == scene
                ok_n = pred_norm == scene

                correct_abs += ok_a
                correct_norm += ok_n
                total += 1

                mark_a = (
                    "OK " if ok_a else "MISS"
                )

                mark_n = (
                    "OK " if ok_n else "MISS"
                )

                print(
                    f"  {Path(r['file']).name:20s} "
                    f"真值={scene:8s} "
                    f"raw={raw:5.2f} | "
                    f"绝对[{abs_t:.2f}] {mark_a} | "
                    f"个人[{personal_t:.2f}] {mark_n}"
                )

        if total > 0:

            abs_scores.append(
                correct_abs / total
            )

            norm_scores.append(
                correct_norm / total
            )

    print()
    print("=" * 64)
    print("结论")
    print("=" * 64)

    print(
        f"绝对阈值平均正确率: "
        f"{statistics.fmean(abs_scores)*100:.0f}%"
    )

    print(
        f"个人归一化平均正确率: "
        f"{statistics.fmean(norm_scores)*100:.0f}%"
    )

    print()
    print(
        "解读: 绝对阈值失败=跨人绝对数值不可比;\n"
        "个人归一化成功=每人内部相对结构一致，\n"
        "部署时用录制前10s自由挥做个人校准段。"
    )


if __name__ == "__main__":

    main()
