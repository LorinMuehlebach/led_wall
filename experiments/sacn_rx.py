import sacn
import time
import socket

local_ip = socket.gethostbyname(socket.gethostname())
print(f"Binding receiver to {local_ip}")

receiver = sacn.sACNreceiver(bind_address=local_ip)

frame_count = 0
last_seq = None
dropped = 0
last_log = time.time()

@receiver.listen_on('universe', universe=1)
def callback(packet: sacn.DataPacket):
    global frame_count, last_seq, dropped, last_log

    frame_count += 1

    seq = packet.sequence
    if last_seq is not None:
        gap = (seq - last_seq) % 256
        if gap > 1:
            dropped += gap - 1
    last_seq = seq

    now = time.time()
    elapsed = now - last_log
    if elapsed >= 1.0:
        fps = frame_count / elapsed
        print(f"FPS: {fps:.1f} | dropped: {dropped}")
        frame_count = 0
        dropped = 0
        last_log = now

receiver.start()
receiver.join_multicast(1)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

receiver.leave_multicast(1)
receiver.stop()
