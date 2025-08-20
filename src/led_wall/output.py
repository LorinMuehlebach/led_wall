
import asyncio
from pyartnet import ArtNetNode

from led_wall.pixels import LedPixelArray, LedPixel

class H807SA():
    """
    H807SA LED Wall Controller using ArtNet
    This class provides methods to set up the LED wall and send pixel data using ArtNet.
    It uses the pyartnet library to communicate with the ArtNet node.
    """
    def __init__(self, ip: str, port: int = 6454):
        self.node = ArtNetNode(ip, port)
        self.universes = []
        self.channels = []

    def setup(self,height:int=80, width:int=36, output_correction=None) -> None:
        START_ID = 1
        CHANNELS_PER_PIXEL = 4  # RGBW

        self.height = height
        self.width = width

        for i in range(width):
            self.universes.append(self.node.add_universe(i))
            self.channels.append(self.universes[i].add_channel(start=START_ID, width=CHANNELS_PER_PIXEL*height))

    def set_outputs(self, data:list[list[int]]) -> None:
        """Set the output data for all channels.

        TODO: data write is done automatically by the ArtNetNode, revisit this for syncronous updates.
        
        Args:
            data (list[list[int]]): A list of lists, where each inner list corresponds to led strips data and the outer list corresponds to each led strip.
        """
        if len(data) != len(self.channels):
            raise ValueError("Data length must match number of channels")

        for i, channel in enumerate(self.channels):
            #if len(data[i]) != channel.width:
            #    raise ValueError(f"Data for channel {i} does not match expected width")
            channel.set_values(data[i])



