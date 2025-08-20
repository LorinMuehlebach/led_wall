import numpy as np

class Color:
    """
    Helper Object to handle colors in RGB and RGBW format.
    It can be used to convert between RGB and RGBW, mix colors, and handle hex color strings.
    the colors are 0-255 integers, so they can be used with OpenCV and other libraries.

    TODO: internally it can store a higher resolution of the color channels, but it will always return the color as a list of integers.
    The color mode can be set to 'rgb' or 'rgbw', and it will automatically convert between the two modes when necessary.
    """
    WHITE = (255, 209, 163) # (255, 196, 137) #3500k rgb color for the white channel https://andi-siess.de/rgb-to-color-temperature/
    value: list[int]
    MODE: str = 'auto'  # Default mode is RGB, can be set to 'rgbw' for RGBW mode

    def __init__(self, input:str|list|int=None, g=None, b=None, w=None, r=None, hex=None, type='auto'):
        if input is None and r is None and g is None and b is None and w is None and hex is None:
            self.value = [0, 0, 0, 0] if self.MODE == 'rgbw' else [0, 0, 0]
            return
        
        self.set_color(input, g, b, w, r, hex, type)
  
    def get_channels(self):
        #convert to 0-255 range
        return self.value
    
    def set_channels(self, channels:list[int]):
        if len(channels) != 3 and self.MODE == 'rgb':
            raise ValueError("Channels must be a list of 3 integers for RGB mode")

        if len(channels) != 4 and self.MODE == 'rgbw':
            raise ValueError("Channels must be a list of 4 integers for RGBW mode")
        
        self.value = channels

    def set_color(self, input:str|list|int, g=None, b=None, w=None, r=None, hex=None, type='auto'):
        if self.MODE != "auto" and self.MODE != type:
            raise ValueError(f"Type mismatch: expected {self.MODE}, got {type}")

        self.value = []
        if isinstance(input, list) or isinstance(input, tuple) or isinstance(input, np.ndarray):
            self.MODE = type if type != 'auto' else 'rgbw' if len(input) == 4 else 'rgb'
            self.set_channels(list(input))

        elif isinstance(input, str):
            self.set_hex(input,type=type)

        elif isinstance(input, int):
            r = input if r is None else r # input is used as r if r is not provided
            if r is None or g is None or b is None:
                raise ValueError("If input is an integer, r, g and b must be provided")
            self.value = [r, g, b]
            if type == 'rgbw' and w is not None:
                self.value.append(w)
            elif w is not None:
                raise ValueError("RGB mode does not support 'w' channel")

    def set_hex(self, hex:str,type='auto'):
        if not hex.startswith('#'):
            raise ValueError("Hex color must start with '#'")
                    
        hex = hex.lstrip('#')

        if len(hex) < 6:
            raise ValueError("Hex color must be at least 6 characters long")
        
        self.value[0] = int(hex[0:2], 16)
        self.value[1] = int(hex[2:4], 16)
        self.value[2] =int(hex[4:6], 16)
        self.MODE = 'rgb'
        
        if len(hex) < 8 and type == 'rgbw':
            raise ValueError("Hex color must be 8 characters long for RGBW mode")
        
        if len(hex) == 8 and not type == 'rgb':
            #ignore last channel if type is rgb
            self.MODE = 'rgbw'
            self.value[3] = int(hex[6:8], 16)

    def as_hex(self) -> str:
        """Returns the color as a hex string."""
        if self.MODE == 'rgbw':
            return f'#{self.value[0]:02x}{self.value[1]:02x}{self.value[2]:02x}{self.value[3]:02x}'
        return f'#{self.value[0]:02x}{self.value[1]:02x}{self.value[2]:02x}'

    def mix(self, other: 'Color', factor: float | int, convert=True) -> 'Color':
        """
        Interpolates between this color and another color by a given factor.
        The factor can be a float between 0 and 1, where 0 returns this color and 1 returns the other color.
        The factor can also be an integer, where 0 returns this color and 255 returns the other color.
        """
        if not isinstance(other, Color):
            raise ValueError("Other must be an instance of Color")
        
        #convert the other color to the same mode if necessary
        if other.MODE != self.MODE:
            if convert:
                other = other.convert_rgb2rgbw() if self.MODE == 'rgbw' else other.convert_rgbw2rgb()
            else:
                other = other.to_rgbw() if self.MODE == 'rgbw' else other.to_rgb()
        
        if isinstance(factor, int):
            if factor < 0 or factor > 255:
                raise ValueError("Factor must be between 0 and 255 if it is an integer")
            factor = factor / 255.0
        
        if factor < 0 or factor > 1:
            raise ValueError("Factor must be between 0 and 1")

        r = int(self.r + (other.r - self.r) * factor)
        g = int(self.g + (other.g - self.g) * factor)
        b = int(self.b + (other.b - self.b) * factor)
        w = int(self.w + (other.w - self.w) * factor) if self.MODE == 'rgbw' else None
        
        return Color(r, g, b, w, type=self.MODE)

    @property
    def r(self):
        return self.value[0]
    @r.setter
    def r(self, value:int):
        self.value[0] = value   

    @property
    def g(self):
        return self.value[1]
    @g.setter
    def g(self, value:int):
        self.value[1] = value
    @property
    def b(self):
        return self.value[2]
    @b.setter
    def b(self, value:int):
        self.value[2] = value

    @property
    def w(self):
        if self.MODE == 'rgbw':
            return self.value[3]
        return None
    @w.setter
    def w(self, value:int):
        if self.MODE == 'rgbw':
            self.value[3] = value
        else:
            raise ValueError("RGB mode does not support 'w' channel")
        
    def to_rgb(self,convert=False) -> 'Color':
        """Returns the color as an RGB Color object."""
        if self.MODE == 'rgb':
            return self
        
        if convert:
            return self.convert_rgbw2rgb()
        # Convert RGBW to RGB by removing the white channel contribution
        return Color(self.r, self.g, self.b, type='rgb')
    
    def to_rgbw(self, convert=False) -> 'Color':
        """Returns the color as an RGBW Color object."""
        if self.MODE == 'rgbw':
            return self
        
        if convert:
            return self.convert_rgb2rgbw()
        # Convert RGB to RGBW by adding a white channel with 0 value
        return Color(self.r, self.g, self.b, w=0, type='rgbw')

    @staticmethod
    def convert_rgbw2rgb(color:list) -> list:
        """
        convert RGBW to RGB by removing the white channel and adding the contribution of the white channel to the RGB channels.
        """
        if isinstance(color, np.ndarray):
            color = color.astype(np.uint16)
            
        out = [0, 0, 0]
        out[0] = min(color[0] + color[3] * Color.WHITE[0] // 255,255)
        out[1] = min(color[1] + color[3] * Color.WHITE[1] // 255,255)
        out[2] = min(color[2] + color[3] * Color.WHITE[2] // 255,255)

        return out
    
    def convert_rgb2rgbw(self) -> 'Color':
        """
        Returns the color as an RGBW Color object.
        https://stackoverflow.com/questions/40312216/converting-rgb-to-rgbw
        
        """
        if self.MODE == 'rgbw':
            return self
        #If the maximum value is 0, immediately return pure black.
        tM = max(self.r, max(self.g, self.b))
        if(tM == 0):
            return Color( r = 0, g = 0, b = 0, w = 0 )
            
        
        # These values are what the 'white' value would need to
        # be to get the corresponding color value.
        whiteValueForRed = self.r * 255.0 / self.WHITE[0]
        whiteValueForGreen = self.g * 255.0 / self.WHITE[1]
        whiteValueForBlue = self.b * 255.0 / self.WHITE[2]

        # Set the white value to the highest it can be for the given color
        # (without over saturating any channel - thus the minimum of them).
        minWhiteValue = min(whiteValueForRed, whiteValueForGreen, whiteValueForBlue)

        # The rest of the channels will just be the original value minus the
        # contribution by the white channel.
        Ro = max(min(self.r - minWhiteValue * self.WHITE[0] / 255,255),0)
        Go = max(min(self.g - minWhiteValue * self.WHITE[1] / 255,255),0)
        Bo = max(min(self.b - minWhiteValue * self.WHITE[2] / 255,255),0)
        Wo = max(min(minWhiteValue,255), 0)

        return Color(Ro, Go, Bo, Wo, type='rgbw')


        #This section serves to figure out what the color with 100% hue is
        multiplier = 255.0 / tM
        hR = self.r * multiplier
        hG = self.g * multiplier
        hB = self.b * multiplier

        #This calculates the Whiteness (not strictly speaking Luminance) of the color
        M = max(hR, max(hG, hB))
        m = min(hR, min(hG, hB))
        Luminance = ((M + m) / 2.0 - 127.5) * (255.0/127.5) / multiplier

        #Calculate the output values
        Wo = int(Luminance)
        Bo = int(self.b - Luminance)
        Ro = int(self.r - Luminance)
        Go = int(self.g - Luminance)

        #Trim them so that they are all between 0 and 255
        if (Wo < 0): Wo = 0
        if (Bo < 0): Bo = 0
        if (Ro < 0): Ro = 0
        if (Go < 0): Go = 0
        if (Wo > 255): Wo = 255
        if (Bo > 255): Bo = 255
        if (Ro > 255): Ro = 255
        if (Go > 255): Go = 255
        return Color(Ro, Go, Bo, Wo, type='rgbw')