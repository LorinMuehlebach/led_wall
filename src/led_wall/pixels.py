

class LedPixel():
    def __init__(self, r=0, g=0, b=0, w=0, order="rgbw"):
        self.r = r
        self.g = g
        self.b = b
        self.w = w

        self.order = order.lower()

    def as_bytes(self):
        if self.order == "rgbw":
            return bytes([self.r, self.g, self.b, self.w])
        elif self.order == "rgwb":
            return bytes([self.r, self.g, self.w, self.b])
        elif self.order == "rwgb":
            return bytes([self.r, self.w, self.g, self.b])
        elif self.order == "bgrw":
            return bytes([self.b, self.g, self.r, self.w])
        elif self.order == "bgwr":
            return bytes([self.b, self.g, self.w, self.r])
        elif self.order == "wbrg":
            return bytes([self.w, self.b, self.r, self.g])
        else:
            raise ValueError("Invalid order specified")
        
    def setColor(self, r, g, b, w):
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255 and 0 <= w <= 255):
            raise ValueError("Color values must be between 0 and 255")
        
        self.r = r
        self.g = g
        self.b = b
        self.w = w

    @staticmethod
    def to_data_list(led_pixels:list["LedPixel"]) -> list[int]:
        output = []
        for led in led_pixels:
            if not isinstance(led, LedPixel):
                raise TypeError("All elements must be of type LedPixel")
            
            output.extend([led.r, led.g, led.b, led.w])

        return output

    @staticmethod
    def to_bytes(led_pixels:list["LedPixel"]) -> bytes:
        output = bytearray()
        for led in led_pixels:
            if not isinstance(led, LedPixel):
                raise TypeError("All elements must be of type LedPixel")
            
            output.extend(led.as_bytes())

        return bytes(output)
    
class LedPixelArray():
    def __init__(self, num_pixels, order="rgbw"):
        self.pixels = [LedPixel(order=order) for _ in range(num_pixels)]
        self.order = order

    def set_pixel_color(self, index, r, g, b, w):
        if index < 0 or index >= len(self.pixels):
            raise IndexError("Index out of bounds")
        self.pixels[index].setColor(r, g, b, w)

    def set_all_pixels_color(self, r, g, b, w):
        for pixel in self.pixels:
            pixel.setColor(r, g, b, w)

    def to_bytes(self):
        return LedPixel.to_bytes(self.pixels)
    
    def to_data_list(self):
        return LedPixel.to_data_list(self.pixels)    

    def __len__(self):
        return len(self.pixels)
    
    def channels_per_pixel(self):
        if self.order == "rgbw":
            return 4
        elif self.order in ["rgwb", "rwgb", "bgrw", "bgwr", "wbrg"]:
            return 4
        else:
            raise ValueError("Invalid order specified")

