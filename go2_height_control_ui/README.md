# Go2 低姿态控制 Web 界面

这是给 Go2 固件 `1.1.4` 准备的本地网页控制台。它不会替代底层控制脚本，而是通过后端启动 `go2_height_control_legacy_114/` 里的脚本，让操作更直观。

## 功能

- 在网页里修改机器人 IP、低姿态偏移、前进距离、速度和 Move 周期。
- 一键切换到普通运动模式 `normal`。
- 一键执行“降低高度 -> 前进约 2m -> 恢复高度”。
- 一键运行 BodyHeight 诊断。
- 一键停止并恢复正常高度。
- 页面显示实时日志，方便给客户演示和排查问题。
- 支持网页键盘遥控：`WASD` 为左摇杆，`IJKL` 为右摇杆，`Q/↑` 升高身体，`E/↓` 降低身体。
- 支持在遥控区域用滑动条直接设置目标偏移。
- 显示当前目标高度、反馈高度、速度、步态/模式和高度响应码。
- 支持读取 Go2 H.264 UDP 组播视频流，在网页中显示相机画面。

## 适用范围

这套界面默认针对：

- Go2 固件：`1.1.4`
- WebRTC IP：`192.168.12.2`
- WebRTC 端口：`9991`
- BodyHeight API：`1013`

如果是 `1.1.7-1.1.11` 的 MCF 模式，之前测试过 `BodyHeight=1013` 会返回 `3203`，这套 Web 界面也不能绕过固件限制。

## 启动界面

如果需要使用视频流，先安装 GStreamer、带 GStreamer 支持的 OpenCV 和 `iproute2`：

```bash
sudo apt install -y iproute2 python3-opencv gstreamer1.0-tools gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav
```

不要依赖 pip 的 `opencv-python` 来跑视频预览；它通常不带 GStreamer 支持。

在仓库根目录运行：

```bash
cd ~/go2-height-control
python go2_height_control_ui/backend.py
```

浏览器打开：

```text
http://127.0.0.1:8765
```

如果需要让局域网内其他设备访问：

```bash
GO2_UI_HOST=0.0.0.0 python go2_height_control_ui/backend.py
```

然后用控制电脑的 IP 访问 `http://控制电脑IP:8765`。

## 推荐操作流程

1. 电脑连接 Go2 Wi-Fi。
2. 确认端口可用：

```bash
nc -vz 192.168.12.2 9991
```

3. 启动 Web 后端：

```bash
python go2_height_control_ui/backend.py
```

4. 打开网页后先点“诊断 BodyHeight”。
5. 点“切换普通运动模式”。
6. 诊断成功后点“降低高度并前进 2m”。
7. 如果机器人状态不对，点“停止并恢复高度”。

## 键盘遥控

网页里点击“启动键盘遥控”后，后端会保持 WebRTC 长连接，并持续把键盘状态转换成 `rt/wirelesscontroller` 摇杆指令。

启动键盘遥控时，后端会先尝试调用 motion switcher，把机器人切到 `normal` 普通运动模式。如果固件或当前状态不允许切换，日志里会显示响应码。

键位如下：

```text
W / S：左摇杆前后
A / D：左摇杆左右
I / K：右摇杆前后
J / L：右摇杆左右
Q 或 ↑：身体升高一个步进
E 或 ↓：身体降低一个步进
```

下方“目标偏移滑动条”可以直接拖动到指定偏移值，默认范围是 `-0.13m` 到 `0.05m`，步进是 `0.01m`。滑动条只在“启动键盘遥控”后才会向机器人发送 `BodyHeight` 指令；拖动时按约 `20ms` 节流持续发送当前位置。未启动时只会提示先启动遥控。

页面会实时显示：

```text
左摇杆位置
右摇杆位置
目标高度
机器人反馈高度
速度反馈
步态/模式
运动模式切换结果
BodyHeight 响应码
```

如果浏览器窗口失去焦点，前端会自动清空按键状态；如果后端超过约 0.35 秒收不到键盘输入，也会自动发零摇杆，避免持续运动。

## 视频流

页面里的“视频流”区域用于读取 Go2 相机画面。点击“开启视频”后，后端会打开 Go2 H.264 UDP 组播流，解码后再编码为 MJPEG 给浏览器显示。

```text
Go2 H264 RTP multicast 230.1.1.1:1720
-> GStreamer/OpenCV decode
-> Python backend JPEG/MJPEG
-> browser img
```

使用前确认：

```bash
gst-launch-1.0 --version
```

操作流程：

