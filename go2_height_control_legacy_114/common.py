import asyncio
import json
import logging
import os

from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD


logging.basicConfig(level=logging.FATAL)

ROBOT_IP = os.environ.get("UNITREE_ROBOT_IP", "192.168.12.137")
LOW_BODY_HEIGHT = float(os.environ.get("LOW_BODY_HEIGHT", "-0.13"))
NORMAL_BODY_HEIGHT = float(os.environ.get("NORMAL_BODY_HEIGHT", "0.0"))
CRAWL_DISTANCE_M = float(os.environ.get("CRAWL_DISTANCE_M", "2.0"))
CRAWL_SPEED_MPS = float(os.environ.get("CRAWL_SPEED_MPS", "0.20"))
MOVE_COMMAND_PERIOD_S = float(os.environ.get("MOVE_COMMAND_PERIOD_S", "0.10"))

REMOTE_FORWARD_LY = float(os.environ.get("REMOTE_FORWARD_LY", "0.45"))
ESTIMATED_SPEED_MPS = float(os.environ.get("ESTIMATED_SPEED_MPS", "0.20"))
REMOTE_PUBLISH_PERIOD_S = float(os.environ.get("REMOTE_PUBLISH_PERIOD_S", "0.02"))


def response_code(response):
    return response.get("data", {}).get("header", {}).get("status", {}).get("code")


def response_data(response):
    return response.get("data", {}).get("data", "")


def require_ok(response, action):
    code = response_code(response)
    if code != 0:
        raise RuntimeError(f"{action} failed, response code={code}, data={response_data(response)!r}")


def make_connection():
    return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=ROBOT_IP)


async def sport_call(conn, command, parameter=None):
    payload = {"api_id": SPORT_CMD[command]}
    if parameter is not None:
        payload["parameter"] = parameter
    return await conn.datachannel.pub_sub.publish_request_new(RTC_TOPIC["SPORT_MOD"], payload)


async def try_get_motion_mode(conn):
    try:
        response = await conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["MOTION_SWITCHER"],
            {"api_id": 1001},
        )
        data = response_data(response)
        if not data:
            return None, response
        return json.loads(data).get("name"), response
    except Exception as exc:
        print(f"Motion switcher check skipped: {exc}")
        return None, None


async def try_set_normal_mode(conn):
    current_mode, _response = await try_get_motion_mode(conn)
    print(f"Motion mode: {current_mode or 'unknown'}")

    if current_mode and current_mode != "normal":
        response = await conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["MOTION_SWITCHER"],
            {"api_id": 1002, "parameter": {"name": "normal"}},
        )
        print(f"Switch normal response code: {response_code(response)}")
        await asyncio.sleep(5.0)


async def try_get_body_height(conn, label):
    try:
        response = await sport_call(conn, "GetBodyHeight")
        print(
            f"{label} GetBodyHeight response code: {response_code(response)}, "
            f"data: {response_data(response)!r}"
        )
        return response
    except Exception as exc:
        print(f"{label} GetBodyHeight skipped: {exc}")
        return None


async def balance_stand(conn):
    print("BalanceStand...")
    response = await sport_call(conn, "BalanceStand")
    print(f"BalanceStand response code: {response_code(response)}")
    require_ok(response, "BalanceStand")
    await asyncio.sleep(1.0)


async def set_body_height(conn, height, label="BodyHeight"):
    print(f"{label}: {height:.3f} m...")
    response = await sport_call(conn, "BodyHeight", {"data": height})
    print(f"{label} response code: {response_code(response)}, data: {response_data(response)!r}")
    require_ok(response, label)
    return response


async def stop_and_restore(conn):
    try:
        await sport_call(conn, "StopMove")
        await asyncio.sleep(0.2)
    finally:
        await sport_call(conn, "BodyHeight", {"data": NORMAL_BODY_HEIGHT})
        await asyncio.sleep(0.2)


async def move_for_duration(conn, vx, vy, vyaw, duration):
    deadline = asyncio.get_running_loop().time() + duration
    next_report = 0.0

    while True:
        now = asyncio.get_running_loop().time()
        remaining = deadline - now
        if remaining <= 0:
            break

        response = await sport_call(conn, "Move", {"x": vx, "y": vy, "z": vyaw})
        code = response_code(response)
        if code != 0:
            raise RuntimeError(f"Move failed, response code={code}, data={response_data(response)!r}")

        elapsed = duration - remaining
        if elapsed >= next_report:
            print(f"  moving... {elapsed:.1f}/{duration:.1f}s")
            next_report += 1.0

        await asyncio.sleep(min(MOVE_COMMAND_PERIOD_S, remaining))


def publish_remote(pub_sub, lx=0.0, ly=0.0, rx=0.0, ry=0.0, keys=0):
    pub_sub.publish_without_callback(
        RTC_TOPIC["WIRELESS_CONTROLLER"],
        {"lx": lx, "ly": ly, "rx": rx, "ry": ry, "keys": keys},
    )


async def remote_forward_for_duration(conn, duration):
    pub_sub = conn.datachannel.pub_sub
    deadline = asyncio.get_running_loop().time() + duration
    next_report = 0.0

    while True:
        now = asyncio.get_running_loop().time()
        remaining = deadline - now
        if remaining <= 0:
            break

        publish_remote(pub_sub, ly=REMOTE_FORWARD_LY)

        elapsed = duration - remaining
        if elapsed >= next_report:
            print(f"  remote forward... {elapsed:.1f}/{duration:.1f}s ly={REMOTE_FORWARD_LY:.2f}")
            next_report += 1.0

        await asyncio.sleep(min(REMOTE_PUBLISH_PERIOD_S, remaining))

    publish_remote(pub_sub)
