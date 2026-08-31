import csv
import json
import time
from pathlib import Path


class Recorder:

    """
    连续录制器：只负责采集和落盘，不做任何信号处理。
    信号处理（重采样、活动门限等）全部在 features 层完成。
    """

    def __init__(
        self,
        out_dir,
        subject_id,
        mount_version="ruler_v1",
    ):

        self.out_dir = (
            Path(out_dir) / subject_id
        )

        self.out_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.subject_id = subject_id
        self.mount_version = mount_version

        self.rows = []
        self.recording = False
        self.started_at = None

        self.COLUMNS = [
            "time_ms",
            "ax", "ay", "az",
            "gx", "gy", "gz",
        ]

    def start(self):

        self.rows = []
        self.started_at = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.recording = True

    def feed(self, values):

        """
        接收一行 7 个浮点数：
        time_ms, ax, ay, az, gx, gy, gz
        """

        if self.recording:
            self.rows.append(values)

    def stop(self):

        self.recording = False

        return len(self.rows)

    def save(self, scene="free", notes=""):

        if not self.rows:
            return None

        index = 1

        while True:

            path = (
                self.out_dir
                / f"{scene}_{index:03d}.csv"
            )

            if not path.exists():
                break

            index += 1

        with open(
            path,
            "w",
            newline="",
            encoding="utf-8",
        ) as f:

            writer = csv.writer(f)
            writer.writerow(self.COLUMNS)
            writer.writerows(self.rows)

        duration = (
            self.rows[-1][0]
            - self.rows[0][0]
        ) / 1000.0

        hz = (
            (len(self.rows) - 1)
            / duration
            if duration > 0
            else 0.0
        )

        meta = {
            "subject_id": self.subject_id,
            "scene": scene,
            "mount_version": self.mount_version,
            "started_at": self.started_at,
            "samples": len(self.rows),
            "duration_s": round(duration, 2),
            "hz_estimate": round(hz, 1),
            "notes": notes,
        }

        meta_path = path.with_suffix(
            ".meta.json"
        )

        with open(
            meta_path,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                meta,
                f,
                ensure_ascii=False,
                indent=2,
            )

        return {
            "csv": path,
            "meta": meta_path,
            "meta_content": meta,
        }
