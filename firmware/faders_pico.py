# Faders Pico: 4067 S0..S3=GP2..5, SIG=GP26, EN=GND; UART0 TX=GP0.
# C0..3: knobs k2..5; C4..8: f0..4. Pots/mux at 3.3 V, shared GND.
from common import BAUD, ADCSmoother, raw_to_adc12, encode_faders


def read_channel(select, adc, channel, sleep_us):
    for bit, pin in enumerate(select):
        pin.value((channel >> bit) & 1)
    sleep_us(20)
    adc.read_u16()  # Discard unsettled conversion.
    return sum(adc.read_u16() for _ in range(4)) // 4


def run():
    from machine import Pin, ADC, UART
    import time
    select = [Pin(n, Pin.OUT, value=0) for n in range(2, 6)]
    adc = ADC(Pin(26))
    uart = UART(0, BAUD, bits=8, parity=None, stop=1, tx=Pin(0), rx=Pin(1))
    led = Pin(25, Pin.OUT)  # Non-W Pico and Pico 2 onboard LED.
    filters = [ADCSmoother() for _ in range(9)]
    deadline = time.ticks_ms()
    last_blink = deadline
    while True:
        values = [raw_to_adc12(filters[c].update(read_channel(select, adc, c, time.sleep_us)))
                  for c in range(9)]
        uart.write(encode_faders(values))
        now = time.ticks_ms()
        if time.ticks_diff(now, last_blink) >= 500:
            led.toggle()
            last_blink = now
        deadline = time.ticks_add(deadline, 20)
        wait = time.ticks_diff(deadline, time.ticks_ms())
        if wait > 0:
            time.sleep_ms(wait)
        else:
            deadline = time.ticks_ms()


if __name__ == '__main__':
    run()
