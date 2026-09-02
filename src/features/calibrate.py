import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from profile import load_rows, resample, gyro_mag, TARGET_HZ


def calculate_anchor(csv_path):
    """
    从校准 CSV 计算个人能量锚值。

    流程：
    1. 读取并重采样
    2. 计算陀螺仪三轴合量
    3. 按 1 秒无重叠窗口分段
    4. 每个窗口计算 RMS
    5. 取窗口 RMS 的 95 分位数
    """

    rows = load_rows(csv_path)

    if len(rows) < 2:
        raise ValueError("CSV 数据不足")

    uniform = resample(rows)

    if len(uniform) < TARGET_HZ:
        raise ValueError("校准数据不足 1 秒")

    gyro_mags = [
        gyro_mag(row)
        for row in uniform
    ]

    window_size = int(round(TARGET_HZ))
    window_rms = []

    for start in range(
        0,
        len(gyro_mags) - window_size + 1,
        window_size,
    ):
        window = gyro_mags[
            start:start + window_size
        ]

        rms = math.sqrt(
            sum(g * g for g in window)
            / len(window)
        )

        window_rms.append(rms)

    if not window_rms:
        raise ValueError("没有可用的 1 秒窗口")

    anchor_rms = float(
        np.percentile(window_rms, 95)
    )

    return anchor_rms, window_rms


def save_baseline(csv_path, anchor_rms):
    csv_path = Path(csv_path)

    subject_id = csv_path.parent.name

    baseline = {
        "subject_id": subject_id,
        "anchor_rms": round(anchor_rms, 3),
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    output_path = (
        csv_path.parent / "baseline.json"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            baseline,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def main():
    if len(sys.argv) != 2:
        print(
            "用法: "
            "python calibrate.py "
            "<calibration_XXX.csv>"
        )
        sys.exit(1)

    csv_path = Path(sys.argv[1])

    if not csv_path.exists():
        print(f"文件不存在: {csv_path}")
        sys.exit(1)

    try:
        anchor_rms, window_rms = (
            calculate_anchor(csv_path)
        )

        output_path = save_baseline(
            csv_path,
            anchor_rms,
        )

        print(
            "window_rms:",
            [
                round(v, 3)
                for v in window_rms
            ],
        )
        print(
            f"anchor_rms: "
            f"{anchor_rms:.3f}"
        )
        print(
            f"baseline 已写入: "
            f"{output_path}"
        )

    except Exception as e:
        print(f"校准失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()