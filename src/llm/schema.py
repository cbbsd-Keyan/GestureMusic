# ============================================================
# 画像 Schema v1（已冻结，2026-08-31）
#
# 手势线输出 / API线输入 的唯一契约。
# 改动此文件必须两条线同时知情。
# ============================================================

PROFILE_SCHEMA = {
    "version": "1.0",
    "duration_s": "float, 录制时长",

    "tempo": {
        "bpm": "float | null, 低置信度时为 null",
        "confidence": "high | medium | low",
        "method": "autocorr | peaks | none",
    },

    "energy": {
        "gyro_rms": "float rad/s, 平均运动强度（核心）",
        "accel_std": "float m/s², 加速度波动",
        "gyro_peak": "float rad/s, 峰值（可能饱和削顶）",
        "normalized": "float 0~1 | null, 多人基线归一化值，阶段6前恒 null",
    },

    "activity": {
        "active_ratio": "float 0~1, 运动时间占比",
    },

    "posture": {
        "available": "bool, 剧烈段不可信时为 false",
        "roll_median": "float deg | null",
        "roll_range": "float deg, p90-p10 | null",
        "pitch_median": "float deg | null",
    },

    "structure": {
        "change_points": "list[float] 秒位置, 最多3个 | null",
    },

    "subject_id": "string, 如 s00",
    "mount_version": "string, 如 ruler_v1",
}


# ============================================================
# 乐谱 Schema（草案，等乐理审校）
#
# TODO(乐理): 以下约束需要人工确认后从 DRAFT 改为 FROZEN：
#   - 音域 36~84 是否合适（MusicEngine 当前实际使用范围）
#   - 每小节时值总和 = 16（十六分音符网格）
#   - 和弦表示法：音名 "Am" 还是音级数组 [57,60,64]
# ============================================================

SCORE_SCHEMA_DRAFT = {
    "bpm": "int, 作曲端有权覆盖画像 bpm",
    "key": "string, 调性",
    "bars": "int, 小节数",
    "chords": [
        {
            "bar": "int, 从0开始",
            "symbol": "string, 如 Am",
        }
    ],
    "melody": [
        {
            "bar": "int",
            "note": "int MIDI 36~84",
            "start": "int, 小节内十六分音符位置 0~15",
            "dur": "int, 十六分音符数",
            "velocity": "int 1~127",
        }
    ],
    "title": "string, 曲名",
    "description": "string, ~50字乐曲解读",
}
