import sacn
import time

# provide an IP-Address to bind to if you want to receive multicast packets from a specific interface
receiver = sacn.sACNreceiver()
receiver.start()  # start the receiving thread

# define a callback function
@receiver.listen_on('universe', universe=1)  # listens on universe 1
def callback(packet:sacn.DataPacket):  # packet type: sacn.DataPacket
    if packet.dmxStartCode == 0x00:  # ignore non-DMX-data packets
        current_time = time.time()
        if hasattr(callback, 'last_time'):
            delta = current_time - callback.last_time
            if delta > 0:
                fps = 1 / delta
                print(f"FPS: {fps:.2f}")
        callback.last_time = current_time

        #print(packet.dmxData)  # print the received DMX data

# optional: if multicast is desired, join with the universe number as parameter
receiver.join_multicast(1)

time.sleep(60)  # receive for 10 seconds

# optional: if multicast was previously joined
receiver.leave_multicast(1)

receiver.stop()