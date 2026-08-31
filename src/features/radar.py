import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "sans-serif",
]

import matplotlib.pyplot as plt
import numpy as np

from profile import analyze


# =========================
# 配置
# =========================

DATA_ROOT = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
)

REPORT_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "reports"
)

AXES = [
    "能量",
    "节奏速度",
    "节奏稳定",
    "活跃度",
    "幅度",
]

SCENES = ["vigorous", "gentle", "free"]

CONF_SCORE = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.2,
}

COLORS = {
    "vigorous": "#d62728",
    "gentle": "#1f77b4",
    "free": "#2ca02c",
}


def axis_values(r, personal_max):

    energy = (
        r["gyro_rms"] / personal_max
        if personal_max
        else 0.0
    )

    bpm = r["tempo_bpm"]

    tempo = (
        (bpm - 60.0) / 120.0
        if bpm
        else 0.0
    )

    tempo = max(0.0, min(1.0, tempo))

    conf = CONF_SCORE.get(
        r["tempo_confidence"],
        0.2,
    )

    spread = min(
        r["roll_range"] / 180.0,
        1.0,
    ) if r["roll_range"] else 0.0

    return [
        energy,
        tempo,
        conf,
        r["active_ratio"],
        spread,
    ]


def collect():

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

                scene = path.stem.split("_")[0]

                data.setdefault(
                    scene,
                    [],
                ).append(r)

    return subjects


def draw_subject(subj, scenes, path):

    personal_max = max(
        r["gyro_rms"]
        for items in scenes.values()
        for r in items
    )

    angles = np.linspace(
        0,
        2 * np.pi,
        len(AXES),
        endpoint=False,
    ).tolist()

    angles += angles[:1]

    fig, ax = plt.subplots(
        figsize=(6, 6),
        subplot_kw={
            "polar": True
        },
    )

    for scene in SCENES:

        items = scenes.get(scene, [])

        if not items:
            continue

        vectors = [
            axis_values(r, personal_max)
            for r in items
        ]

        med = [
            statistics.median(
                col
            )
            for col in zip(*vectors)
        ]

        values = med + med[:1]

        ax.plot(
            angles,
            values,
            color=COLORS[scene],
            linewidth=2,
            label=f"{scene} (n={len(items)})",
        )

        ax.fill(
            angles,
            values,
            color=COLORS[scene],
            alpha=0.15,
        )

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(AXES)
    ax.set_ylim(0, 1)
    ax.set_title(subj)

    ax.legend(
        loc="upper right",
        bbox_to_anchor=(1.3, 1.1),
    )

    fig.savefig(
        path,
        dpi=150,
        bbox_inches="tight",
    )

    plt.close(fig)


def main():

    REPORT_DIR.mkdir(exist_ok=True)

    subjects = collect()

    if not subjects:
        print("没有数据。")
        return

    for subj, scenes in subjects.items():

        out = REPORT_DIR / f"radar_{subj}.png"

        draw_subject(subj, scenes, out)

        print(f"已生成: {out}")


if __name__ == "__main__":

    main()
