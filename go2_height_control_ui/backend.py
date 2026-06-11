#!/usr/bin/env python3
import asyncio
import ipaddress
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod


ROOT = Path(__file__).resolve().parents[1]
LEGACY_DIR = ROOT / "go2_height_control_legacy_114"
STATIC_DIR = Path(__file__).resolve().parent / "static"

HOST = os.environ.get("GO2_UI_HOST", "127.0.0.1")
PORT = int(os.environ.get("GO2_UI_PORT", "8765"))

DEFAULT_PARAMS = {
    "UNITREE_ROBOT_IP": "192.168.12.2",
    "LOW_BODY_HEIGHT": "-0.13",
    "NORMAL_BODY_HEIGHT": "0.0",
    "CRAWL_DISTANCE_M": "2.0",
    "CRAWL_SPEED_MPS": "0.20",
    "MOVE_COMMAND_PERIOD_S": "0.10",
    "REMOTE_FORWARD_LY": "0.45",
    "REMOTE_PUBLISH_PERIOD_S": "0.02",
    "KEYBOARD_AXIS_SCALE": "0.55",
    "HEIGHT_STEP_M": "0.01",
    "MIN_BODY_HEIGHT": "-0.13",
    "MAX_BODY_HEIGHT": "0.05",
    "VIDEO_MULTICAST_IFACE": "auto",
    "VIDEO_MULTICAST_ADDRESS": "230.1.1.1",
    "VIDEO_MULTICAST_PORT": "1720",
}

TASKS = {
    "diagnose": "diagnose_go2.py",
    "crawl": "lower_and_crawl.py",
    "remote": "remote_forward_crawl.py",
    "restore": "restore_height.py",
}

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


class TaskManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.task_name = None
        self.started_at = None
        self.finished_at = None
        self.exit_code = None
        self.logs = []

    def snapshot(self):
        with self.lock:
            running = self.process is not None and self.process.poll() is None
            return {
                "running": running,
                "task": self.task_name,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "exit_code": self.exit_code,
                "logs": self.logs[-600:],
                "defaults": DEFAULT_PARAMS,
            }

    def append_log(self, line):
        with self.lock:
            stamp = time.strftime("%H:%M:%S")
            self.logs.append(f"[{stamp}] {line.rstrip()}")
            self.logs = self.logs[-1000:]

    def start(self, task_name, params):
        if task_name not in TASKS:
            raise ValueError(f"Unknown task: {task_name}")

        with self.lock:
            running = self.process is not None and self.process.poll() is None
            if running and task_name != "restore":
                raise RuntimeError("已有任务正在运行，请先停止或等待完成")

        if task_name == "restore":
            self.stop_current()

        env = os.environ.copy()
        for key, default_value in DEFAULT_PARAMS.items():
            value = params.get(key, default_value)
            env[key] = str(value)

        script = TASKS[task_name]
        command = [sys.executable, str(LEGACY_DIR / script)]

        with self.lock:
            self.logs.clear()
            self.task_name = task_name
            self.started_at = time.time()
            self.finished_at = None
            self.exit_code = None
            self.process = subprocess.Popen(
                command,
                cwd=str(LEGACY_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            process = self.process

        self.append_log(f"启动任务: {task_name}")
        self.append_log("参数: " + json.dumps({k: env[k] for k in DEFAULT_PARAMS}, ensure_ascii=False))

        thread = threading.Thread(target=self._read_process, args=(process,), daemon=True)
        thread.start()

    def stop_current(self):
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                return

        self.append_log("正在停止当前任务...")
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            return

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.append_log("任务未及时退出，发送 SIGTERM")
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def _read_process(self, process):
        assert process.stdout is not None
        for line in process.stdout:
            self.append_log(line)

        exit_code = process.wait()
        with self.lock:
            if self.process is process:
                self.exit_code = exit_code
                self.finished_at = time.time()
                self.process = None
        self.append_log(f"任务结束，退出码: {exit_code}")


manager = TaskManager()


def response_code(response):
    return response.get("data", {}).get("header", {}).get("status", {}).get("code")


def response_data(response):
    return response.get("data", {}).get("data", "")


async def sport_call(conn, command, parameter=None):
    payload = {"api_id": SPORT_CMD[command]}
    if parameter is not None:
        payload["parameter"] = parameter
    return await conn.datachannel.pub_sub.publish_request_new(RTC_TOPIC["SPORT_MOD"], payload)


def publish_remote(pub_sub, lx=0.0, ly=0.0, rx=0.0, ry=0.0, keys=0):
    pub_sub.publish_without_callback(
        RTC_TOPIC["WIRELESS_CONTROLLER"],
        {"lx": lx, "ly": ly, "rx": rx, "ry": ry, "keys": keys},
    )


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def parse_json_data(raw):
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


def detect_route_iface(target_ip):
    try:
        target = ipaddress.ip_address(target_ip)
    except ValueError:
        return None

    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "addr", "show"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        links = json.loads(result.stdout)
        for link in links:
            ifname = link.get("ifname")
            if not ifname or ifname == "lo":
                continue
            for info in link.get("addr_info", []):
                local = info.get("local")
                prefixlen = info.get("prefixlen")
                if not local or prefixlen is None:
                    continue
                network = ipaddress.ip_network(f"{local}/{prefixlen}", strict=False)
                if target in network:
                    return ifname
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["ip", "route", "get", target_ip],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None

    parts = result.stdout.split()
    if "dev" not in parts:
        return None
    index = parts.index("dev")
    if index + 1 >= len(parts):
        return None
    return parts[index + 1]


async def get_motion_mode(conn):
    response = await conn.datachannel.pub_sub.publish_request_new(
        RTC_TOPIC["MOTION_SWITCHER"],
        {"api_id": 1001},
    )
    code = response_code(response)
    data = parse_json_data(response_data(response)) or {}
    return code, data.get("name"), data


async def set_normal_motion_mode(conn):
    before_code, before_mode, before_data = await get_motion_mode(conn)
    response = await conn.datachannel.pub_sub.publish_request_new(
        RTC_TOPIC["MOTION_SWITCHER"],
        {"api_id": 1002, "parameter": {"name": "normal"}},
    )
    set_code = response_code(response)
    await asyncio.sleep(2.0)
    after_code, after_mode, after_data = await get_motion_mode(conn)
    return {
        "before_code": before_code,
        "before_mode": before_mode,
        "before_data": before_data,
        "set_code": set_code,
        "after_code": after_code,
        "after_mode": after_mode,
        "after_data": after_data,
    }


class MotionModeManager:
    def __init__(self, task_manager):
        self.task_manager = task_manager
        self.lock = threading.Lock()
        self.running = False
        self.last_result = None
        self.error = None

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "last_result": self.last_result,
                "error": self.error,
            }

    def switch_normal(self, params):
        with self.lock:
            if self.running:
                raise RuntimeError("运动模式切换正在执行")
            self.running = True
            self.error = None

        thread = threading.Thread(target=self._thread_main, args=(params,), daemon=True)
        thread.start()

    def _thread_main(self, params):
        try:
            result = asyncio.run(self._switch_normal(params))
            with self.lock:
                self.last_result = result
            self.task_manager.append_log(
                "普通运动模式切换完成: "
                f"before={result.get('before_mode')} set_code={result.get('set_code')} "
                f"after={result.get('after_mode')}"
            )
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
            self.task_manager.append_log(f"普通运动模式切换失败: {exc}")
        finally:
            with self.lock:
                self.running = False

    async def _switch_normal(self, params):
        env_params = {key: str(params.get(key, value)) for key, value in DEFAULT_PARAMS.items()}
        ip = env_params["UNITREE_ROBOT_IP"]
        self.task_manager.append_log(f"连接 Go2 并切换普通运动模式: {ip}")
        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)
        await conn.connect()
        try:
            return await set_normal_motion_mode(conn)
        finally:
            await conn.disconnect()


