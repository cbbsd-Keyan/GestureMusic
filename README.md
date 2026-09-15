# GestureMusic

GestureMusic 是一个面向硬件设计竞赛的动作音乐交互作品。用户挥动 ESP32-S3 + MPU 指挥棒，通过旋转编码器选择两种体验：

- **动作作曲**：录制一段挥动，用既有规则作曲与配器生成音乐；可选择整体听感、起伏映射或个人校准。
- **音乐指挥**：挥动控制月光曲的启停和强弱，或控制卡农摇滚版逐步加入键盘、贝斯、电吉他和鼓组。

正式桌面入口是 `src/desktop_app.py`。当前成品不使用 AI 在线作曲，也不使用实时变速。

## 快速启动

Windows PowerShell，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-tempo.txt
.\.venv\Scripts\python.exe -X utf8 src\desktop_app.py --encoder-port COM9
```

将 `COM9` 改为编码器实际端口。旋转选择，短按确认，长按返回；先关闭 Arduino 串口监视器及其他占用串口或 UDP 4210 的程序。

若没有 `.venv`，请先安装 Python 3.12 或更新版本，再执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-tempo.txt
```

不要裸用 `pip`；统一使用 `.\.venv\Scripts\python.exe -m pip`。

## 目录

- `firmware/`：指挥棒与桌面编码器的 ESP32-S3 固件。
- `src/`：正式桌面菜单、动作采集、规则作曲、音频与 MIDI 控制。
- `assets/conductor/`：卡农摇滚分轨 MIDI。
- `moonlight.wav`：月光曲指挥模式音源。
- `docs/`：现场启动、硬件编码器与演示检查说明。
- `experiments/`、`archive/`：保留的历史实验，不作为正式演示入口。

## 文档入口

- [快速上手](docs/quickstart.md)
- [桌面编码器与菜单](docs/encoder-control.md)
- [当前架构与功能范围](docs/architecture-status.md)
- [演示前检查表](docs/demo-checklist.md)
- [个人校准说明](docs/calibration-spec.md)

## 交付提醒

月光曲播放需要 `src/audio/native/stream_stretch.dll`。该文件是本机构建产物，未纳入 Git；将项目移到另一台电脑前，需一并带上它，或按历史变速实验文档重新构建。正式演示不启用变速。
