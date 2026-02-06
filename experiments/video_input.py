# import the necessary packages
from deffcode import Sourcer
import numpy as np

# # initialize and formulate the decoder
# sourcer = Sourcer("0").probe_stream()

# # enumerate probed devices as Dictionary object(`dict`)
# print(sourcer.enumerate_devices)

# # enumerate probed devices as JSON string(`json.dump`)
# print(json.dumps(sourcer.enumerate_devices,indent=2))


# import the necessary packages
from deffcode import FFdecoder
import cv2
import time
import pathlib

OUTPUT_FRAMERATE = 10  # Set the desired output frame rate
RESOLUTION = (35*2,80)  # Set the resolution to 80x35
FILE = pathlib.Path(__file__).parent / "BigBuckBunny_320x180.mp4"

ffparams = {#"-filter:v":f"fps={OUTPUT_FRAMERATE}",
            "-custom_resolution": RESOLUTION # Set custom resolution to 35x80,
            }  # Example parameter to set frame rate to 10 FPS

# initialize and formulate the decoder with "0" index source for BGR24 output
#decoder = FFdecoder("1", frame_format="bgr24", verbose=True).formulate()
decoder = FFdecoder(str(FILE), verbose=True, **ffparams).formulate()

ts_last_frame = 0  # timestamp of the last frame

def ResizeWithAspectRatio(image, width=None, height=None, inter=cv2.INTER_AREA):
    dim = None
    (h, w) = image.shape[:2]

    if width is None and height is None:
        return image
    if width is None:
        r = height / float(h)
        dim = (int(w * r), height)
    elif height is None:
        r = width / float(w)
        dim = (width, int(h * r))
    else:
        rW = width / float(w)
        rH = height / float(h)
        r = min(rW, rH)
        dim = (int(w * r), int(h * r))

    return cv2.resize(image, dim, interpolation=inter)

# grab the BGR24 frames from decoder
for frame in decoder.generateFrame():
    # while time.time() - ts_last_frame < 1 / OUTPUT_FRAMERATE:
    #     time.sleep(0.002)

    # ts_last_frame = time.time()  # timestamp of new frame

    # check if frame is None
    if frame is None:
        break

    # {do something with the frame here}
    
    
    # Show output window
    resize = ResizeWithAspectRatio(frame, width=1280, height=720) # Resize by width OR

    cv2.imshow("Output", resize)

    # Convert the frame to the desired shape for the LED wall

    frameT = np.transpose(frame, (1, 0, 2)) #needet for H807SA
    #frame_flat = frameT.flatten()  # Flatten the frame to a 1D array

    #add white channel
    RGBW_frame = np.dstack((frameT, np.zeros((RESOLUTION[0], RESOLUTION[1], 1))))
    
    #flatten to universes
    RGBW_universes = RGBW_frame.reshape(RESOLUTION[0],RESOLUTION[1]*4)

    # check for 'q' key if pressed
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break

    

    
# close output window
cv2.destroyAllWindows()

# terminate the decoder
decoder.terminate()