class KeyboardController:
    def __init__(self, task_manager):
        self.task_manager = task_manager
        self.lock = threading.Lock()
        self.thread = None
        self.stop_flag = False
        self.loop = None
        self.conn = None
        self.running = False
        self.connected = False
        self.error = None
        self.started_at = None
        self.last_input_at = 0.0
        self.last_state_at = None
        self.last_height_command_at = None
        self.last_height_code = None
        self.axes = {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0}
        self.target_height = 0.0
        self.measured_height = None
        self.last_sport_state = {}
        self.params = DEFAULT_PARAMS.copy()
        self.body_height_query_supported = True

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "connected": self.connected,
                "error": self.error,
                "started_at": self.started_at,
                "last_input_at": self.last_input_at,
                "last_state_at": self.last_state_at,
                "last_height_command_at": self.last_height_command_at,
                "last_height_code": self.last_height_code,
                "axes": dict(self.axes),
                "target_height": self.target_height,
                "measured_height": self.measured_height,
                "sport_state": dict(self.last_sport_state),
            }

    def start(self, params):
        with self.lock:
            if self.running:
                raise RuntimeError("键盘遥控已经在运行")
            self.stop_flag = False
            self.error = None
            self.connected = False
            self.started_at = time.time()
            self.last_input_at = 0.0
            self.last_state_at = None
            self.last_height_command_at = None
            self.last_height_code = None
            self.body_height_query_supported = True
            self.axes = {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0}
            self.params = {key: str(params.get(key, value)) for key, value in DEFAULT_PARAMS.items()}
            self.target_height = float(self.params["NORMAL_BODY_HEIGHT"])
            self.running = True

        self.task_manager.stop_current()
        self.task_manager.append_log("启动键盘遥控会话")
        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self.thread.start()

    def stop(self):
        with self.lock:
            self.stop_flag = True
        self.task_manager.append_log("请求停止键盘遥控会话")

    def update_axes(self, axes):
        with self.lock:
            if not self.running:
                raise RuntimeError("键盘遥控未启动")
            scale = float(self.params["KEYBOARD_AXIS_SCALE"])
            self.axes = {
                "lx": clamp(float(axes.get("lx", 0.0)) * scale, -1.0, 1.0),
                "ly": clamp(float(axes.get("ly", 0.0)) * scale, -1.0, 1.0),
                "rx": clamp(float(axes.get("rx", 0.0)) * scale, -1.0, 1.0),
                "ry": clamp(float(axes.get("ry", 0.0)) * scale, -1.0, 1.0),
            }
            self.last_input_at = time.time()

    def adjust_height(self, direction):
        with self.lock:
            if not self.running:
                raise RuntimeError("键盘遥控未启动")
            step = float(self.params["HEIGHT_STEP_M"])
            lower = float(self.params["MIN_BODY_HEIGHT"])
            upper = float(self.params["MAX_BODY_HEIGHT"])
            requested_height = self.target_height + (step * direction)
            next_height = clamp(requested_height, lower, upper)
            limited = next_height != requested_height
            changed = abs(next_height - self.target_height) >= 0.0005
            self.target_height = next_height
            if changed:
                self.last_height_command_at = 0.0
            if limited and direction < 0:
                message = f"已经到最低偏移 {lower:.2f}m，不能再下降"
            elif limited:
                message = f"已经到最高偏移 {upper:.2f}m，不能再升高"
            else:
                message = ""
            return {
                "target_height": self.target_height,
                "limited": limited,
                "message": message,
                "min_height": lower,
                "max_height": upper,
            }

    def set_height_target(self, height):
        with self.lock:
            if not self.running:
                raise RuntimeError("键盘遥控未启动")
            lower = float(self.params["MIN_BODY_HEIGHT"])
            upper = float(self.params["MAX_BODY_HEIGHT"])
            requested_height = float(height)
            next_height = clamp(requested_height, lower, upper)
            limited = next_height != requested_height
            changed = abs(next_height - self.target_height) >= 0.0005
            self.target_height = next_height
            if changed:
                self.last_height_command_at = 0.0
            if limited and requested_height < lower:
                message = f"已经到最低偏移 {lower:.2f}m，不能再下降"
            elif limited:
                message = f"已经到最高偏移 {upper:.2f}m，不能再升高"
            else:
                message = ""
            return {
                "target_height": self.target_height,
                "limited": limited,
                "message": message,
                "min_height": lower,
                "max_height": upper,
            }

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
            self.task_manager.append_log(f"键盘遥控异常: {exc}")
        finally:
            with self.lock:
                self.running = False
                self.connected = False
                self.conn = None
            self.task_manager.append_log("键盘遥控会话结束")

    async def _run(self):
        with self.lock:
            ip = self.params["UNITREE_ROBOT_IP"]

        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)
        self.conn = conn
        self.task_manager.append_log(f"键盘遥控连接 Go2: {ip}")
        await conn.connect()

        with self.lock:
            self.connected = True

        self._subscribe_state(conn)

        try:
            try:
                result = await set_normal_motion_mode(conn)
                self.task_manager.append_log(
                    "键盘遥控已请求普通运动模式: "
                    f"before={result.get('before_mode')} set_code={result.get('set_code')} "
                    f"after={result.get('after_mode')}"
                )
            except Exception as exc:
                self.task_manager.append_log(f"键盘遥控切换普通运动模式跳过: {exc}")

            try:
                response = await sport_call(conn, "BalanceStand")
                self.task_manager.append_log(f"BalanceStand code={response_code(response)}")
            except Exception as exc:
                self.task_manager.append_log(f"BalanceStand 跳过: {exc}")

            await self._refresh_body_height(conn)
            await self._control_loop(conn)
        finally:
            try:
                publish_remote(conn.datachannel.pub_sub)
                await sport_call(conn, "StopMove")
            except Exception:
                pass
            try:
                await conn.disconnect()
            except Exception:
                pass

    def _subscribe_state(self, conn):
        def callback(message):
            data = message.get("data") or {}
            state = {
                "mode": data.get("mode"),
                "gait_type": data.get("gait_type"),
                "progress": data.get("progress"),
                "body_height": data.get("body_height"),
                "velocity": data.get("velocity"),
                "yaw_speed": data.get("yaw_speed"),
                "foot_raise_height": data.get("foot_raise_height"),
            }
            with self.lock:
                self.last_sport_state = state
                self.last_state_at = time.time()
                if data.get("body_height") is not None:
                    self.measured_height = data.get("body_height")

        try:
            conn.datachannel.pub_sub.subscribe(RTC_TOPIC["LF_SPORT_MOD_STATE"], callback)
            self.task_manager.append_log("已订阅 sportmodestate")
        except Exception as exc:
            self.task_manager.append_log(f"sportmodestate 订阅失败: {exc}")

    async def _refresh_body_height(self, conn):
        with self.lock:
            if not self.body_height_query_supported:
                return

        try:
            response = await sport_call(conn, "GetBodyHeight")
            code = response_code(response)
            data = parse_json_data(response_data(response))
            height = data.get("data") if isinstance(data, dict) else None
            with self.lock:
                self.last_height_code = code
                if height is not None:
                    self.measured_height = height
                if code == 3203:
                    self.body_height_query_supported = False
            if code == 3203:
                self.task_manager.append_log("GetBodyHeight code=3203，当前固件不支持查询，后续改用 sportmodestate 反馈")
            else:
                self.task_manager.append_log(f"GetBodyHeight code={code}, height={height}")
        except Exception as exc:
            self.task_manager.append_log(f"GetBodyHeight 跳过: {exc}")

    async def _set_body_height(self, conn, height):
        response = await sport_call(conn, "BodyHeight", {"data": height})
        code = response_code(response)
        with self.lock:
            self.last_height_code = code
            self.last_height_command_at = time.time()
        self.task_manager.append_log(f"BodyHeight target={height:.3f}, code={code}")

    async def _control_loop(self, conn):
        last_height_sent = None
        next_body_query = 0.0

        while True:
            now = time.time()
            with self.lock:
                if self.stop_flag:
                    break
                axes = dict(self.axes)
                stale = self.last_input_at and now - self.last_input_at > 0.35
                target_height = float(self.target_height)
                last_height_command_at = self.last_height_command_at

            if stale:
                axes = {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0}

            publish_remote(conn.datachannel.pub_sub, **axes)

            should_send_height = (
                last_height_sent is None
                or abs(target_height - last_height_sent) >= 0.001
                or last_height_command_at == 0.0
            )
            if should_send_height:
                await self._set_body_height(conn, target_height)
                last_height_sent = target_height

            if now >= next_body_query:
                await self._refresh_body_height(conn)
                next_body_query = now + 1.5

            await asyncio.sleep(0.02)


