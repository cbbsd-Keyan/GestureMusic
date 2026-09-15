# GestureMusic 快速上手

本页只说明当前正式演示流程。API 作曲、姿态音区、摄像头音区与实时变速属于历史或独立实验，不需要为现场演示启动。

## 1. 建立环境（每台电脑一次）

需要 Windows 与 Python 3.12 或更新版本。项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-tempo.txt
```

以后始终用 `.\.venv\Scripts\python.exe` 运行程序，用 `.\.venv\Scripts\python.exe -m pip` 安装依赖。VS Code 选择 `.venv\Scripts\python.exe` 作为解释器。

## 2. 连接硬件

- 指挥棒：ESP32-S3 + MPU，接入与电脑相同的专用 Wi-Fi/热点，向 UDP 4210 发送动作数据。
- 编码器：USB 接电脑；Arduino 串口监视器必须关闭。
- 扬声器/耳机：设为 Windows 默认音频输出，或在启动参数中指定音频设备。

编码器端口可在设备管理器或 Arduino IDE 中查看。当前常用端口为 `COM9`。

## 3. 启动正式菜单

```powershell
.\.venv\Scripts\python.exe -X utf8 src\desktop_app.py --encoder-port COM9
```

旋转选择，短按确认，长按返回。一次只能有一个程序使用编码器串口，也只能有一个程序监听 UDP 4210。

## 4. 动作作曲

选择“动作作曲”后有三项：

- **整体听感**：用整段挥动的总体强度决定配器与力度。
- **起伏映射**：把一段挥动中的强弱变化映射到各小节的配器与力度。
- **个人校准**：依次录制最大自然挥动、舒缓挥动、自然发挥各 5 秒；确认后更新该用户的强度基准。

前两项均为 3 秒倒计时后录制；短按可结束，15 秒自动结束。作品会自动保存到 `reports/live_demo/<时间戳>/`；可在菜单中试听、保存或重录。

## 5. 音乐指挥

- **月光曲**：挥动开始播放，停手暂停；动作强度控制音量，播放速度固定。
- **卡农摇滚（分轨）**：按原 MIDI 节奏播放，动作强度从键盘逐步加入贝斯、电吉他与鼓组；播放速度固定。

短按可暂停或重新进入等待挥动，长按返回主菜单。

## 6. 常见问题

- `pip` 不是命令：使用 `.\.venv\Scripts\python.exe -m pip ...`。
- `无法打开编码器 COMx`：关闭 Arduino 串口监视器和其他读取串口的软件，确认端口号。
- 等待挥动但无反应：确认指挥棒已连上相同热点；关闭其他监听 UDP 4210 的程序；Windows 防火墙允许本项目 Python 通信。
- 月光曲报 DLL 缺失：把 `src/audio/native/stream_stretch.dll` 放回对应路径。
- `pygame` 缺失：重新执行本页第 1 步的安装命令。
