import sacn
import time

# send changing packets 0 - 255 to a defined dmx channel in a defined universe. on ctrl - c exit

FRAMERATE = 10
DMX_CHANNEL = 1
UNIVERSE = 1

def main():
    print(f"Starting sACN sender on Universe {UNIVERSE}, Channel {DMX_CHANNEL} at {FRAMERATE} FPS")
    
    # Initialize sender
    sender = sacn.sACNsender(fps=FRAMERATE)
    sender.start()
    
    # Activate the universe
    sender.activate_output(UNIVERSE)
    sender[UNIVERSE].multicast = True  # send via multicast
    
    # Initialize DMX data array (512 channels)
    dmx_data = [0] * 512
    
    val = 0
    frames_sent = 0
    last_log_time = time.time()
    
    try:
        while True:
            # Set the channel value (0-indexed array for 1-based DMX channel)
            if 1 <= DMX_CHANNEL <= 512:
                dmx_data[DMX_CHANNEL - 1] = val
            
            dmx_data[DMX_CHANNEL] = 255
            # Update the universe data
            sender[UNIVERSE].dmx_data = tuple(dmx_data)
            
            frames_sent += 1
            current_time = time.time()
            if current_time - last_log_time >= 1.0:
                fps = frames_sent / (current_time - last_log_time)
                print(f"FPS: {fps:.2f}")
                frames_sent = 0
                last_log_time = current_time

            # Update value for next frame (0-255 loop)
            val = (val + 10) % 256
            
            # Sleep to maintain framerate
            time.sleep(1.0 / FRAMERATE)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        sender.stop()

if __name__ == "__main__":
    main()