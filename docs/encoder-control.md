# 桌面编码器与正式菜单

编码器使用独立 ESP32-S3，经 USB 串口向电脑发送菜单事件。它只负责选择、确认与返回；音乐与动作数据仍由桌面程序和指挥棒处理。

## 接线与固件

编码器固件为 `firmware/EncoderControl/EncoderControl.ino`：

| 编码器引脚 | ESP32-S3 |
|---|---|
| 5V | 3V3 |
| GND | GND |
| S1 | GPIO4 |
| S2 | GPIO5 |
| KEY | GPIO6 |

USB 串口速率为 115200。固件发送的消息仅包括旋转、短按、长按与启动就绪状态；电脑端会忽略其他串口文本。

```json
{"type":"encoder","delta":1}
{"type":"encoder","delta":-1}
{"type":"encoder","press":"short"}
{"type":"encoder","press":"long"}
```

## 启动

1. 用 Arduino IDE 烧录固件，确认设备管理器显示一个 COM 口。
2. 关闭 Arduino 串口监视器。同一时间只能有一个程序打开该串口。
3. 在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 src\desktop_app.py --encoder-port COM9
```

把 `COM9` 替换为实际端口。若报“无法打开编码器”，优先检查端口号、USB 线、串口监视器和其他读取串口的软件。

## 菜单操作

- **旋转**：移动选择。
- **短按**：确认、开始录制、暂停或继续等待挥动。
- **长按**：返回；录制中会先进入取消确认，避免误触丢失本次数据。

正式菜单包含“动作作曲”和“音乐指挥”。具体流程见 [快速上手](quickstart.md)。

## 调试串口（可选）

如需只检查编码器事件，可使用本地的 `tools/encoder_monitor.py`；它是调试工具，不是正式演示入口。运行前同样要关闭 Arduino 串口监视器，结束后再启动桌面菜单。
