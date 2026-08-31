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

SCENES = ["vigorous", "gentle", "free"]


def collect_all():

    """
    扫描所有批次目录下的受试者文件夹，
    返回 {subject: {scene: [result, ...]}}
    """

    subjects = {}

    for batch in sorted(DATA_ROOT.glob("batch_*")):

        for subj in sorted(batch.glob("s*/")):

            data = subjects.setdefault(
                subj.name,
                {},
            )

            for path in sorted(
                subj.glob("*.csv")
            ):

                r = analyze(path)

                if "error" in r:
                    continue

                scene = (
                    path.stem.split("_")[0]
                )

                data.setdefault(
                    scene,
                    [],
                ).append(r)

    return subjects


def percentile(sorted_vals, q):

    idx = int(q * (len(sorted_vals) - 1))

    return sorted_vals[idx]


def main():

    subjects = collect_all()

    if not subjects:
        print("没有找到任何数据。")
        return

    all_rms = []
    all_bpm = []

    print("=" * 60)
    print("各受试者概览")
    print("=" * 60)

    for subj, scenes in subjects.items():

        print(f"\n[{subj}]")

        for scene in SCENES:

            items = scenes.get(scene, [])

            if not items:
                continue

            rms_vals = [
                r["gyro_rms"] for r in items
            ]

            bpms = [
                r["tempo_bpm"]
                for r in items
                if r["tempo_bpm"]
            ]

            conf = [
                r["tempo_confidence"]
                for r in items
            ]

            bpm_med = (
                statistics.median(bpms)
                if bpms
                else None
            )

            print(
                f"  {scene:8s} n={len(items)} "
                f"gyro_rms_med={statistics.median(rms_vals):6.3f} "
                f"bpm_med={bpm_med and round(bpm_med,1)} "
                f"conf={'/'.join(conf)}"
            )

            all_rms.extend(rms_vals)
            all_bpm.extend(bpms)

    # 归一化锚点只统计真正的运动段，
    # 静止持握段(active_ratio<0.5)会把下锚拉到0附近
    all_rms = [
        v for v in all_rms if v > 0.5
    ]

    if len(all_rms) < 6:
        print("\n运动段样本不足6段，归一化对比待更多数据。")
        return

    # =========================
    # 全局分位归一化
    # =========================

    all_rms.sort()

    p10 = percentile(all_rms, 0.10)
    p90 = percentile(all_rms, 0.90)

    def global_norm(v):

        if p90 <= p10:
            return None

        x = (v - p10) / (p90 - p10)

        return round(max(0.0, min(1.0, x)), 3)

    # =========================
    # 个人基线归一化
    # =========================

    print()
    print("=" * 60)
    print("归一化对比 (energy.normalized)")
    print("=" * 60)
    print(f"全局分位: p10={p10:.3f} p90={p90:.3f}")

    for subj, scenes in subjects.items():

        subj_rms = [
            r["gyro_rms"]
            for scene in SCENES
            for r in scenes.get(scene, [])
        ]

        if not subj_rms:
            continue

        subj_max = max(subj_rms)

        print(f"\n[{subj}] 个人基准 max={subj_max:.3f}")

        for scene in SCENES:

            items = scenes.get(scene, [])

            for r in items:

                g = global_norm(r["gyro_rms"])

                p = (
                    round(
                        r["gyro_rms"] / subj_max,
                        3,
                    )
                    if subj_max > 0
                    else None
                )

                name = Path(r["file"]).name

                print(
                    f"  {name:20s} "
                    f"raw={r['gyro_rms']:6.3f} "
                    f"全局={g}  个人={p}"
                )

    print()
    print(
        "判读标准: 同一人各场景相对位置在两种方法下\n"
        "是否一致；多人后看跨人波动是否被压缩。"
    )


if __name__ == "__main__":

    main()