1. 在网页里填写实际 Go2 IP。
2. “视频组播网卡”默认保持 `auto`。后端会根据 Go2 IP 自动识别电脑连接 Go2 的网卡。
3. 如果自动识别失败，再手动改成 `eth0`、`enp3s0`、`enx...` 这类真实网卡名。
4. 保持默认组播地址 `230.1.1.1` 和端口 `1720`。
5. 点击“开启视频”。
6. 页面会显示画面、实际使用的网卡、分辨率、帧数和最近帧延迟。
7. 不需要画面时点击“关闭视频”。

后端会先查本机 IPv4 地址段，优先选择和 Go2 IP 在同一子网的网卡；找不到同子网网卡时，再用路由结果兜底。可用下面命令查看路由兜底会返回的网卡：

```bash
ip route get 你的机器人IP
```

输出里的 `dev xxx` 就是组播网卡名。

视频功能只读取相机画面，不会发送运动命令。它不使用 `unitree_webrtc_connect` 的 `conn.video`，而是使用和 `go2_l2_ros2_humble` 中 `go2_h264_repub` 相同的 H.264 组播管线。

可单独测试管线：

```bash
gst-launch-1.0 udpsrc address=230.1.1.1 port=1720 multicast-iface=你的网卡名 \
  ! application/x-rtp,media=video,encoding-name=H264 \
  ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! autovideosink
```

如果页面提示无法打开视频，通常是自动识别不到网卡、手动网卡名不对，或者当前 OpenCV 不支持 GStreamer。

## 高度参数说明

界面里的可输入高度不是官方文档里 `0.15-0.36m` 那种“机身绝对高度”。

这里发送给 Go2 的是 Sport API `BodyHeight=1013` 的相对偏移量：

```text
0.00：恢复普通站立高度
负数：在当前普通高度基础上降低身体
正数：在当前普通高度基础上抬高身体
```

例如普通站立时实际高度大约是 `0.33m`，发送：

```text
BodyHeight = -0.13
```

可以理解为目标实际高度大约接近：

```text
0.33m - 0.13m = 0.20m
```

按官方绝对高度 `0.15-0.36m` 理论换算，最低偏移大约可以到 `-0.18m`。但当前这台 Go2 实测 `BodyHeight` 目标低于 `-0.13m` 后不再继续降低，因此界面默认把最低偏移限制为 `-0.13m`；最高偏移按你的要求限制为 `0.05m`。

所以本界面里的 `LOW_BODY_HEIGHT=-0.13`、`MIN_BODY_HEIGHT=-0.13` 这类值，表示“高度偏移量”，不是让机器人达到 `-0.13m` 的绝对高度。

页面里的“实际高度反馈”来自 `sportmodestate`。如果 `GetBodyHeight` 返回 `3203`，说明当前固件不支持这个查询接口，后端会停止重复查询，避免日志刷屏。

## 默认参数

后端默认参数如下：

```text
UNITREE_ROBOT_IP=192.168.12.2
LOW_BODY_HEIGHT=-0.13
NORMAL_BODY_HEIGHT=0.0
CRAWL_DISTANCE_M=2.0
CRAWL_SPEED_MPS=0.20
MOVE_COMMAND_PERIOD_S=0.10
REMOTE_FORWARD_LY=0.45
REMOTE_PUBLISH_PERIOD_S=0.02
KEYBOARD_AXIS_SCALE=0.55
HEIGHT_STEP_M=0.01
MIN_BODY_HEIGHT=-0.13
MAX_BODY_HEIGHT=0.05
VIDEO_MULTICAST_IFACE=auto
VIDEO_MULTICAST_ADDRESS=230.1.1.1
VIDEO_MULTICAST_PORT=1720
```

键盘调高度时，如果目标偏移已经到达 `MIN_BODY_HEIGHT` 或 `MAX_BODY_HEIGHT`，后端不会继续越界发送高度目标，页面会提示“不能再下降”或“不能再升高”。

这些参数也可以直接在网页里修改。网页提交的参数只影响本次执行，不会改动源码。

## 文件结构

```text
go2_height_control_ui/
├── backend.py
├── README.md
└── static/
    ├── app.js
    ├── index.html
    └── styles.css
```

## 安全说明

- 第一次测试时不要站在机器人正前方。
- 确保机器人周围至少有 3 米空旷空间。
- 执行低姿态前进前，先用“诊断 BodyHeight”确认固件确实支持调节高度。
- 页面只是操作入口，真正的运动逻辑仍在 `go2_height_control_legacy_114/` 中。
- 如果页面卡住，可以在终端按 `Ctrl+C` 退出后端，再运行：

```bash
python go2_height_control_legacy_114/restore_height.py
```
