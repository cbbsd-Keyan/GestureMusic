# GestureMusic 架构与进度总览（团队对齐文档）

> 更新：2026-09-02。新人或掉队者读这一篇即可追上。

## 一句话

挥动开发板（ESP32-S3 + MPU6500）10~30 秒，系统把动作翻译成一段
带配器的音乐——不做乐器，做"动作到音乐的翻译器"。

## 架构（数据流）

```
ESP32-S3 + MPU6500（尺子上的"指挥棒"）
   │ 100Hz 原始6轴数据 + ALIVE心跳（UDP 单播，注册握手）
   ▼
录制 record.py（场景: vigorous/gentle/free/calibration）→ CSV + meta
   ▼
画像 profile.py（features/）
   ├─ tempo.py    BPM双路估计（自相关+峰值间隔，贴底自动判无效）
   ├─ posture.py  roll/pitch（准静态过滤）
   ├─ structure.py 乐段突变点
   └─ 校准 normalized（个人全力挥=1.0，B实现中）
   ▼ 画像 JSON（schema v1 已冻结，见 src/llm/schema.py）
作曲（两条路，9/6 定主次）
   ├─ LLM：client.py(V3 prompt+变奏轮换) → validator 校验修复
   └─ 规则兜底：composer_rule.py（离线、秒出、永可用）
   ▼ 乐谱 JSON（SCORE_SCHEMA 同构，两条路输出同格式）
渲染 arrangement.py（energy 驱动：提速/八度/力度/鼓贝斯三档）
   → arranged_play.py → MidiEngine → GM音源 → 扬声器
```

## 分层职责（9/2 盲测定稿）

- **生成端（LLM/规则）：只负责"每首不一样"**（旋律/和声/轮廓）
- **渲染端（arrangement）：只负责"激不激动"**（速度/音区/力度/织体）
- 两者解耦：同一份乐谱可用不同 energy 播出不同情绪

## 已完成（有数据背书的才算）

| 里程碑 | 证据 |
|---|---|
| 数据链路 | 4 人 36 段全部 100Hz；单播注册握手后丢包≈0 |
| BPM 精度 | 节拍器验证 90→90.0 / 120→120.1（误差<0.2%） |
| 跨人归一化 | 四人留一交叉盲分：**个人归一化 96% vs 绝对阈值 71%** |
| 渲染层能量映射 | 同旋律不同 energy 盲测可明确分辨（v2 三杠杆） |
| LLM 链路 | 10/10 生成成功（V2 首批），validator 自动修复 |
| 同质化诊断与修复 | V2 全 do-mi-sol-mi 开头 → V3 变奏轮换+lint 门禁（待 9/3 验证） |
| 工程体系 | 任务单/规格/指南三件套，分支开发，多样性 lint 双门禁 |

## 数据资产

- `data/batch_2026_09_w1/s00~s03`：4 人 × vigorous/gentle/free，36 段
- `data/legacy_single_subject/`：110 段历史数据（单人，仅参考）
- 格式与纪律见 `data/README.md`；校准规格见 `docs/calibration-spec.md`

## 未决（9/6 决策会的两个轴）

1. LLM 旋律质量（V3 首批 → 20 首盲听合格率，≥60% 为主力）
2. 生成延迟（实测 30~68s；对策：Plan B 参数模式 or 演示垫场）

## 文档索引

任务与日程 `docs/api-line-tasks.md` ｜ 上手 `docs/quickstart.md`
校准规格 `docs/calibration-spec.md` ｜ A收敛指南 `docs/for-A-convergence.md`
