import asyncio
import sys

from common import NORMAL_BODY_HEIGHT, ROBOT_IP, make_connection, set_body_height, sport_call, response_code


async def main():
    conn = make_connection()
    connected = False
    try:
        print(f"Connecting to Go2 at {ROBOT_IP}...")
        await conn.connect()
        connected = True

        print("StopMove...")
        response = await sport_call(conn, "StopMove")
        print(f"StopMove response code: {response_code(response)}")
        await asyncio.sleep(0.5)

        await set_body_height(conn, NORMAL_BODY_HEIGHT, "Restore BodyHeight")
        print("Restored.")
    finally:
        if connected:
            await conn.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
        sys.exit(0)
