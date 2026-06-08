# Go2 低姿态匍匐控制功能包（固件 1.1.4）

本项目用于 Unitree Go2 在 **1.1.4 固件** 下执行低姿态高度控制和短距离匍匐前进。

默认参数：

```text
机器人 IP: 192.168.12.2
最低偏移: -0.13 m
恢复高度: 0.00 m
前进距离: 2.0 m
前进速度: 0.20 m/s
Move 重发周期: 0.10 s
```

## 1. 适用范围

适用：

- Go2 固件 1.1.4
- WebRTC 局域网连接
- `BodyHeight=1013` 可用的普通 sport mode
- 需要先降低身体高度，再低速前进，最后恢复正常高度的任务

说明：

新版 1.1.7 到 1.1.11 中，机器人通常处于 `mcf` 运动模式。实测公开 WebRTC/DDS 接口里 `BodyHeight=1013` 返回 `3203`，不能设置身体高度。因此本方案采用 1.1.4 固件作为兼容性实现。

## 2. 文件说明

```text
go2_height_control_legacy_114/
├── README.md                 中文使用说明
├── config.env                默认参数配置
├── common.py                 公共连接、sport API、高度和移动封装
├── diagnose_go2.py           诊断脚本：连接、模式、BodyHeight 测试
├── lower_and_crawl.py        主任务：降低高度 + Move 持续前进 + 恢复高度
├── remote_forward_crawl.py   模拟遥控器摇杆前进版本
└── restore_height.py         紧急恢复：StopMove + BodyHeight=0
```

## 3. 运行前准备

进入项目根目录：

```bash
cd ~/unitree_webrtc_connect
```

确认机器人网络：

```bash
nc -vz 192.168.12.2 9991
```

看到类似下面输出表示 WebRTC 信令端口可用：

```text
Connection to 192.168.12.2 9991 port [tcp/*] succeeded!
```

如果 IP 不同，可临时覆盖：

```bash
UNITREE_ROBOT_IP=你的机器人IP python go2_height_control_legacy_114/diagnose_go2.py
```

## 4. 参数配置

默认参数写在 `config.env` 中，也可以用环境变量覆盖。

加载默认配置：

```bash
source go2_height_control_legacy_114/config.env
```

常用参数：

```bash
export UNITREE_ROBOT_IP=192.168.12.2
export LOW_BODY_HEIGHT=-0.13
export NORMAL_BODY_HEIGHT=0.0
export CRAWL_DISTANCE_M=2.0
export CRAWL_SPEED_MPS=0.20
export MOVE_COMMAND_PERIOD_S=0.10
```

## 5. 第一次诊断

先运行诊断脚本：

```bash
source go2_height_control_legacy_114/config.env
python go2_height_control_legacy_114/diagnose_go2.py
```

正常情况下应看到：

```text
BalanceStand response code: 0
Test BodyHeight response code: 0
Restore BodyHeight response code: 0
```

如果 `BodyHeight` 不是 `0`，说明当前固件或运动模式不支持本方案。

## 6. 执行低姿态匍匐

运行主任务：

```bash
source go2_height_control_legacy_114/config.env
python go2_height_control_legacy_114/lower_and_crawl.py
```

执行流程：

```text
连接机器人
检查 motion mode
BalanceStand
BodyHeight=-0.13
等待高度稳定
每 0.10 秒重复发送 Move
估算前进 2 米
StopMove
BodyHeight=0.0
断开连接
```

为什么要重复发送 Move：

Go2 的 `Move` 是短时速度指令，通常会被看门狗自动停止。只发一次只能移动很短时间，因此脚本会按 `MOVE_COMMAND_PERIOD_S=0.10` 周期重复发送，保证持续前进。

## 7. 紧急恢复

如果中途异常或高度没有恢复，运行：

```bash
source go2_height_control_legacy_114/config.env
python go2_height_control_legacy_114/restore_height.py
```

它会执行：

```text
StopMove
BodyHeight=0.0
```

## 8. 模拟遥控器前进版本

如果想用 `rt/wirelesscontroller` 模拟左摇杆前推，而不是 sport `Move`：

```bash
source go2_height_control_legacy_114/config.env
python go2_height_control_legacy_114/remote_forward_crawl.py
```

相关参数：

```bash
export REMOTE_FORWARD_LY=0.45
export ESTIMATED_SPEED_MPS=0.20
export REMOTE_PUBLISH_PERIOD_S=0.02
```

注意：`REMOTE_FORWARD_LY` 是归一化摇杆量，不是米每秒。实际距离需要按地面摩擦、机器人状态和电量校准。

## 9. 安全注意事项

运行前请确认：

- 机器人在平地
- 周围 2 米内无人员和障碍物
- 电量充足
- 不在楼梯、坡道、湿滑地面上测试
- 第一次测试先用较保守高度，例如 `LOW_BODY_HEIGHT=-0.10`

保守测试命令：

```bash
LOW_BODY_HEIGHT=-0.10 CRAWL_DISTANCE_M=1.0 python go2_height_control_legacy_114/lower_and_crawl.py
```

## 10. 交付说明

本功能包不是简单的固件降级脚本，而是对 Go2 高度控制能力做了兼容性验证后的工程化封装：

- 固件兼容性判断
- BodyHeight 控制封装
- Move 看门狗重发机制
- 低姿态匍匐任务编排
- 异常恢复逻辑
- 参数化配置
- 诊断脚本
- 中文操作教程

在 1.1.4 固件下，公开 `BodyHeight=1013` 接口可用，因此可以稳定实现低姿态匍匐。新版 1.1.7 到 1.1.11 的 MCF 模式未开放等价高度 set 接口，已通过 WebRTC 和 DDS 两条路径验证。
