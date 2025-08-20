import asyncio
from pyartnet import ArtNetNode

from led_wall.pixels import LedPixelArray, LedPixel


def gamma(val: float, max_val: int = 0xFF) -> float:
    """gamma output correction"""
    gamma_value = 2 # 2.2
    return min((val ** gamma_value) / max_val,255)  # Ensure the value does not exceed 255

async def update_loop(PixelArray:list[LedPixelArray]=None):
    # Run this code in your async function
    node = ArtNetNode('192.168.178.100', 6454)

    # Create universe 0
    universes = []
    channels = []
    for i in range(len(PixelArray)):
        universes.append(node.add_universe(i))
        #universes[i].set_output_correction(gamma)

        #setup pixel arrays
        pixel_length = PixelArray[i].channels_per_pixel()
        num_pixels = len(PixelArray[i])

        channels.append(universes[i].add_channel(start=1, width=pixel_length*num_pixels))

    fade = 0
    
    while True:
        set_all_same(PixelArray,2,0,0,0)
        fade = (fade + 2) % 256

        #at least one pixel need to change such that the channel is updated

        PixelArray[0].pixels[100].setColor(0, 0, fade, 0)  # Set pixel 100 to green with fade effect
        for i in range(len(PixelArray)):
            channels[i].set_values(PixelArray[i].to_data_list())
        await asyncio.sleep(0.02)  # 50 FPS


PixelArray1 = LedPixelArray(120, order="rgbw")
PixelArray1.set_all_pixels_color(0, 125, 0, 0)  # Set all pixels to red

PixelArray2 = LedPixelArray(120, order="rgbw")
PixelArray2.set_all_pixels_color(0, 125, 0, 0)  # Set all pixels to red

PixelArray3 = LedPixelArray(120, order="rgbw")
PixelArray3.set_all_pixels_color(0, 0, 125, 0)  # Set all pixels to red

PixelArray4 = LedPixelArray(120, order="rgbw")
PixelArray4.set_all_pixels_color(0, 0, 125, 0)  # Set all pixels to red


def set_all_same(list,r,g,b,w):
    for e in list:
        e.set_all_pixels_color(r, g, b, w)


def set_all_same_height(list,switch,r,g,b,w,r2,g2,b2,w2):
    for e in list:
        for i,p in enumerate(e.pixels):
            if i < switch:
                p.setColor(r, g, b, w)
            else:
                p.setColor(r2, g2, b2, w2)

async def color_update(PixelArray:LedPixelArray=None):
    last_color = 0  # Initial color
    last_state = 0
    while True:
        
        #last_color = (last_color+1) % 255
        last_state = (last_state + 1) % 2
        PixelArray.set_all_pixels_color(0, 0, 0, 255*last_state)  
        
        await asyncio.sleep(1/30)


arrays = [PixelArray1,PixelArray2]

set_all_same(arrays,25,0,0,0)
#set_all_same_height(arrays,30,0,125,0,0,0,0,125,0)

async def main():
    await asyncio.gather(
        update_loop(arrays),
        #color_update(PixelArray2)
    )

asyncio.run(main())