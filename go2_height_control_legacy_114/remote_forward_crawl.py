import asyncio
import sys

from common import (
    CRAWL_DISTANCE_M,
    ESTIMATED_SPEED_MPS,
    LOW_BODY_HEIGHT,
    NORMAL_BODY_HEIGHT,
    REMOTE_FORWARD_LY,
    REMOTE_PUBLISH_PERIOD_S,
    ROBOT_IP,
    balance_stand,
    make_connection,
    publish_remote,
    remote_forward_for_duration,
    set_body_height,
    stop_and_restore,
    try_set_normal_mode,
    sport_call,
    response_code,
)


async def main():
    if ESTIMATED_SPEED_MPS <= 0:
        raise ValueError("ESTIMATED_SPEED_MPS must be positive")

    conn = make_connection()
    connected = False

    try:
        print(f"Connecting to Go2 firmware 1.1.4 at {ROBOT_IP}...")
        await conn.connect()
        connected = True

        await try_set_normal_mode(conn)
        await balance_stand(conn)

        await set_body_height(conn, LOW_BODY_HEIGHT, "Lower BodyHeight")
        await asyncio.sleep(2.0)

        duration = CRAWL_DISTANCE_M / ESTIMATED_SPEED_MPS
        print(
            f"Remote-style forward about {CRAWL_DISTANCE_M:.2f} m for {duration:.1f} s "
            f"(ly={REMOTE_FORWARD_LY:.2f}, publish every {REMOTE_PUBLISH_PERIOD_S:.2f} s)..."
        )
        await remote_forward_for_duration(conn, duration)

        print("Stopping...")
        publish_remote(conn.datachannel.pub_sub)
        response = await sport_call(conn, "StopMove")
        print(f"StopMove response code: {response_code(response)}")
        await asyncio.sleep(0.5)

        await set_body_height(conn, NORMAL_BODY_HEIGHT, "Restore BodyHeight")
        await asyncio.sleep(1.0)
        print("Done.")

    finally:
        if connected:
            publish_remote(conn.datachannel.pub_sub)
            await stop_and_restore(conn)
            await conn.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
        sys.exit(0)
