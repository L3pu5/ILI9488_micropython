#
#  ILI4988b. 
#      By L3pu5, L3pu5_Hare
#
# A simple Python wrapper for the ILI4988 driver bound to the SPI interface IM[2:0] 101 for chipsets such as
# those ubuqituous ones on Aliexpress.

from c565_chunk.c565_chunk import c565_chunk_image
from time import sleep
from math import floor


import ustruct

PICO_EXPERIMENTAL_MAX_BUFFER = 60_000 #Bytes, give/take memory. (42512 with earlier verison of this build)
                                       # Ihave gotten this to 60_000?
#565 RGBcolour 2 byte datastructure
def color565(r,g,b):
    return (r & 0xf8) << 8 | (g & 0xfc) << 3 | b >> 3

#Rectangle Helper class
class RECTANGLE():
    x = 0
    y = 0
    xf = 0
    yf = 0
    width = 0
    height = 0
    
    def __str__(self):
        return f"({self.x}, {self.y} -> {self.xf}, {self.yf} : {self.width} x {self.height} => {self.width*self.height} :: BUFF => {self.width*self.height*2})"

    def __init__(self, xi, yi, xf, yf):
        #FORCE lowerbound corners, xy
        if(xf < xi):
            self.x = xf
            self.xf = xi
        else:
            self.x = xi
            self.xf = xf
        if(yf < yi):
            self.y = yf
            self.yf = yi
        else:
            self.y = yi
            self.yf = yf
        self.width = self.xf-self.x
        self.height = self.yf-self.y

    def from_bounds(xi, yi, xf, yf):
        return RECTANGLE(xi, yi, xf, yf)
    
    def from_dimensions(xi, yi, width, height):
        return RECTANGLE(xi, yi, xi+width, yi+height)
    
    def buffer_cost_c565(self):
        return self.height * self.width * 2


