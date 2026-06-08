import asyncio
import sys

from common import (
    CRAWL_DISTANCE_M,
    CRAWL_SPEED_MPS,
    LOW_BODY_HEIGHT,
    MOVE_COMMAND_PERIOD_S,
    NORMAL_BODY_HEIGHT,
    ROBOT_IP,
    balance_stand,
    make_connection,
    move_for_duration,
    set_body_height,
    stop_and_restore,
    try_get_body_height,
    try_set_normal_mode,
    sport_call,
    response_code,
)


async def main():
    if CRAWL_SPEED_MPS <= 0:
        raise ValueError("CRAWL_SPEED_MPS must be positive")

    conn = make_connection()
    connected = False

    try:
        print(f"Connecting to Go2 firmware 1.1.4 at {ROBOT_IP}...")
        await conn.connect()
        connected = True

        await try_set_normal_mode(conn)
        await try_get_body_height(conn, "Before")
        await balance_stand(conn)

        await set_body_height(conn, LOW_BODY_HEIGHT, "Lower BodyHeight")
        await asyncio.sleep(2.0)
        await try_get_body_height(conn, "After lowering")

        duration = CRAWL_DISTANCE_M / CRAWL_SPEED_MPS
        print(
            f"Crawling forward about {CRAWL_DISTANCE_M:.2f} m "
            f"at {CRAWL_SPEED_MPS:.2f} m/s for {duration:.1f} s "
            f"(Move every {MOVE_COMMAND_PERIOD_S:.2f} s)..."
        )
        await move_for_duration(conn, CRAWL_SPEED_MPS, 0.0, 0.0, duration)

        print("Stopping...")
        response = await sport_call(conn, "StopMove")
        print(f"StopMove response code: {response_code(response)}")
        await asyncio.sleep(0.5)

        await set_body_height(conn, NORMAL_BODY_HEIGHT, "Restore BodyHeight")
        await asyncio.sleep(1.0)
        await try_get_body_height(conn, "After restore")
        print("Done.")

    finally:
        if connected:
            await stop_and_restore(conn)
            await conn.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
        sys.exit(0)
