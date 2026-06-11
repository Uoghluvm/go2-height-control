# Go2 Height Control Web Console

这是一个面向 Unitree Go2 的低姿态控制功能包，基于 `unitree_webrtc_connect` 通过 WebRTC DataChannel 发送 Sport API 指令。

它包含两套入口：

- `go2_height_control_ui/`：本地 Web 控制台，适合演示、调参和客户现场操作。
- `go2_height_control_legacy_114/`：命令行脚本，适合诊断、自动低姿态前进和紧急恢复。

## 固件兼容性

已验证的高度控制路径：

```text
Go2 固件 1.1.4
WebRTC LocalSTA
Sport API BodyHeight = 1013
motion mode = normal
```

版本说明：

- `1.1.4`：公开 `BodyHeight=1013` 在普通 `normal` sport mode 下可用，本项目的低姿态控制和匍匐前进按这个版本实现。
- `1.1.7` 到 `1.1.11`：通常运行在 `mcf` 运动模式。实测公开 WebRTC/DDS 接口里 `BodyHeight=1013` 返回 `3203` 或不生效，因此可以安装和运行诊断，但不能保证能通过本项目调节机身高度。
- `1.1.11` 以下但不是 `1.1.4`：请先运行诊断脚本。如果 `BodyHeight` 响应码为 `0`，再继续测试；如果返回 `3203` 或其他非 `0`，说明当前固件/模式不支持这个公开接口。

本项目不包含固件升级或降级工具，也不会绕过固件限制。固件切换有风险，应单独确认来源和流程。

## 准备环境

推荐使用 Ubuntu 20.04/22.04，Python 3.8 以上。

安装基础工具：

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv netcat
```

如果系统里 `netcat` 包名不可用，可改装：

```bash
sudo apt install -y netcat-openbsd
```

建议使用虚拟环境：

```bash
python3 -m venv ~/go2-webrtc-venv
source ~/go2-webrtc-venv/bin/activate
python -m pip install --upgrade pip
```

Web 页面的视频流预览使用 `unitree_webrtc_connect` 的 WebRTC video track。OpenCV 只用于把收到的帧编码成 MJPEG 给浏览器显示。上游 `unitree_webrtc_connect` 通常会安装 `opencv-python`；如果当前环境缺少 `cv2`，任选一种方式安装：

```bash
python -m pip install opencv-python
```

或：

```bash
sudo apt install -y python3-opencv
```

## 安装 unitree_webrtc_connect

本功能包依赖上游 `unitree_webrtc_connect` Python 包。先克隆并安装上游项目：

```bash
cd ~
git clone https://github.com/legion1581/unitree_webrtc_connect.git
cd unitree_webrtc_connect
python -m pip install -e .
```

验证 Python 能导入：

```bash
python - <<'PY'
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD
print("unitree_webrtc_connect OK")
print("BodyHeight api:", SPORT_CMD.get("BodyHeight"))
PY
```

正常应看到：

```text
unitree_webrtc_connect OK
BodyHeight api: 1013
```

如果你之前已经 clone 过 `unitree_webrtc_connect`，仍建议更新它，确保 WebRTC 基础连接、鉴权和 DataChannel 代码是新的：

```bash
source ~/go2-webrtc-venv/bin/activate
cd ~/unitree_webrtc_connect
git pull
python -m pip install -e .
```

说明：本项目的视频功能使用上游 `UnitreeWebRTCConnection.video`，并会在连接后发送 `switchVideoChannel(True)` 开启视频通道。

## 安装本功能包

克隆本仓库：

```bash
cd ~
git clone https://github.com/Uoghluvm/go2-height-control.git
cd go2-height-control
```

本仓库只放高度控制功能代码。运行时需要能导入刚才安装的 `unitree_webrtc_connect`。

如果你使用虚拟环境，每次运行前先进入环境：

```bash
source ~/go2-webrtc-venv/bin/activate
```

## 制作安装包

如果是给最终用户使用，推荐制作安装包，而不是要求用户手动安装 Python 依赖。

当前打包策略：

- Ubuntu 22.04：用 PyInstaller 先冻结成本机可执行程序，再打进 `.deb`。用户安装后直接运行 `go2-height-control`。
- Windows：用 PyInstaller 冻结成 exe 文件夹，再用 Inno Setup 制作 `.exe` 安装器。用户安装后从开始菜单或桌面快捷方式启动。
- Python、`unitree_webrtc_connect`、`aiortc`、`opencv-python` 等依赖由构建机安装并打进产物；最终用户不需要手动运行 `pip install`。

### Ubuntu 22.04 .deb

构建机需要 Ubuntu 22.04、Python 3、venv、pip、git、dpkg-deb，并且能访问 Python 包源和 GitHub：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip dpkg-dev
```

