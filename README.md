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
- `experiments/` 实验和历史版本
- `models/` 手势识别模型
- `logs/` 测试数据

## Environment

Python 3.13

```bash
pip install -r requirements.txt