keyboard = KeyboardController(manager)
motion_mode = MotionModeManager(manager)


class ActionManager:
    def __init__(self, task_manager):
        self.task_manager = task_manager
        self.lock = threading.Lock()
        self.running = False
        self.action = None
        self.last_result = None
        self.error = None
        self.started_at = None

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "action": self.action,
                "last_result": self.last_result,
                "error": self.error,
                "started_at": self.started_at,
            }

    def front_jump(self, params):
        with self.lock:
            if self.running:
                raise RuntimeError("动作正在执行")
            if keyboard.snapshot()["running"]:
                raise RuntimeError("请先停止键盘遥控，再执行前跳")
            self.running = True
            self.action = "front_jump"
            self.error = None
            self.started_at = time.time()

        self.task_manager.stop_current()
        thread = threading.Thread(target=self._thread_main, args=(params,), daemon=True)
        thread.start()

    def _thread_main(self, params):
        try:
            result = asyncio.run(self._front_jump(params))
            with self.lock:
                self.last_result = result
            self.task_manager.append_log(f"前跳完成: FrontJump code={result.get('front_jump_code')}")
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
            self.task_manager.append_log(f"前跳失败: {exc}")
        finally:
            with self.lock:
                self.running = False

    async def _front_jump(self, params):
        env_params = {key: str(params.get(key, value)) for key, value in DEFAULT_PARAMS.items()}
        ip = env_params["UNITREE_ROBOT_IP"]
        normal_height = float(env_params["NORMAL_BODY_HEIGHT"])

        conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ip)
        self.task_manager.append_log(f"连接 Go2 并执行前跳: {ip}")
        await conn.connect()
        result = {}
        try:
            try:
                mode_result = await set_normal_motion_mode(conn)
                result["motion_mode"] = mode_result
                self.task_manager.append_log(
                    "前跳前切换普通运动模式: "
                    f"before={mode_result.get('before_mode')} set_code={mode_result.get('set_code')} "
                    f"after={mode_result.get('after_mode')}"
                )
            except Exception as exc:
                self.task_manager.append_log(f"前跳前切换普通运动模式跳过: {exc}")

            response = await sport_call(conn, "BalanceStand")
            result["balance_stand_code"] = response_code(response)
            self.task_manager.append_log(f"前跳前 BalanceStand code={result['balance_stand_code']}")
            await asyncio.sleep(0.4)

            response = await sport_call(conn, "BodyHeight", {"data": normal_height})
            result["body_height_code"] = response_code(response)
            self.task_manager.append_log(
                f"前跳前恢复 BodyHeight target={normal_height:.3f}, code={result['body_height_code']}"
            )
            await asyncio.sleep(0.6)

            response = await sport_call(conn, "FrontJump")
            result["front_jump_code"] = response_code(response)
            result["front_jump_data"] = response_data(response)
            self.task_manager.append_log(
                f"FrontJump code={result['front_jump_code']}, data={result['front_jump_data']!r}"
            )
            await asyncio.sleep(1.5)

            try:
                response = await sport_call(conn, "StopMove")
                result["stop_move_code"] = response_code(response)
                self.task_manager.append_log(f"前跳后 StopMove code={result['stop_move_code']}")
            except Exception as exc:
                self.task_manager.append_log(f"前跳后 StopMove 跳过: {exc}")

            return result
        finally:
            try:
                await conn.disconnect()
            except Exception:
                pass


