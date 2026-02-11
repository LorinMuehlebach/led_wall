import python_artnet as Artnet

# By default it will listen on 0.0.0.0 (all interfaces)
artNet = Artnet.Artnet()

# Fetch the latest packet we received from universe 0.
artNetPacket = artNet.readBuffer()[2]
# And extract the DMX data from that packet.
dmxPacket = artNetPacket.data
# You'll also want to check that there *is* data in the packet;
# if there isn't then it returns None
# See the example for more information
print(dmxPacket)

# Close the listener nicely :)
artNet.close()