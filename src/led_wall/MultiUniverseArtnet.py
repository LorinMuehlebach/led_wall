"""(Very) Simple Implementation of Artnet.

Python Version: 3.6
Source: http://artisticlicence.com/WebSiteMaster/User%20Guides/art-net.pdf

NOTES
- For simplicity: NET and SUBNET not used by default but optional

"""

import socket
import _thread
from time import sleep, time
from stupidArtnet.ArtnetUtils import shift_this, put_in_range


class StupidArtnet():
    """(Very) simple implementation of Artnet."""

    def __init__(self, target_ip='127.0.0.1', universes=[0], packet_size=512, fps=30,
                 even_packet_size=True, broadcast=False, source_address=None, artsync=False, port=6454):
        """Initializes Art-Net Client.

        Args:
        targetIP - IP of receiving device
        universes - universes to listen
        packet_size - amount of channels to transmit
        fps - transmition rate
        even_packet_size - Some receivers enforce even packets
        broadcast - whether to broadcast in local sub
        artsync - if we want to synchronize buffer
        port - UDP port used to send Art-Net packets (default: 6454)

        Returns:
        None

        """
        # Instance variables
        self.target_ip = target_ip
        self.universes = universes if isinstance(universes, (list, tuple, range)) else [universes]
        self.sequences = {u: 0 for u in self.universes}
        self.physical = 0

        self.subnet = 0
        self.if_sync = artsync
        self.net = 0
        self.packet_size = put_in_range(packet_size, 2, 512, even_packet_size)
        
        self.universe_buffer = {u: bytearray(self.packet_size) for u in self.universes}
        self.last_sent_buffer = {u: bytearray(self.packet_size) for u in self.universes}
        self.last_send_time = {u: 0.0 for u in self.universes}
        self.port = port  
        # Use provided port or default 6454
        # By default, the server uses port 6454, no need to specify it.
        # If you need to change the Art-Net port, ensure the port is within the valid range for UDP ports (1024-65535).
        # Be sure that no other application is using the selected port on your network.

        self.make_even = even_packet_size

        self.is_simplified = True		# simplify use of universe, net and subnet

        # UDP SOCKET
        self.socket_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        if broadcast:
            self.socket_client.setsockopt(
                socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Allow speciying the origin interface
        if source_address:
            self.socket_client.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket_client.bind(source_address)

        # Timer
        self.fps = fps
        self.__clock = None

        if self.if_sync:
            self.artsync_header = bytearray()
            self.make_artsync_header()


    def __del__(self):
        """Graceful shutdown."""
        self.stop()
        self.close()


    def __str__(self):
        """Printable object state."""
        state = "===================================\n"
        state += "Stupid Artnet initialized\n"
        state += f"Target IP: {self.target_ip} : {self.port} \n"
        state += f"Universes: {self.universes} \n"
        if not self.is_simplified:
            state += f"Subnet: {self.subnet} \n"
            state += f"Net: {self.net} \n"
        state += f"Packet Size: {self.packet_size} \n"
        state += "==================================="

        return state


    def make_artdmx_header(self, universe):
        """Make packet header."""
        # 0 - id (7 x bytes + Null)
        header = bytearray()
        header.extend(bytearray('Art-Net', 'utf8'))
        header.append(0x0)
        # 8 - opcode (2 x 8 low byte first)
        header.append(0x00)
        header.append(0x50)  # ArtDmx data packet
        # 10 - prototocol version (2 x 8 high byte first)
        header.append(0x0)
        header.append(14)
        # 12 - sequence (int 8), NULL for not implemented
        header.append(self.sequences[universe])
        # 13 - physical port (int 8)
        header.append(0x00)
        # 14 - universe, (2 x 8 low byte first)
        if self.is_simplified:
            # not quite correct but good enough for most cases:
            # the whole net subnet is simplified
            # by transforming a single uint16 into its 8 bit parts
            # you will most likely not see any differences in small networks
            msb, lsb = shift_this(universe)   # convert to MSB / LSB
            header.append(lsb)
            header.append(msb)
        # 14 - universe, subnet (2 x 4 bits each)
        # 15 - net (7 bit value)
        else:
            # as specified in Artnet 4 (remember to set the value manually after):
            # Bit 3  - 0 = Universe (1-16)
            # Bit 7  - 4 = Subnet (1-16)
            # Bit 14 - 8 = Net (1-128)
            # Bit 15     = 0
            # this means 16 * 16 * 128 = 32768 universes per port
            # a subnet is a group of 16 Universes
            # 16 subnets will make a net, there are 128 of them
            header.append(self.subnet << 4 | universe)
            header.append(self.net & 0xFF)
        # 16 - packet size (2 x 8 high byte first)
        msb, lsb = shift_this(self.packet_size)		# convert to MSB / LSB
        header.append(msb)
        header.append(lsb)
        return header


    def make_artsync_header(self):
        """Make ArtSync header"""
        self.artsync_header = bytearray()  # Initialize as empty bytearray
        # ID: Array of 8 characters, the final character is a null termination.
        self.artsync_header.extend(bytearray('Art-Net', 'utf8'))
        self.artsync_header.append(0x0)
        # OpCode: Defines the class of data within this UDP packet. Transmitted low byte first.
        self.artsync_header.append(0x00)
        self.artsync_header.append(0x52)
        # ProtVerHi and ProtVerLo: Art-Net protocol revision number. Current value =14.
        # Controllers should ignore communication with nodes using a protocol version lower than =14.
        self.artsync_header.append(0x0)
        self.artsync_header.append(14)
        # Aux1 and Aux2: Should be transmitted as zero.
        self.artsync_header.append(0x0)
        self.artsync_header.append(0x0)


    def send_artsync(self):
        """Send Artsync"""
        self.make_artsync_header()
        try:
            self.socket_client.sendto(self.artsync_header, (self.target_ip, self.port))
        except socket.error as error:
            print(f"ERROR: Socket error with exception: {error}")


    def show(self):
        """Finally send data."""
        current_time = time()
        for u in self.universes:
            # Check if data has changed or if it's been more than a second since the last update
            if self.universe_buffer[u] != self.last_sent_buffer[u] or (current_time - self.last_send_time[u]) > 1.0:
                header = self.make_artdmx_header(u)
                packet = bytearray()
                packet.extend(header)
                packet.extend(self.universe_buffer[u])
                try:
                    self.socket_client.sendto(packet, (self.target_ip, self.port))
                    self.last_sent_buffer[u] = bytearray(self.universe_buffer[u])
                    self.last_send_time[u] = current_time
                except socket.error as error:
                    print(f"ERROR: Socket error with exception: {error}")
                finally:
                    self.sequences[u] = (self.sequences[u] + 1) % 256
        
        if self.if_sync:  # if we want to send artsync
            self.send_artsync()


    def close(self):
        """Close UDP socket."""
        self.socket_client.close()

    # THREADING #

    def start(self):
        """Starts thread clock."""
        self.show()
        if not hasattr(self, "running"):
            self.running = True
        if self.running:
            sleep((1000.0 / self.fps) / 1000.0)
            _thread.start_new_thread(self.start, ())


    def stop(self):
        """Set flag so thread will exit."""
        self.running = False

    # SETTERS - HEADER #

    def set_universe(self, universe):
        """Setter for universe (0 - 15 / 256).

        Mind if protocol has been simplified
        """
        # This is ugly, trying to keep interface easy
        # With simplified mode the universe will be split into two
        # values, (uni and sub) which is correct anyway. Net will always be 0
        
        # For multiple universes, this will reset the list to a single universe
        if self.is_simplified:
            u = put_in_range(universe, 0, 255, False)
        else:
            u = put_in_range(universe, 0, 15, False)
        
        self.universes = [u]
        self.universe_buffer = {u: bytearray(self.packet_size)}
        self.last_sent_buffer = {u: bytearray(self.packet_size)}
        self.last_send_time = {u: 0.0}
        self.sequences = {u: 0 for u in self.universes}


    def set_subnet(self, sub):
        """Setter for subnet address (0 - 15).

        Set simplify to false to use
        """
        self.subnet = put_in_range(sub, 0, 15, False)


    def set_net(self, net):
        """Setter for net address (0 - 127).

        Set simplify to false to use
        """
        self.net = put_in_range(net, 0, 127, False)


    def set_packet_size(self, packet_size):
        """Setter for packet size (2 - 512, even only)."""
        self.packet_size = put_in_range(packet_size, 2, 512, self.make_even)
        for u in self.universes:
            # Resize existing buffers
            new_buffer = bytearray(self.packet_size)
            old_buffer = self.universe_buffer.get(u, b'')
            length = min(len(old_buffer), self.packet_size)
            new_buffer[:length] = old_buffer[:length]
            self.universe_buffer[u] = new_buffer
            
            # Also resize last_sent_buffer
            new_last_sent = bytearray(self.packet_size)
            old_last_sent = self.last_sent_buffer.get(u, b'')
            length_last = min(len(old_last_sent), self.packet_size)
            new_last_sent[:length_last] = old_last_sent[:length_last]
            self.last_sent_buffer[u] = new_last_sent

    # SETTERS - DATA #

    def clear(self, universe=None):
        """Clear DMX buffer."""
        if universe is not None:
            self.universe_buffer[universe] = bytearray(self.packet_size)
        else:
            for u in self.universes:
                self.universe_buffer[u] = bytearray(self.packet_size)


    def set(self, value, universe=None):
        """Set buffer."""
        if universe is None:
            universe = self.universes[0]
            
        if len(value) != self.packet_size:
            print("ERROR: packet does not match declared packet size")
            return
        self.universe_buffer[universe] = bytearray(value) if isinstance(value, (list, bytes)) else value


    def set_16bit(self, address, value, high_first=False, universe=None):
        """Set single 16bit value in DMX buffer."""
        if universe is None:
            universe = self.universes[0]

        if address > self.packet_size:
            print("ERROR: Address given greater than defined packet size")
            return
        if address < 1 or address > 512 - 1:
            print("ERROR: Address out of range")
            return
        value = put_in_range(value, 0, 65535, False)

        # Check for endianess
        if high_first:
            self.universe_buffer[universe][address - 1] = (value >> 8) & 0xFF  # high
            self.universe_buffer[universe][address] = (value) & 0xFF 			# low
        else:
            self.universe_buffer[universe][address - 1] = (value) & 0xFF				# low
            self.universe_buffer[universe][address] = (value >> 8) & 0xFF  # high


    def set_single_value(self, address, value, universe=None):
        """Set single value in DMX buffer."""
        if universe is None:
            universe = self.universes[0]

        if address > self.packet_size:
            print("ERROR: Address given greater than defined packet size")
            return
        if address < 1 or address > 512:
            print("ERROR: Address out of range")
            return
        self.universe_buffer[universe][address - 1] = put_in_range(value, 0, 255, False)


    def set_single_rem(self, address, value, universe=None):
        """Set single value while blacking out others."""
        if universe is None:
            universe = self.universes[0]

        if address > self.packet_size:
            print("ERROR: Address given greater than defined packet size")
            return
        if address < 1 or address > 512:
            print("ERROR: Address out of range")
            return
        self.clear(universe)
        self.universe_buffer[universe][address - 1] = put_in_range(value, 0, 255, False)


    def set_rgb(self, address, red, green, blue, universe=None):
        """Set RGB from start address."""
        if universe is None:
            universe = self.universes[0]

        if address > self.packet_size:
            print("ERROR: Address given greater than defined packet size")
            return
        if address < 1 or address > 510:
            print("ERROR: Address out of range")
            return

        self.universe_buffer[universe][address - 1] = put_in_range(red, 0, 255, False)
        self.universe_buffer[universe][address] = put_in_range(green, 0, 255, False)
        self.universe_buffer[universe][address + 1] = put_in_range(blue, 0, 255, False)

    # AUX Function #

    def send(self, packet, universe=None):
        """Set buffer and send straightaway.

        Args:
        array - integer array to send
        """
        self.set(packet, universe)
        self.show()


    def set_simplified(self, simplify):
        """Builds Header accordingly.

        True - Header sends 16 bit universe value (OK but incorrect)
        False - Headers sends Universe - Net and Subnet values as protocol
        It is recommended that you set these values with .set_net() and set_physical
        """
        # avoid remaking header if there are no changes
        if simplify == self.is_simplified:
            return
        self.is_simplified = simplify


    def see_header(self, universe=None):
        """Show header values."""
        if universe is None:
            universe = self.universes[0]
        print(self.make_artdmx_header(universe))


    def see_buffer(self, universe=None):
        """Show buffer values."""
        if universe is None:
            for u in self.universes:
                print(f"Universe {u}: {self.universe_buffer[u]}")
        else:
            print(self.universe_buffer[universe])


    def blackout(self):
        """Sends 0's all across."""
        self.clear()
        self.show()


    def flash_all(self, delay=None):
        """Sends 255's all across."""
        for u in self.universes:
            self.set([255] * self.packet_size, universe=u)
        self.show()
        # Blackout after delay
        if delay:
            sleep(delay)
            self.blackout()


if __name__ == '__main__':
    print("===================================")
    print("Namespace run")
    TARGET_IP = '127.0.0.1'         # typically in 2.x or 10.x range
    UNIVERSES_TO_SEND = [3, 4, 5]    # see docs
    PACKET_SIZE = 20                # it is not necessary to send whole universe
    PORT = 6455                     # default Art-Net port

    a = StupidArtnet(TARGET_IP, UNIVERSES_TO_SEND, PACKET_SIZE, port=PORT, artsync=True)
    a.set_simplified(False)

    # Look at the object state
    print(a)

    a.set_single_value(3, 255, universe=3)
    a.set_single_value(4, 100, universe=4)
    a.set_single_value(5, 200, universe=5)

    print("Sending values")
    a.show()
    a.see_buffer()
    # a.flash_all()
    # a.see_buffer()
    # a.show()

    print("Values sent")

    # Cleanup when you are done
    del a
