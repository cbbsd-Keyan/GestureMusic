# A 收敛指南（基于 8.31 进度报告的核对结论）

> 结论先行：你的链路验证是真进度（比日程早两天），方向已完全正确。
> 唯一问题：**工作发生在仓库外的平行实现上**。本指南用一天时间把它收敛回正轨，
> 你的成果全部保留，只是搬进统一的管道。

---

## 一、核对结论（哪些保留、哪些停止）

| 你的成果 | 处置 |
|---|---|
| 千问 API 调用跑通、key 配置 | ✅ 保留——用环境变量接入仓库管道（见下） |
| "模型→JSON→MIDI→出声"验证 | ✅ 保留——这是里程碑，已达成 |
| 你自己的 Python 环境/播放器/JSON 格式 | ❌ 停止使用——仓库已有全套（client/validator/demo/player 规格） |
| 你的 `generated_score.json` 旧样品 | 📦 不转换、不迁移——用新 prompt 重新生成（成本几分钱），旧样品仅自己留参考 |
| "重新设计 JSON schema"提议 | ❌ 撤回——仓库 SCORE_SCHEMA 已含小节网格(bar/start)与和弦挂靠，比你提案的信息更全，且已冻结。要改走任务单流程 |
| 四条质量建议 | ✅ 全部吸收：1/2 已写进 SYSTEM_PROMPT V2（乐理约束+和弦进行）；4 变成新试听表格；混合方案登记为 Plan B |

## 二、收敛步骤（Day 1，约 2~3 小时）

### 第 1 步 · 克隆仓库（仓库是公开的，无需权限）

```powershell
git clone https://github.com/cbbsd-Keyan/GestureMusic.git
cd GestureMusic
python -m venv .venv            # 你机器是 3.12 也没问题，直接建
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 第 2 步 · 离线自检（不需要 key）

```powershell
.venv\Scripts\python.exe src\features\profile.py data\batch_2026_09_w1\s00\gentle_001.csv --json > reports\p.json
.venv\Scripts\python.exe src\llm\demo.py reports\p.json --mock
# 预期: [来源] mock ... [已保存] reports\llm_score.json
```

### 第 3 步 · 接入千问（你的 key 直接复用）

```powershell
$env:LLM_API_KEY="你的key"
$env:LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
$env:LLM_MODEL="qwen-plus"        # 建议作曲用 plus，flash/turbo 乐理偏弱
.venv\Scripts\python.exe src\llm\demo.py reports\p.json
```

说明：client 已做跨厂商兼容——若厂商不支持 `response_format`，
自动去掉重试，无需你处理。**SYSTEM_PROMPT 已升级 V2**（调性白名单/
和弦模板/强拍和弦音/禁大跳/收束/乐句结构），直接用，不要改回你的旧 prompt。

### 第 4 步 · 迁移播放器 → `src/music/score_player.py`

你的播放器逻辑可以移植，但输入格式必须换成仓库乐谱：

```json
{"bpm": 96, "bars": 8,
 "chords": [{"bar": 0, "symbol": "C"}],
 "melody": [{"bar": 0, "note": 60, "start": 0, "dur": 2, "velocity": 70}]}
```

关键差异：**`start` 是小节内十六分音符格位（0~15），不是顺序累加**——
同一格位可以有多音（和弦）。换算：绝对拍 = bar×4 + start/4；
一十六分音符秒长 = 60/bpm/4。用 `MidiEngine`（`src/music/midi_engine.py`）的
`play_melody/note_off`；**device_id 必须做成参数**——先跑
`experiments\midi\list_midi.py` 查你机器的输出设备号。
调试用现成样例：`reports\llm_score.json`。
完成后接入 `demo.py` 末尾自动播放。

### 第 5 步 · 第一批（V2 质量）

- 5 个画像（`data/batch_2026_09_w1/` 下 s00~s02 各选，用第 2 步命令生成 p.json）
- 每画像生成 2 首，共 10 首
- 文件命名 `pV2_{画像名}_{序号}.json` 放 `reports/`，**提交到仓库**
- 群发参数卡：每首附 `prompt版本V2 / 温度0.8 / 延迟 / [修复]N处`

## 三、你的日程（按实际进度重定义）

| 天 | 任务 |
|---|---|
| D1 | 上述收敛 5 步 |
| D2 | 第一批 10 首发群 + 按"V2 听感问题清单"归类；温度实验 0.5/0.9 各 3 首 |
| D3 | prompt 微调（改约束措辞，一次一个变量，版本号 V2.1/V2.2...）；若 V2 系仍不合格 → 提供 Plan B 数据：让模型只出参数(BPM/调性/模板/密度)，`composer_rule.py` 出音符，同画像对比两版 |
| D4 | 20 首正式 + 厂商对比笔记（批量工具主程提供） |

## 四、红线（重申）

1. 一切代码进仓库，不再本地私改管道
2. schema 变更走任务单 + 乐理审校，不自行重设计
3. 卡壳 2 小时上报群，带报错原文
4. 新试听表格（六问）：旋律感 / 跑调 / 节奏自然度 / 重复度 / 情绪匹配 / 可否演示
