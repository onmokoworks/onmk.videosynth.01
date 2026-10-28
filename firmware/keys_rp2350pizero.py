# RP2350-PiZero: key i=GPIO(2+i), GP2..13, pull-up, other leg=GND.
# UART0 TX=GP0 -> main GP5; shared GND. GPIO numbers, NOT header pins.
from common import BAUD, Debouncer, encode_keys


def sample_keys(pins, debouncers, now_ms):
    changed = False
    for pin, key in zip(pins, debouncers):
        if key.update(not pin.value(), now_ms):
            changed = True
    return changed, ''.join(str(key.value) for key in debouncers)


def run():
    from machine import Pin, UART
    import time
    pins = [Pin(n, Pin.IN, Pin.PULL_UP) for n in range(2, 14)]
    keys = [Debouncer() for _ in pins]
    uart = UART(0, BAUD, bits=8, parity=None, stop=1, tx=Pin(0), rx=Pin(1))
    last_tick = time.ticks_ms()
    now_ms = 0
    last_send = -100
    while True:
        tick = time.ticks_ms()
        now_ms += time.ticks_diff(tick, last_tick)
        last_tick = tick
        changed, bits = sample_keys(pins, keys, now_ms)
        if changed or now_ms - last_send >= 100:
            uart.write(encode_keys(bits))
            last_send = now_ms
        time.sleep_ms(1)


if __name__ == '__main__':
    run()
