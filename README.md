# B站缓存转换工具

将 B 站客户端下载的 m4s 音视频缓存合并为可播放的 mp4 文件。

纯本地操作，不联网、不调用 B 站 API、无需登录，永久可用。

## 功能特性

- **三种缓存格式自动识别**
  - PC 客户端缓存（`videoInfo.json` + `<cid>-1-30064.m4s`）
  - 手机 APP 缓存（`entry.json` + `<cid>-1-<qn>-video.m4s`）
  - 裸 m4s 文件（无元信息时按 cid 分组）
- **音视频自动配对**：按 B 站清晰度代码识别视频流（30xxx）和音频流（302xx）
- **流拷贝合并**：使用 ffmpeg `-c copy` 直接封装，不重新编码，速度快、无质量损失
- **后台线程转换**：UI 不卡死，转换过程可实时查看日志
- **批量转换**：支持多选批量处理
- **跳过已存在**：同名 mp4 已存在则自动跳过
- **文件名净化**：自动过滤 Windows 非法字符

## 使用方式

### 方式一：直接运行（需 Python 3 环境）

1. 将 `ffmpeg.exe` 放到脚本同目录（或加入系统 PATH）
2. 双击 `启动转换工具.bat`
3. 或命令行运行：`python bili_converter.py`

### 方式二：打包版 EXE

直接双击 `BiliCacheConverter.exe` 即可，已内置 ffmpeg，无需额外依赖。

## 操作步骤

1. **选择缓存目录**：点击"浏览"选择 B 站缓存根目录（如 `F:\Download\bilibili`）
2. **扫描**：点击"扫描"按钮，列表会显示所有可转换的视频
3. **选择输出目录**（可选）：留空则输出到各视频的缓存目录
4. **转换**：选中要转换的视频，点击"转换选中"或"全部转换"
5. **双击列表行**可直接打开视频所在文件夹

## 支持的缓存结构

### PC 客户端缓存

```
缓存目录/
└── <cid>/
    ├── videoInfo.json       ← 视频元信息
    ├── <cid>-1-30064.m4s    ← 视频流
    ├── <cid>-1-30280.m4s    ← 音频流
    ├── video.temp           ← (可选)已重命名的视频临时文件
    ├── audio.temp           ← (可选)已重命名的音频临时文件
    ├── dm1/dm2/dm3          ← 弹幕(本工具不处理)
    └── image.jpg            ← 封面
```

### 手机 APP 缓存

```
缓存目录/
└── <cid>/
    ├── entry.json           ← 视频元信息
    ├── <cid>-1-<qn>-video.m4s
    └── <cid>-1-<qn>-audio.m4s
```

## 技术实现

- **语言**：Python 3
- **GUI**：tkinter（Python 标准库，无需安装第三方 GUI 框架）
- **合并**：调用 ffmpeg `-i video -i audio -c copy output.mp4`
- **无第三方依赖**：仅使用 Python 标准库

## 从源码构建 EXE

需要安装 PyInstaller：

```bash
pip install pyinstaller
```

将 `ffmpeg.exe` 放到脚本同目录，然后执行：

```bash
pyinstaller --onefile --windowed --name "BiliCacheConverter" --add-binary "ffmpeg.exe;." bili_converter.py
```

生成的 EXE 在 `dist/BiliCacheConverter.exe`。

## 与原工具的区别

本工具是对已停更的"哔哩缓存助手"中**本地转换功能**的独立复刻，去除了在线下载部分：

| 对比项 | 原工具 | 本工具 |
|--------|--------|--------|
| 在线下载 | 有（已失效） | 无 |
| 本地转换 | 有 | 有（功能一致） |
| 合规风险 | 模拟客户端，存在风险 | 纯本地操作，无风险 |
| 维护成本 | 需追 B 站协议变化 | 零 |

## 免责声明

本工具仅处理用户已合法下载的本地缓存文件，不涉及任何在线下载、破解或绕过 DRM 的功能。用户应确保对所处理的缓存文件拥有合法使用权。

## 许可

MIT License
