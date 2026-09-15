# 连续变速播放器（已冻结实验）

本文件记录 `src/tempo_player.py` 的连续变速试验背景。它不属于当前正式演示流程。

经过试听，正式产品已关闭实时变速：

- 月光曲指挥只控制启停与音量。
- 卡农摇滚分轨按原 MIDI 速度播放，动作强度控制声部层级。
- 正式入口是 `src/desktop_app.py`，请按 [快速上手](quickstart.md) 启动。

`tempo_player.py` 仍保留音频加载、连续播放和历史离线测试代码；除非重新开展变速实验，不应把它作为比赛现场启动方式。

## 保留原因

月光曲播放仍复用其中的稳定音频播放基础设施，因此需要：

```text
src/audio/native/stream_stretch.dll
```

该 DLL 是 Windows x64 本机构建产物，未纳入 Git。换电脑时需一并携带该文件；若必须重新构建，使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-tempo.txt
.\.venv\Scripts\python.exe tools\build_stream_stretch.py
```

重新构建需要 Windows C++ 构建工具与网络连接，建议在比赛前完成，而不是现场处理。
