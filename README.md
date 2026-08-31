# GestureMusic

基于 ESP32-S3 + MPU6050 的动作音乐交互系统。

## Current Goal

将用户自然动作实时转换为具有音乐结构的结果：

- 下挥 -> Beat
- 连续挥动 -> Tempo
- 动作强度 -> Energy
- 左右姿态 -> Melody contour
- 特殊手势 -> Variation / Section control

## Structure

- `firmware/` ESP32 固件
- `src/` 正式程序
  - `main.py` 实时演奏模式
  - `record.py` 连续录制工具（R 开始 / S 保存 / Q 退出）
  - `features/` 动作统计画像（开发中）
  - `llm/` 大模型作曲接口（规划中）
- `experiments/` 实验和历史版本（冻结只读）
- `models/` 手势识别模型（随旧方案封存）
- `logs/` 测试数据
- `data/` 数据集与采集规范（见 data/README.md）
- `archive/` 已归档的祖先项目（只读）

## Environment

Python 3.13

```bash
pip install -r requirements.txt