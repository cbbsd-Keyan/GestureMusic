# 个人校准规格（B 实现）

> 依据：四人回测证实单锚点方案成立（gentle 0.29~0.77 / vigorous 0.87~1.0），
> 两点方案的"free段做自然锚"已被数据证伪（s01~s03 自由发挥比刻意轻柔更激烈）。
> 本文档是实现契约：按此做，无需再做设计决策。

## 1. 原理

```
energy.normalized = clamp( 本段gyro_rms / 校准锚值 , 0, 1 )
校准锚值 = 本人"全力挥5秒"的 1秒滑窗RMS 的95分位
```

锚值存于受试者目录：`data/batch_2026_09_w1/sXX/baseline.json`

## 2. 实现清单（三处改动）

### 2.1 `src/record.py`（一行）

```python
SCENES = {
    "1": "vigorous",
    "2": "gentle",
    "3": "free",
    "4": "calibration",   # 新增
}
```

口令：**"用尽全力挥 5 秒，越大越快越好"**（R 开始 / S 保存，和平时一样）。

### 2.2 新建 `src/features/calibrate.py`

```
从 CSV 计算：
  1. 复用 profile.load_rows + profile.resample 得到均匀序列
  2. 陀螺合量 |g|（复用 posture/structure 里的 gyro_mag 公式）
  3. 1 秒滑窗（无重叠即可）逐窗算 RMS
  4. anchor = 窗RMS序列的95分位
  5. 写入同目录 baseline.json：
     {"subject_id": "sXX", "anchor_rms": 12.34, "created_at": "..."}
CLI: python calibrate.py <calibration_XXX.csv>
     （或并入 profile.py 的 --calibrate 参数，二选一，实现方便优先）
```

### 2.3 `src/features/profile.py`（--json 模式）

`build_profile_json` 时检查源 CSV 同目录是否存在 `baseline.json`：
- 存在 → `energy.normalized = round(clamp(gyro_rms / anchor_rms, 0, 1), 3)`
- 不存在 → 维持 null（现状）

## 3. 验收标准（现场实测，B 自测后交主程复核）

1. 校准段 + gentle 段 + vigorous 段各录一次：
   gentle.normalized < 0.7，vigorous.normalized ≥ 0.85
2. 连续两次校准，锚值波动 < 15%
3. 删除 baseline.json 后 --json 的 normalized 回到 null（可撤销性）

## 4. 已知边界（写进答辩预案，不需要修）

- **疲劳漂移**：校准后力气衰减 → normalized 变低。这是"如实反映当前状态"的特性
- **s03 型用户**（自身对比度小）：gentle 可能贴近 0.7。渲染层三档边界 0.33/0.7 已考虑
- **绝对数值跨人不可比**是特性不是 bug——四人盲分 71% vs 96% 就是证据

## 5. 禁止事项

- 不得用 free 段或其他任意段充当校准锚（已证伪）
- 不得改 tier 边界值（0.33/0.7，渲染层 coupling）
