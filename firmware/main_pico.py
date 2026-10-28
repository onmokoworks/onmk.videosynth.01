# Main Pico: knob=GP26; encoder A/B=GP16/17 pull-ups, C=GND.
# RESET=GP18, SW2=GP19 pull-ups to GND (closed=1); POWER cuts 5 V only.
# UART0 RX=GP1 <- faders, TX=GP0 -> Pi GPIO15; UART1 RX=GP5 <- keys.
# Shared GND; all UARTs 3.3 V. UART1 TX GP4 is unused: leave disconnected.
from common import BAUD, ADCSmoother, Debouncer, QuadratureDecoder, LineBuffer, MainControls

USB_MIRROR = True  # V lines also on USB for the Mac bench test.


def poll_uart(uart, assembler, controls, source, now_ms):
    if uart.any():
        data = uart.read(min(uart.any(), 256))  # Bounded work; never wait for a line.
        if data:
            for line in assembler.feed(data):
                controls.receive(line, now_ms, source)


def run():
    from machine import Pin, ADC, UART, disable_irq, enable_irq
    import micropython
    import time
    micropython.alloc_emergency_exception_buf(100)
    faders_uart = UART(0, BAUD, bits=8, parity=None, stop=1, tx=Pin(0), rx=Pin(1),
                       timeout=0, timeout_char=0, rxbuf=512)
    keys_uart = UART(1, BAUD, bits=8, parity=None, stop=1, tx=Pin(4), rx=Pin(5),
                     timeout=0, timeout_char=0, rxbuf=512)
    adc = ADC(Pin(26))
    a, b = Pin(16, Pin.IN, Pin.PULL_UP), Pin(17, Pin.IN, Pin.PULL_UP)
    reset_pin, sw2_pin = Pin(18, Pin.IN, Pin.PULL_UP), Pin(19, Pin.IN, Pin.PULL_UP)
    decoder = QuadratureDecoder((a.value() << 1) | b.value())
    update_encoder = decoder.update

    def encoder_irq(pin):
        update_encoder((a.value() << 1) | b.value())

    # Hard IRQ sees edges even during UART/USB writes. Only small-int operations;
    # drain count each loop so the IRQ never needs to allocate a growing integer.
    a.irq(handler=encoder_irq, trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, hard=True)
    b.irq(handler=encoder_irq, trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, hard=True)
    controls = MainControls()
    f_buffer, k_buffer = LineBuffer(), LineBuffer()
    smooth, reset, sw2 = ADCSmoother(), Debouncer(), Debouncer()
    enc = 0
    last_tick = time.ticks_ms()
    now_ms = 0
    last_adc = -2
    deadline = time.ticks_us()
    knob = smooth.update(adc.read_u16())
    try:
        while True:
            tick = time.ticks_ms()
            now_ms += time.ticks_diff(tick, last_tick)
            last_tick = tick
            irq_state = disable_irq()
            delta = decoder.count
            decoder.count = 0
            enable_irq(irq_state)
            enc += delta  # Cumulative signed detents; player handles RESET offset.
            reset.update(not reset_pin.value(), now_ms)
            sw2.update(not sw2_pin.value(), now_ms)
            poll_uart(faders_uart, f_buffer, controls, 'F', now_ms)
            poll_uart(keys_uart, k_buffer, controls, 'K', now_ms)
            if now_ms - last_adc >= 2:
                knob = smooth.update(adc.read_u16())
                last_adc = now_ms
            if time.ticks_diff(time.ticks_us(), deadline) >= 0:
                line = controls.build_v(knob, enc, reset.value, sw2.value)
                faders_uart.write(line)
                if USB_MIRROR:
                    print(line, end='')
                deadline = time.ticks_add(deadline, 16667)
                if time.ticks_diff(time.ticks_us(), deadline) >= 0:
                    deadline = time.ticks_add(time.ticks_us(), 16667)
            time.sleep_us(250)
    finally:
        a.irq(handler=None)
        b.irq(handler=None)


if __name__ == '__main__':
    run()
