# IMCD Application Configuration

# Radio SPI (SPI3) pins
IMCD_SPI_ID = 3
IMCD_SCK = 41
IMCD_MOSI = 42
IMCD_MISO = 39

# nRF24L01+ pins & settings
NRF_CSN = 5
NRF_CE = 4
NRF_IRQ = 6

# CC1101 pins & settings
CC_CSN = 8
CC_GDO0 = 9

# Operation modes
MODE_BOTH = 'both'
MODE_HIGH = 'high'
MODE_LOW = 'low'
DEFAULT_MODE = MODE_BOTH

# Channel / Room settings
DEFAULT_CHANNEL = 1
DEFAULT_ROOM_CODE = 0x4D43  # 'MC'
DEFAULT_RADIO_SPEED = '1M'  # '250k', '1M', '2M'

# Storage
STORAGE_PATH = '/imcd'
