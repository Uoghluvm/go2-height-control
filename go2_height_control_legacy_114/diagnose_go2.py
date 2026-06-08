import asyncio
import sys

from common import (
    LOW_BODY_HEIGHT,
    NORMAL_BODY_HEIGHT,
    ROBOT_IP,
    balance_stand,
    make_connection,
    response_code,
    set_body_height,
    sport_call,
    try_get_body_height,
    try_get_motion_mode,
)


async def main():
    conn = make_connection()
    connected = False
    try:
        print("Go2 低姿态控制诊断")
        print("====================")
        print(f"Robot IP: {ROBOT_IP}")
        print(f"Configured low height: {LOW_BODY_HEIGHT}")
        print(f"Configured normal height: {NORMAL_BODY_HEIGHT}")

        await conn.connect()
        connected = True

        mode, response = await try_get_motion_mode(conn)
        print(f"Motion mode: {mode or 'unknown'}")
        if response is not None:
            print(f"Motion mode response code: {response_code(response)}")

        await try_get_body_height(conn, "Current")

        print("Testing BalanceStand...")
        await balance_stand(conn)

        print("Testing BodyHeight with a small safe value -0.05...")
        await set_body_height(conn, -0.05, "Test BodyHeight")
        await asyncio.sleep(1.0)
        await try_get_body_height(conn, "After test")

        print("Restoring height...")
        await set_body_height(conn, NORMAL_BODY_HEIGHT, "Restore BodyHeight")
        await asyncio.sleep(0.5)
        await try_get_body_height(conn, "After restore")

        print("诊断完成：如果以上 response code 均为 0，则当前固件支持 BodyHeight。")

    finally:
        if connected:
            try:
                await sport_call(conn, "StopMove")
                await asyncio.sleep(0.2)
                await sport_call(conn, "BodyHeight", {"data": NORMAL_BODY_HEIGHT})
                await asyncio.sleep(0.2)
            finally:
                await conn.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
        sys.exit(0)