action_manager = ActionManager(manager)


class VideoStreamManager:
    def __init__(self, task_manager):
        self.task_manager = task_manager
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.thread = None
        self.capture = None
        self.running = False
        self.connected = False
        self.stop_flag = False
        self.error = None
        self.started_at = None
        self.last_frame_at = None
        self.frame_count = 0
        self.width = None
        self.height = None
        self.latest_jpeg = None
        self.iface = None
        self.params = DEFAULT_PARAMS.copy()

    def snapshot(self):
        with self.lock:
            age = None
            if self.last_frame_at is not None:
                age = round(time.time() - self.last_frame_at, 2)
            return {
                "running": self.running,
                "connected": self.connected,
                "error": self.error,
                "started_at": self.started_at,
                "last_frame_at": self.last_frame_at,
                "frame_age": age,
                "frame_count": self.frame_count,
                "width": self.width,
                "height": self.height,
                "iface": self.iface,
            }

    def start(self, params):
        with self.lock:
            if self.running:
                raise RuntimeError("视频流已经在运行")
            self.params = {key: str(params.get(key, value)) for key, value in DEFAULT_PARAMS.items()}
            self.running = True
            self.connected = False
            self.stop_flag = False
            self.error = None
            self.started_at = time.time()
            self.last_frame_at = None
            self.frame_count = 0
            self.width = None
            self.height = None
            self.latest_jpeg = None
            self.iface = None

        self.task_manager.append_log("启动 Go2 视频流")
        self.thread = threading.Thread(target=self._thread_main, daemon=True)
        self.thread.start()

    def stop(self):
        with self.lock:
            self.stop_flag = True
            self.condition.notify_all()
        self.task_manager.append_log("请求停止 Go2 视频流")

    def get_latest_jpeg(self, timeout=2.0, after_frame_at=None):
        deadline = time.time() + timeout
        with self.condition:
            while self.running and time.time() < deadline:
                has_frame = self.latest_jpeg is not None
                is_new = after_frame_at is None or self.last_frame_at != after_frame_at
                if has_frame and is_new:
                    return self.latest_jpeg, self.last_frame_at
                self.condition.wait(timeout=max(0.05, deadline - time.time()))
            if self.latest_jpeg is not None and after_frame_at is None:
                return self.latest_jpeg, self.last_frame_at
            return None, after_frame_at

    def _thread_main(self):
        try:
            self._run()
        except Exception as exc:
            with self.condition:
                self.error = str(exc)
                self.condition.notify_all()
            self.task_manager.append_log(f"视频流异常: {exc}")
        finally:
            with self.condition:
                self.running = False
                self.connected = False
                self.capture = None
                self.condition.notify_all()
            self.task_manager.append_log("视频流已停止")

    def _run(self):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("缺少 OpenCV，请安装支持 GStreamer 的 python3-opencv") from exc

        with self.lock:
            robot_ip = self.params["UNITREE_ROBOT_IP"].strip()
            configured_iface = self.params["VIDEO_MULTICAST_IFACE"].strip()
            iface = configured_iface
            if not iface or iface.lower() == "auto":
                iface = detect_route_iface(robot_ip)
                if not iface:
                    raise RuntimeError(
                        f"无法根据 Go2 IP {robot_ip} 自动识别视频组播网卡，"
                        "请手动填写视频组播网卡"
                    )
            address = self.params["VIDEO_MULTICAST_ADDRESS"].strip() or "230.1.1.1"
            port = int(float(self.params["VIDEO_MULTICAST_PORT"]))
            self.iface = iface

        pipeline = (
            f"udpsrc address={address} port={port} multicast-iface={iface} "
            "! application/x-rtp, media=video, encoding-name=H264 "
            "! rtph264depay ! h264parse ! avdec_h264 ! videoconvert "
            "! video/x-raw,width=1280,height=720,format=BGR ! appsink drop=1 sync=false"
        )
        self.task_manager.append_log(f"视频流打开 H264 组播: {address}:{port} iface={iface}")

        capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        with self.lock:
            self.capture = capture

        if not capture.isOpened():
            raise RuntimeError(
                "无法打开 Go2 H264 组播视频。请确认网卡名正确、Go2 视频组播可达，"
                "并且当前 OpenCV 支持 GStreamer。"
            )

        try:
            with self.condition:
                self.connected = True
                self.condition.notify_all()

            while True:
                with self.lock:
                    if self.stop_flag:
                        break
                ok, image = capture.read()
                if not ok:
                    time.sleep(0.02)
                    continue
                ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
                if not ok:
                    continue
                jpeg = encoded.tobytes()
                height, width = image.shape[:2]
                with self.condition:
                    self.latest_jpeg = jpeg
                    self.width = int(width)
                    self.height = int(height)
                    self.frame_count += 1
                    self.last_frame_at = time.time()
                    self.condition.notify_all()
        finally:
            capture.release()