class Display():

    #Initialised Register values are defined on 13.1 pg. 306
    # Mostly    : Sleep IN, Display OFF, Idle OFF, All Pixels OFF, Col_End 0x013F Row_End 0x01DF
    #           : Color_pixel_format 18Bit/Pix

    # Command constants from ILI9488 datasheet (Limited)
    # * Can be used in short Packet (no param)
    # ** Can be used in short Packet (1 param)
    # WRITE - NO PARAM                                    Note  Ref
    NO_OP           = const(0x00)   # No Operation          *   5.2.1
    SOFT_RESET      = const(0x01)   # Software Reset        *   5.2.2
    SLEEP_IN        = const(0x10)   # Enter Sleep           *   5.2.12
    SLEEP_OUT       = const(0x11)   # Leave Sleep           *   5.2.13
    ## ??
    PIXELS_ALL_OFF  = const(0x22)   # Turn all pixels off       5.2.18
    PIXELS_ALL_ON   = const(0x23)   # Turn all pixels on        5.2.19
    ## CONFIGURATION?
    PIXELS_FORMAT   = const(0x3A)   # Colour format             5.2.34 DBI[2:0], DPI[2:0] -> 101 for 565 --> b'01010101'
    CONFIG_BUFFER   = const(0x36)   # Buffer configuration      5.2.30  

    DISPLAY_FUNC    = const(0xB6)   # Display Op Mode           5.3.7

    ## OPERATIONAL MODES
    MODE_PARTIAL    = const(0x12)   # Enter Partial         *   5.2.14 (Described in 0x30, )
    MODE_NORMAL     = const(0x13)   # Enter Normal          *   5.2.15 (Disables Scroll/partial mode)
    ## DISPLAY MODES
    DISPLAY_OFF     = const(0x28)   # Turn Display off      *   5.2.20 (Screen still lit, memory not drawn)
    DISPLAY_ON      = const(0x29)   # Turn Display on       *   5.2.21 
    ## IDLE MODES
    IDLE_ON         = const(0x39)   # Enter Idle            *   5.2.33 (Nukes colour density to save power)
    IDLE_OFF        = const(0x38)   # Leave Idle            *   5.2.32 (Full colour density)
    # -- 
    ADDR_SET_COL    = const(0x2A)   # Set Col               *
    ADDR_SET_ROW    = const(0x2B)   # Set Row/Page          *
    WRITE_MEM       = const(0x2C)   # Write Memory          *   5.2.24
 
    FRAME_RATE      = const(0xB1)   #                           5.3.2
    CABC_9          = const(0xCF)   #                          5.3.26
    #CABC_9 is the only needed CABC control. 

    def __init__(self, spi, cs, dc, rst, width, height):
        #CS, DC are of type PIN()
        #CS pin means the chip is selected and data is going to be sent over the serial bus
        #DC means data/command -> if low, command, if high parameter.
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.reset = rst
        self.width = width
        self.height = height
        self.buffer = b""
        #Set default pin values
        cs.value(1)
        dc.value(0)
        rst.value(1)
        self.minimum_board_init()
        self.minimum_configuration()
        #self.build_buffer()
        self.clear()

    def build_buffer(self):
        #Do some controls here to see if we can save memory, or afford the buffer
        self.buffer = color565(0,0,0).to_bytes(2, "big") * self.width * self.height 
    
    def minimum_board_init(self):
        #Send the reset command to the display screen
        self.full_reset()
        sleep(.2)
        #Awake
        self.write_command(self.SLEEP_OUT)
        sleep(.1)
        #???
        self.write_command(self.CABC_9, 0x10)
        #Screen ON
        self.write_command(self.DISPLAY_ON)
    #CABC_9 is the ONLY required field.

    def minimum_configuration(self):
        #Set Pixel format
        self.write_command(self.PIXELS_FORMAT, int(b'01010101', 2))
        #Orientation
        self.write_command(self.CONFIG_BUFFER, int(b"0101100",2)) 

    def clear(self):
        self.write_buffer(0,0, self.width, self.height, self.buffer)


    def full_reset(self):
        #Reset the buffers on the display board
        self.write_command(self.SOFT_RESET)
        #ALlow device to do the reset
        sleep(.2)

    def reset_display(self):
        self.reset(1)
        sleep(0.05)
        self.reset(0)
        sleep(0.05)

    #Drawing Functions

    def write_buffer(self, rect, buffer):
        self.write_buffer(rect.x, rect.y, rect.width, rect.height, buffer)

    def write_buffer(self, x, y, width, height, buffer):
        self.write_command(self.ADDR_SET_COL, *ustruct.pack(">HH", x, x+width))
        self.write_command(self.ADDR_SET_ROW, *ustruct.pack(">HH", y, y+height ))
        self.write_command(self.WRITE_MEM)
        self.write_data(buffer)
        print("Writing buffer (%i, %i, %i, %i)", x, y, width, height)

    def draw_pixel(self, x, y, colour):
        self.write_buffer(x, y, 0, 0, colour.to_bytes(2, 'big'))
    
    def fill_rectangle(self, rect, color):
        buffer = color.to_bytes(2, "big") * rect.width * rect.height
        self.write_buffer(rect.x, rect.y, rect.width, rect.height, buffer)

    #Drawing Troubleshooting functions 

    def test_single_range(self, cmd, min, max, step, deltaTime, color=0x00):
        for i in range(min, max, step):
            self.write_command(cmd, i)
            self.draw_horizontal_range_bar(0, self.height-20, self.width, 20,(i-min)/max, color)
            sleep(deltaTime)
        self.write_command(cmd, min)
    
    def test_single_range_custom_bar(self, cmd, min, max, step, deltaTime, custom_bar, color=0x00):
        if(custom_bar.width > custom_bar.height):
            for i in range(min, max, step):
                self.write_command(cmd, i)
                self.draw_horizontal_range_bar(custom_bar,(i-min)/(max), color)
                sleep(deltaTime)
        else:
             for i in range(min, max, step):
                self.write_command(cmd, i)
                self.draw_vertical_range_bar(custom_bar, (i-min)/(max) ,color)
                sleep(deltaTime)           
        self.write_command(cmd, min)

    #A horizontal bar starting at x,y growing to x+width, y+height, 
    def draw_horizontal_range_bar(self, rect, progress, color=0x00):
        trueWidth = floor((rect.width)*progress)
        intermediate = RECTANGLE.from_dimensions(rect.x,rect.y,trueWidth, rect.height)
        self.fill_rectangle(intermediate, color) 

    #A vertical bar starting at x,y growing to x+width, y+height
    def draw_vertical_range_bar(self, rect, progress, color=0x00):
        trueHeight = floor((rect.height)*progress)
        intermediate = RECTANGLE.from_dimensions(rect.x,rect.y,rect.width, trueHeight)
        print(intermediate)
        self.fill_rectangle(intermediate, color) 

    # IO


    # Data Functions


    def write_data(self, buffer):
        self.dc(1)
        self.cs(0)
        self.spi.write(buffer)
        self.cs(1)

    def write_command(self, cmd, *opt_args):
        # Set DC = 0 for Data, set CS to 0
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1) 
        if len(opt_args) > 0:
            self.write_data(bytearray(opt_args))
    

