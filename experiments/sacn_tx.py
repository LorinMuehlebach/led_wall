import sacn
import time
import ctypes
import socket

# send changing packets 0 - 255 to a defined dmx channel in a defined universe. on ctrl - c exit

FRAMERATE = 30
DMX_CHANNEL = 1
UNIVERSE = 1
SLEEP_THRESHOLD = 0.005  # spin-wait the last 5 ms for sub-ms accuracy


def _set_timer_resolution():
    """Request 1 ms Windows timer resolution."""
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass


def _restore_timer_resolution():
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


def main():
    print(f"Starting sACN sender on Universe {UNIVERSE}, Channel {DMX_CHANNEL} at {FRAMERATE} FPS")

    #local_ip = socket.gethostbyname(socket.gethostname())
    #print(f"Binding sender to {local_ip}")
    sender = sacn.sACNsender(fps=FRAMERATE)
    sender.start()

    sender.activate_output(UNIVERSE)
    sender[UNIVERSE].multicast = True

    dmx_data = [0] * 512
    val = 0
    clock = time.perf_counter
    frame_period = 1.0 / FRAMERATE

    frames_sent = 0
    actual_period_sum = 0.0
    last_tick = clock()
    last_log_time = clock()

    _set_timer_resolution()
    try:
        while True:
            tick_start = clock()

            dmx_data[DMX_CHANNEL - 1] = val
            #dmx_data = [val] * 512
            sender[UNIVERSE].dmx_data = tuple(dmx_data)
            val = (val + 5) % 256

            # Sleep coarse part, then spin-wait the tail
            deadline = tick_start + frame_period
            remaining = deadline - clock()
            if remaining > SLEEP_THRESHOLD:
                time.sleep(remaining - SLEEP_THRESHOLD)
            while clock() < deadline:
                pass

            now = clock()
            actual_period_sum += now - last_tick
            last_tick = now
            frames_sent += 1
            if now - last_log_time >= 1.0:
                avg_period = actual_period_sum / frames_sent
                print(f"TX: {1/avg_period:.1f} fps (target {FRAMERATE})")
                frames_sent = 0
                actual_period_sum = 0.0
                last_log_time = now

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        _restore_timer_resolution()
        sender.stop()


if __name__ == "__main__":
    main()