在仓库根目录运行：

```bash
packaging/linux/build_deb.sh
```

生成文件：

```text
dist/packages/go2-height-control_0.1.0_amd64.deb
```

用户安装：

```bash
sudo apt install ./go2-height-control_0.1.0_amd64.deb
go2-height-control
```

浏览器打开：

```text
http://127.0.0.1:8765
```

### Windows exe 安装器

构建机需要 Windows、Python 3、git。如果要生成正式安装器，还需要安装 Inno Setup 6。

在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
```

如果已安装 Inno Setup，会生成：

```text
dist\installer\go2-height-control-setup-0.1.0.exe
```

如果没有安装 Inno Setup，也会先生成可直接运行的便携版目录：

```text
dist\go2-height-control\
```

Windows 用户安装后直接启动 `Go2 Height Control`，浏览器打开：

```text
http://127.0.0.1:8765
```

## 连接 Go2

本项目默认使用 LocalSTA 方式连接机器人，默认 IP 是：

```text
192.168.12.137
```

先确认电脑和 Go2 在同一网络内，然后检查 WebRTC 信令端口：

```bash
nc -vz 192.168.12.137 9991
```

成功时类似：

```text
Connection to 192.168.12.137 9991 port [tcp/*] succeeded!
```

如果你的 Go2 IP 不同，运行时用环境变量覆盖：

```bash
export UNITREE_ROBOT_IP=你的机器人IP
```

常见连接方式：

- 电脑连接 Go2 Wi-Fi 或与 Go2 在同一局域网时，确认机器人的实际 IP 后使用 `UNITREE_ROBOT_IP`。
- 如果你使用网线直连或路由器分配地址，先用路由器后台、`arp -a`、`ip neigh` 或 Unitree App 确认 IP。
- 本项目脚本当前封装的是 `WebRTCConnectionMethod.LocalSTA`。如果你需要 AP 模式，需要在 `go2_height_control_legacy_114/common.py` 里改 `make_connection()` 的连接方式。

## 第一次诊断

先运行诊断，不要直接执行低姿态移动：

```bash
cd ~/go2-height-control
source ~/go2-webrtc-venv/bin/activate
source go2_height_control_legacy_114/config.env
python go2_height_control_legacy_114/diagnose_go2.py
```

如果 IP 不同：

```bash
UNITREE_ROBOT_IP=你的机器人IP python go2_height_control_legacy_114/diagnose_go2.py
```

`1.1.4` 正常情况应看到类似：

```text
Motion mode: normal
BalanceStand response code: 0
Test BodyHeight response code: 0
Restore BodyHeight response code: 0
```

如果看到：

```text
BodyHeight response code: 3203
```

通常表示当前固件或运动模式不支持公开 `BodyHeight=1013` 设置接口。`1.1.7-1.1.11` 的 MCF 模式常见这个结果。

## 启动 Web 控制台

在仓库根目录运行：

```bash
cd ~/go2-height-control
source ~/go2-webrtc-venv/bin/activate
python go2_height_control_ui/backend.py
```

浏览器打开：

```text
http://127.0.0.1:8765
```

如果需要让同一局域网里的其他设备访问：

```bash
GO2_UI_HOST=0.0.0.0 python go2_height_control_ui/backend.py
```

然后在其他设备浏览器访问：

```text
http://控制电脑IP:8765
```

页面推荐流程：

1. 填写或确认机器人 IP。
2. 点击“诊断 BodyHeight”。
3. 如果诊断成功，点击“切换普通运动模式”。
4. 低姿态演示时，点击“降低高度并前进 2m”。
5. 手动控制时，点击“启动键盘遥控”。
6. 需要查看相机画面时，点击“开启视频”。
7. 状态异常时，点击“停止并恢复高度”。

## 读取 Go2 视频流

Web 控制台提供“视频流”区域。点击“开启视频”后，后端会使用 `unitree_webrtc_connect` 的 WebRTC video track 接收 Go2 相机画面，再编码为 MJPEG 给浏览器显示。

```text
Go2 WebRTC video track
-> aiortc frame.to_ndarray(format="bgr24")
-> OpenCV JPEG encode
-> Python backend MJPEG
-> browser img
```

关键实现逻辑和已验证成功的示例一致：

1. 先 `await conn.connect()` 建立 WebRTC 连接。
2. 马上注册 `conn.video.add_track_callback(...)`。
3. 再调用 `conn.video.switchVideoChannel(True)` 开启视频通道，避免“先开视频再注册 callback”的竞态。

使用步骤：

1. 启动 Web 控制台。
2. 在网页里填写实际 Go2 IP，默认是 `192.168.12.137`。
3. 点击“开启视频”。
4. 页面显示来源、分辨率、帧数和最近帧延迟。
5. 不需要画面时点击“关闭视频”。

视频功能只读取 Go2 WebRTC 相机画面，不会发送运动命令。

可先单独测试上游 WebRTC 视频示例：

```bash
cd ~/unitree_webrtc_connect
export UNITREE_ROBOT_IP=192.168.12.137
python examples/go2/video/camera_stream/display_video_channel.py
```

如果示例终端持续打印 `Shape: ...`，说明 WebRTC 视频帧正常到达。

## 命令行执行低姿态前进

加载默认参数：

```bash
source go2_height_control_legacy_114/config.env
```

默认参数：

```text
UNITREE_ROBOT_IP=192.168.12.137
LOW_BODY_HEIGHT=-0.13
NORMAL_BODY_HEIGHT=0.0
CRAWL_DISTANCE_M=2.0
CRAWL_SPEED_MPS=0.20
MOVE_COMMAND_PERIOD_S=0.10
REMOTE_FORWARD_LY=0.45
ESTIMATED_SPEED_MPS=0.20
REMOTE_PUBLISH_PERIOD_S=0.02
```

执行 Sport `Move` 版本：

```bash
python go2_height_control_legacy_114/lower_and_crawl.py
```

执行流程：

```text
连接机器人
读取 motion mode
必要时尝试切到 normal
BalanceStand
BodyHeight=-0.13
持续重复发送 Move
估算前进 2m
StopMove
BodyHeight=0.0
断开连接
```

为什么要重复发送 `Move`：

Go2 的 `Move` 是短时速度指令，通常会被看门狗自动停止。只发送一次只能移动很短时间，所以脚本按 `MOVE_COMMAND_PERIOD_S=0.10` 周期重复发送。

如果想用模拟遥控器摇杆前推，而不是 Sport `Move`：

```bash
python go2_height_control_legacy_114/remote_forward_crawl.py
```

`REMOTE_FORWARD_LY` 是归一化摇杆量，不是 m/s。实际距离需要按地面、负载、电量和固件状态校准。

## 键盘和滑动条

Web 页面点击“启动键盘遥控”后，后端会保持 WebRTC 长连接，并持续把键盘状态转换成 `rt/wirelesscontroller` 摇杆指令。

键位：

```text
W / S：左摇杆前后
A / D：左摇杆左右
I / K：右摇杆前后
J / L：右摇杆左右
Q 或 ↑：身体升高一个步进
E 或 ↓：身体降低一个步进
```

下方“目标偏移滑动条”可以直接拖动到指定偏移值，默认范围：

```text
MIN_BODY_HEIGHT=-0.13
MAX_BODY_HEIGHT=0.05
HEIGHT_STEP_M=0.01
```

滑动条只在“启动键盘遥控”后发送 `BodyHeight`。拖动时前端按约 `20ms` 节流发送当前位置。

## 高度参数含义

这里发送给 Go2 的不是官方文档中 `0.15-0.36m` 的绝对机身高度，而是 Sport API `BodyHeight=1013` 的相对偏移量：

```text
0.00：恢复普通站立高度
负数：在当前普通高度基础上降低身体
正数：在当前普通高度基础上抬高身体
```

例如普通站立实际高度约 `0.33m`，发送：

```text
BodyHeight = -0.13
```

可理解为目标实际高度大约：

```text
0.33m - 0.13m = 0.20m
```

理论上按绝对高度 `0.15-0.36m` 换算，最低偏移大约到 `-0.18m`。但当前实测目标低于 `-0.13m` 后不再继续降低，所以默认把最低偏移限制为 `-0.13m`，最高限制为 `0.05m`。

## 紧急恢复

如果脚本中断、页面卡住或高度没有恢复，运行：

```bash
cd ~/go2-height-control
source ~/go2-webrtc-venv/bin/activate
source go2_height_control_legacy_114/config.env
python go2_height_control_legacy_114/restore_height.py
```

恢复脚本会发送：

```text
StopMove
BodyHeight=0.0
```

## 常见问题

`ModuleNotFoundError: No module named 'unitree_webrtc_connect'`

说明上游包没有安装到当前 Python 环境。重新进入虚拟环境并安装：

```bash
source ~/go2-webrtc-venv/bin/activate
cd ~/unitree_webrtc_connect
python -m pip install -e .
```

`WebRTC 视频黑屏或没有帧`

优先检查：

- `UNITREE_ROBOT_IP` 是否是实际 Go2 IP，默认现在是 `192.168.12.137`。
- 是否能运行上面的 `examples/go2/video/camera_stream/display_video_channel.py` 并看到 `Shape: ...` 输出。
- 当前 Python 是否能导入 `cv2`、`aiortc` 和本地 `unitree_webrtc_connect`。

```bash
python3 - <<'PY'
import cv2, aiortc, unitree_webrtc_connect
print(cv2.__version__)
print(aiortc.__version__)
print(unitree_webrtc_connect.__file__)
PY
```

视频画面不出现

优先检查：

- 是否点击了“开启视频”。
- 是否已经点击“开启视频”，日志里是否出现 `WebRTC 视频通道已开启`。
- 上游 WebRTC 视频示例是否同样黑屏。
- 网络是否稳定；视频比普通 Sport API 更依赖带宽和丢包情况。

`nc` 连不上 `9991`

优先检查：

- 电脑是否和 Go2 在同一网络。
- `UNITREE_ROBOT_IP` 是否填的是机器人 IP，而不是电脑自己的 IP。
- Go2 是否开机完成，WebRTC 服务是否启动。
- 防火墙或代理是否影响本机到机器人局域网连接。

`BodyHeight` 返回 `3203`

通常是当前固件或运动模式不支持这个公开接口。`1.1.7-1.1.11` 的 MCF 模式常见。可以继续使用连接诊断和其他 WebRTC 功能，但本项目不能强行调节高度。

机器人只动一下就停

这是 `Move` 看门狗行为。请使用本项目的 `lower_and_crawl.py`，它会按 `MOVE_COMMAND_PERIOD_S` 重复发送速度指令。

页面能打开但按钮无响应

确认启动后端的终端是否有报错，并确认浏览器访问的是后端地址 `http://127.0.0.1:8765`，不是直接打开 HTML 文件。

## 安全说明

- 第一次测试不要站在机器人正前方。
- 确保机器人周围至少 2 到 3 米空旷空间。
- 不要在楼梯、坡道、湿滑地面、桌面边缘测试。
- 第一次低姿态测试建议使用保守参数：

```bash
LOW_BODY_HEIGHT=-0.10 CRAWL_DISTANCE_M=1.0 python go2_height_control_legacy_114/lower_and_crawl.py
```

- 如果任何响应码不是 `0`，先停止测试并运行恢复脚本。

## 文件结构

```text
go2-height-control/
├── README.md
├── go2_height_control_legacy_114/
│   ├── README.md
│   ├── common.py
│   ├── config.env
│   ├── diagnose_go2.py
│   ├── lower_and_crawl.py
│   ├── remote_forward_crawl.py
│   └── restore_height.py
└── go2_height_control_ui/
    ├── README.md
    ├── backend.py
    └── static/
        ├── app.js
        ├── index.html
        └── styles.css
```
