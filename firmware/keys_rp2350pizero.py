# RP2350-PiZero: keys use the pins in the top 10 rows of the header so the wires stay short (user, 10/28).
# key 0..11 = GP2,GP3,GP4,GP14 (top row = TAP), GP5,GP17,GP18,GP27 (middle), GP22,GP23,GP24,GP11 (bottom).
# Pull-up, other leg = GND.
# UART0 TX=GP0 -> main GP5; shared GND. GPIO numbers, NOT header pins.
from common import BAUD, Debouncer, encode_keys

KEY_PINS = (2, 3, 4, 14, 5, 17, 18, 27, 22, 23, 24, 11)


def sample_keys(pins, debouncers, now_ms):
    changed = False
    for pin, key in zip(pins, debouncers):
        if key.update(not pin.value(), now_ms):
            changed = True
    return changed, ''.join(str(key.value) for key in debouncers)


def run():
    from machine import Pin, UART
    import time
    pins = [Pin(n, Pin.IN, Pin.PULL_UP) for n in KEY_PINS]
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
