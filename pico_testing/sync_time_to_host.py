# Modified from https://www.raspberrypi.org/forums/viewtopic.php?f=146&t=300275#p1810708
#
# Vendor:Product ID for Raspberry Pi Pico is 2E8A:0005
#
# see section 4.8 RTC of https://datasheets.raspberrypi.org/rp2040/rp2040-datasheet.pdf and in particular section 4.8.6
# for the RTC_BASE address (0x4005C000) and details of the RD2040 setup registers used to program the RT (also read
# 2.1.2. on Atomic Register Access)
#
from serial.tools import list_ports
import serial, time

print("Listing all available serial ports...")
# print all available serial ports
for port in list_ports.comports():
    print(f"{port.device} - {port.description}")
    print(f"  hwid: {port.hwid}")
    print(f"  vid:pid: {port.vid:04x}:{port.pid:04x}")
    print(f"  serial_number: {port.serial_number}")
    print(f"  location: {port.location}")
    print(f"  manufacturer: {port.manufacturer}")
    print(f"  product: {port.product}")
    print(f"  interface: {port.interface}")
print("-" * 40)

picoPorts = list(list_ports.grep("2E8A:0005"))
print("Looking for Raspberry Pi Pico...")
print(
    f"Found {len(picoPorts)} Raspberry Pi Pico(s) on port:"
    + str([p.device for p in picoPorts])
)
utcTime = str(int(time.time()))

print("Host computer epoch time: " + utcTime)
print(
    "Host computer local time: "
    + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    + "\r"
)

pythonInject = [
    "import machine",
    "import utime",
    "rtc_base_mem = 0x4005c000",
    "atomic_bitmask_set = 0x2000",
    "led_onboard = machine.Pin('LED', machine.Pin.OUT)",
    "(year,month,day,hour,minute,second,wday,yday)=utime.localtime(" + utcTime + ")",
    "machine.mem32[rtc_base_mem + 4] = (year << 12) | (month  << 8) | day",
    "machine.mem32[rtc_base_mem + 8] = ((hour << 16) | (minute << 8) | second) | (((wday + 1) % 7) << 24)",
    "machine.mem32[rtc_base_mem + atomic_bitmask_set + 0xc] = 0x10",
    "for i in range(5):",
    "    led_onboard.toggle()",
    "    utime.sleep(0.03)",
    "led_onboard.value(0)",
]

if not picoPorts:
    print("No Raspberry Pi Pico found")
else:
    picoSerialPort = picoPorts[0].device
    with serial.Serial(picoSerialPort, timeout=1) as s:
        s.write(b"\x03")  # interrupt the currently running code
        s.write(b"\x03")  # (do it twice to be certain)

        s.write(b"\x01")  # switch to raw REPL mode & inject code
        for code in pythonInject:
            s.write(bytes(code + "\r\n", "ascii"))
            time.sleep(0.01)
        time.sleep(0.25)
        s.write(b"\x04")  # exit raw REPL and run injected code
        time.sleep(0.25)  # give it time to run (observe the LED pulse)

        s.write(b"\x02")  # switch to normal REPL mode
        time.sleep(0.5)  # give it time to complete
        s.write(b"\x04")  # execute a 'soft reset' and trigger 'main.py'

    print("Raspberry Pi Pico found at " + str(picoSerialPort) + "\r")
    print("Host computer epoch synchronised over USB serial: " + utcTime + "\r")


# print the output from the serial port
while True:
    with serial.Serial(picoSerialPort) as s:
        print(s.readline().decode("utf-8").strip())
        print(s.readline().decode("utf-8").strip())
        print(
            "Host computer local time: "
            + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            + "\r"
        )
