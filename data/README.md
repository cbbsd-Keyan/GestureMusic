# 数据目录规范

## 目录结构

- `legacy_single_subject/` —— MPUGesture 迁移的历史数据（110 个 CSV）。
  已知全部来自一名受试者（zky），原样拷贝未改动。
  仅用于基线分布参考和固件阈值调试，不再用于训练。
- `batch_YYYY_MM_WN/` —— 新采集批次，按周命名。批内按受试者分目录：`s01/`、`s02/`…

## CSV 格式（新旧一致，禁止改动）

```
time_ms,ax,ay,az,gx,gy,gz
25311.0,0.996,-0.9553,9.4332,0.3475,0.0873,0.1394
```

- 采样率约 100 Hz，`time_ms` 来自 ESP32 时钟
- 加速度单位 m/s²，陀螺仪单位 rad/s
- **时间戳可能因 WiFi 抖动不均匀**：任何分析前必须重采样到
  均匀 100 Hz 网格（features 层负责，录制层不做处理）

## 元数据

新录制每个 CSV 旁边有同名 `.meta.json`：

```json
{
  "subject_id": "s01",
  "scene": "vigorous",
  "mount_version": "ruler_v1",
  "started_at": "...",
  "samples": 1024,
  "duration_s": 10.24,
  "hz_estimate": 100.0,
  "notes": ""
}
```

## 采集纪律

1. `subject_id` 从第一条数据就要写对，不可复用
2. 场景统一用：`vigorous`（剧烈）/ `gentle`（轻柔）/ `free`（自由发挥）
3. 佩戴：统一手腕、同一朝向，握持线位置一致
4. 每段录满 5 秒以上（<300 点会被工具警告）
5. 更换固定方式时更新 `mount_version`（如 `baton_v1`）