video_stream = VideoStreamManager(manager)


class Handler(BaseHTTPRequestHandler):
    server_version = "Go2HeightControlUI/1.0"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            data = manager.snapshot()
            data["keyboard"] = keyboard.snapshot()
            data["motion_mode"] = motion_mode.snapshot()
            data["action"] = action_manager.snapshot()
            data["video"] = video_stream.snapshot()
            self.write_json(data)
            return

        if parsed.path == "/api/video/stream":
            self.write_mjpeg_stream()
            return

        path = parsed.path
        if path == "/":
            path = "/index.html"

        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", MIME_TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/run":
                manager.start(payload.get("task", ""), payload.get("params", {}))
                self.write_json({"ok": True})
                return

            if parsed.path == "/api/stop":
                manager.stop_current()
                keyboard.stop()
                video_stream.stop()
                self.write_json({"ok": True})
                return

            if parsed.path == "/api/keyboard/start":
                keyboard.start(payload.get("params", {}))
                self.write_json({"ok": True})
                return

            if parsed.path == "/api/motion/normal":
                motion_mode.switch_normal(payload.get("params", {}))
                self.write_json({"ok": True})
                return

            if parsed.path == "/api/action/front_jump":
                action_manager.front_jump(payload.get("params", {}))
                self.write_json({"ok": True})
                return

            if parsed.path == "/api/keyboard/input":
                keyboard.update_axes(payload.get("axes", {}))
                self.write_json({"ok": True})
                return

            if parsed.path == "/api/keyboard/height":
                direction = int(payload.get("direction", 0))
                if direction not in (-1, 1):
                    raise ValueError("direction must be -1 or 1")
                result = keyboard.adjust_height(direction)
                self.write_json({"ok": True, **result})
                return

            if parsed.path == "/api/keyboard/height_target":
                result = keyboard.set_height_target(payload.get("height"))
                self.write_json({"ok": True, **result})
                return

            if parsed.path == "/api/keyboard/stop":
                keyboard.stop()
                self.write_json({"ok": True})
                return

            if parsed.path == "/api/video/start":
                video_stream.start(payload.get("params", {}))
                self.write_json({"ok": True})
                return

            if parsed.path == "/api/video/stop":
                video_stream.stop()
                self.write_json({"ok": True})
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.write_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def write_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_mjpeg_stream(self):
        boundary = "go2frame"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={boundary}")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()

        try:
            last_frame_at = None
            while True:
                frame, last_frame_at = video_stream.get_latest_jpeg(timeout=3.0, after_frame_at=last_frame_at)
                if frame is None:
                    if not video_stream.snapshot()["running"]:
                        break
                    continue
                self.wfile.write(f"--{boundary}\r\n".encode("ascii"))
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return


def main():
    if not LEGACY_DIR.exists():
        raise SystemExit(f"找不到控制脚本目录: {LEGACY_DIR}")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Go2 高度控制界面已启动: http://{HOST}:{PORT}")
    print("按 Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        manager.stop_current()
        keyboard.stop()
        video_stream.stop()
        print("\n服务已退出")


if __name__ == "__main__":
    main()
