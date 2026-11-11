from machine import Pin, SPI, freq
import gc

from drivers.ili93xx.ili9341 import ILI9341 as SSD
# Create and export an SSD instance
pdc = Pin(3, Pin.OUT, value=0)  # Arbitrary pins borrowed from st7735r_esp32.py
prst = Pin(14, Pin.OUT, value=1)
pcs = Pin(10, Pin.OUT, value=1)
pled = Pin(46, Pin.OUT, value=1)
gc.collect()  # Precaution before instantiating framebuf
spi = SPI(2, 60_000_000, sck=Pin(12), mosi=Pin(11), miso=Pin(13))  # No need to wire MISO.
freq(240_000_000)
gc.collect()  # Precaution before instantiating framebuf
ssd = SSD(spi, cs=pcs, dc=pdc, rst=prst, height=240, width=320, usd=False)
from gui.core.ugui import Display, quiet  # Must perform this import after instantiating SSD (see other examples)
quiet()  # No RAM reports / banner chatter on the REPL
gc.collect()  # Precaution before instantiating framebuf

# Create and export a Display instance
# Define control buttons
nxt = Pin(7, Pin.IN, Pin.PULL_UP)  # Move to next control
sel = Pin(18, Pin.IN, Pin.PULL_UP)  # Operate current control
prev = Pin(15, Pin.IN, Pin.PULL_UP)  # Move to previous control
increase = Pin(16, Pin.IN, Pin.PULL_UP)  # Increase control's value
decrease = Pin(17, Pin.IN, Pin.PULL_UP)  # Decrease control's value
display = Display(ssd, nxt, sel, prev, increase, decrease)