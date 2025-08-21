# LED Wall Control Sofware
Software to convert single channel DMX data into control signals for a LED Matrix

## Setup
install [uv](https://docs.astral.sh/uv/getting-started/installation/)

run form repo directory:

     uv run entry_points/main.py

 
## Create new effects
navigate to "src/led_wall/effects/"

create a new effect based on the "BaseEffect" class.

### important methods

#### run_raw
    def  run_raw(self, DMX_channels,last_output) -> np.array:
 this is the only method which is required to be implemented as otherwise nothing will be shown. It is used to calculate the pixel values of the led matrix.
the output has the shape: (pixels width, pixels height, RGBW) e.g. (35,58,4)

inputs defined under "self.inputs" can be used to get current values for the effect. they get automatically updated by the method "update_inputs" which is automatically run bevor the run_raw method.
Optionally the raw channel data or the data from the last update can be used
   
 #### init  
      def  __init__(self,*args,**kwargs) -> None:
can be used to add code which needs to be run on initialisation such as adding additional inputs or state variables.
additional inputs can be added using: self.inputs["<'input name'>"] = <'input'>

    def  start(self):
gets called when there was a switch to this effect


