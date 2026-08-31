# GestureMusic 快速上手（三人分工版）

> 仓库：https://github.com/cbbsd-Keyan/GestureMusic
> 完整任务与日程见 `docs/api-line-tasks.md`，本页只讲怎么动手。

## 通用环境（每台电脑一次）

```powershell
git clone https://github.com/cbbsd-Keyan/GestureMusic.git
cd GestureMusic
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- 一律用 `.venv\Scripts\python.exe` 跑脚本，不要裸 `python`/`pip`
- VSCode：`Ctrl+Shift+P` → Python: Select Interpreter → 选 `.venv\Scripts\python.exe`

---

## A（远程 · API 线）

**D1 自检顺序（不需要 key 先跑通前两步）：**

```powershell
# 1. 离线全链路（应打印 [来源] mock ... [已保存]）
.venv\Scripts\python.exe src\llm\demo.py --help
.venv\Scripts\python.exe src\features\profile.py data\batch_2026_09_w1\s00\gentle_001.csv --json > reports\p.json
.venv\Scripts\python.exe src\llm\demo.py reports\p.json --mock

# 2. 查本机 MIDI 输出设备号（播放器要用，每台机器不同！）
.venv\Scripts\python.exe experiments\midi\list_midi.py

# 3. 真调用
$env:LLM_API_KEY="你的key"
.venv\Scripts\python.exe src\llm\demo.py reports\p.json
```

- 断网/坏 JSON 时 `demo.py` 自动回退规则作曲，**永远有声音**
- 生成文件命名 `p{prompt版本}_{画像名}.json`，发群附参数卡
- 卡壳超 2 小时：报错原文截图发群

## B（同地 · 硬件与现场）

**烧录**：`Desktop\MPU\GestureMusic.ino`（Arduino IDE，板型 ESP32-S3）。
注意此文件**不在仓库里**（含热点密码），找主程要最新版。

**录 s03（15 分钟）：**

```powershell
.venv\Scripts\python.exe src\record.py s03
# 口令同 s01/s02：尽力挥×3(键1)、轻柔×3(键2)、自由×2(键3)，每段10秒
```

**联调验证：**

```powershell
.venv\Scripts\python.exe experiments\gesture\udp_test.py   # 先见 ALIVE 和数据流
.venv\Scripts\python.exe src\record.py s03                  # hz 应为 90~110
.venv\Scripts\python.exe src\features\profile.py data\batch_2026_09_w1\s03
```

## 你（乐理 + 主程 · 判断环节）

**试听反馈**：A 每批生成后，逐首回表格——

```
曲目 | 合格否 | 问题类别(和声/节奏/音域/结构/文案) | 一句话备注
```

**审校位置**：
- 乐谱 schema：`src/llm/schema.py` 的 `SCORE_SCHEMA_DRAFT`（TODO 注释处）
- 和弦模板：`src/music/composer_rule.py` 的 `PROGRESSIONS`（三套，现为占位）

**看数据全景**：

```powershell
.venv\Scripts\python.exe src\features\batch_report.py   # 多人概览+归一化
.venv\Scripts\python.exe src\features\blindtest.py      # 盲分正确率
start reports\radar_s00.png                             # 雷达图
```

---

## 目录速查

```
src/
  record.py        录制入口 (python src\record.py sXX)
  features/        画像: profile / tempo / posture / radar / blindtest...
  llm/             client(调用) validator(校验) demo(全链路) schema(契约)
  music/           midi_engine / music_engine(实时) composer_rule(兜底作曲)
data/              legacy_* 历史 / batch_* 新批次（CSV+meta）
docs/              任务单 + 本页
reports/           雷达图 / 示例乐谱 / 中间产物
firmware/          (空，固件在主程电脑 Desktop\MPU)
archive/           MPUGesture 冻结归档，只读
experiments/       历史实验，只读
```
