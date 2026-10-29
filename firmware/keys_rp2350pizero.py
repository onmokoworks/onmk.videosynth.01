# RP2350-PiZero: pins as actually wired (rewired with short wires, checked key by key on 10/29).
# key 0..11 = GP5,GP7,GP9,GP21 (top row = TAP), GP18,GP8,GP1,GP20 (middle), GP22,GP23,GP24,GP11 (bottom).
# Pull-up, other leg = GND.
# UART0 TX=GP0 -> main GP5; shared GND. GPIO numbers, NOT header pins.
from common import BAUD, Debouncer, encode_keys

KEY_PINS = (5, 7, 9, 21, 18, 8, 1, 20, 22, 23, 24, 11)


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
    uart = UART(0, BAUD, bits=8, parity=None, stop=1, tx=Pin(0), rx=Pin(13))  # GP1 is a key now; RX is unused, parked on GP13
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
