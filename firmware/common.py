"""Vs-01 wire protocol and control logic. No hardware or CPython-only imports."""

BAUD = 115200
STEPS_PER_DETENT = 4  # RE160F: 24 pulses AND 24 detents/turn; four A/B edges/cycle.
DEBOUNCE_MS = 5


def _fields(line, tag, count):
    if isinstance(line, bytes):
        line = line.decode('ascii')
    if line.endswith('\n'):
        line = line[:-1]
    if line.endswith('\r'):
        line = line[:-1]
    parts = line.split(',')
    if len(parts) != count or parts[0] != tag:
        raise ValueError('wrong line type or field count')
    return parts[1:]


def _bits(value, count):
    if len(value) != count or any(c not in '01' for c in value):
        raise ValueError('invalid bit string')
    return value


def _integer(value, signed=False):
    digits = value[1:] if signed and value[:1] in ('-', '+') else value
    if not digits or any(c not in '0123456789' for c in digits):
        raise ValueError('invalid integer')
    return int(value)


def _unit(value):
    value = float(value)
    if not 0.0 <= value <= 1.0:  # Also rejects NaN and infinities.
        raise ValueError('outside 0..1')
    return value


def encode_faders(values):
    if len(values) != 9:
        raise ValueError('nine ADC values required')
    line = 'F,' + ','.join(str(v) for v in values) + '\n'
    decode_faders(line)
    return line


def decode_faders(line):
    values = [_integer(v) for v in _fields(line, 'F', 10)]
    if any(v > 4095 for v in values):
        raise ValueError('outside 0..4095')
    return values


def encode_keys(bits):
    return 'K,' + _bits(bits, 12) + '\n'


def decode_keys(line):
    return _bits(_fields(line, 'K', 2)[0], 12)


def encode_v(knobs, faders, keys, taps, enc, reset, sw2):
    if len(knobs) != 6 or len(faders) != 5:
        raise ValueError('six knobs and five faders required')
    values = ['%.5f' % _unit(v) for v in list(knobs) + list(faders)]
    line = 'V,' + ','.join(values + [keys, taps, str(enc), str(reset), str(sw2)]) + '\n'
    decode_v(line)
    return line


def decode_v(line):
    """Strict v09 decoder; player itself also accepts legacy 16-field V lines."""
    p = _fields(line, 'V', 17)
    analog = [_unit(v) for v in p[:11]]
    keys, taps = _bits(p[11], 8), _bits(p[12], 4)
    enc = _integer(p[13], signed=True)
    reset, sw2 = _bits(p[14], 1), _bits(p[15], 1)
    return analog[:6], analog[6:], keys, taps, enc, int(reset), int(sw2)


class LineBuffer:
    """Bounded ASCII line assembly; discard an entire corrupt/oversized line."""
    def __init__(self, limit=192):
        self.limit = limit
        self.buffer = ''
        self.dropping = False

    def feed(self, data):
        lines = []
        for c in data:
            if c == 10:
                if not self.dropping:
                    lines.append(self.buffer)
                self.buffer = ''
                self.dropping = False
            elif not self.dropping:
                if c < 32 and c != 13 or c > 126 or len(self.buffer) >= self.limit:
                    self.buffer = ''
                    self.dropping = True
                else:
                    self.buffer += chr(c)
        return lines


class Debouncer:
    """Stable for 5 ms before changing; update returns one event per accepted edge.

    Pass an unwrapped ms clock (board loops accumulate time.ticks_diff).
    Poll at ~1 kHz; pulses shorter than debounce_ms intentionally count as bounce.
    """
    def __init__(self, initial=0, debounce_ms=DEBOUNCE_MS):
        self.value = int(bool(initial))
        self.candidate = self.value
        self.since = 0
        self.delay = debounce_ms

    def update(self, raw, now_ms):
        raw = int(bool(raw))
        if raw != self.candidate:
            self.candidate = raw
            self.since = now_ms
        if self.candidate != self.value and now_ms - self.since >= self.delay:
            self.value = self.candidate
            return True
        return False


class QuadratureDecoder:
    """Full-step transition table; count only complete cycles ending at A=B=1.

    A is bit 1, B bit 0. CW (A closes first) is positive. Adjacent bounce cancels;
    a two-bit jump abandons the partial cycle. No time debounce on encoder edges.
    count can be drained under disabled IRQs by the main loop.
    """
    TABLE = (0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0)

    def __init__(self, initial=3):
        self.state = initial
        self.partial = 0
        self.count = 0

    def update(self, state):
        old = self.state
        self.state = state
        if old ^ state == 3:
            self.partial = 0
            return 0
        self.partial += self.TABLE[(old << 2) | state]
        delta = 0
        if state == 3:
            if self.partial >= STEPS_PER_DETENT:
                delta = 1
            elif self.partial <= -STEPS_PER_DETENT:
                delta = -1
            self.partial = 0
        self.count += delta
        return delta


def raw_to_unit(raw):
    return max(0, min(65535, raw)) / 65535.0


def raw_to_adc12(raw):
    return (max(0, min(65535, int(raw))) * 4095 + 32767) // 65535


class ADCSmoother:
    """One-pole IIR followed by a raw-u16 deadband (defaults: alpha=1/4, 64).

    First read seeds the filter; endpoints snap within the deadband so full travel
    still reaches 0 and 1. Filter state continues moving inside the output deadband.
    """
    def __init__(self, alpha=0.25, deadband=64):
        if not 0 < alpha <= 1 or deadband < 0:
            raise ValueError('invalid filter settings')
        self.alpha = alpha
        self.deadband = deadband
        self.filtered = None
        self.value = None

    def update(self, raw):
        raw = max(0, min(65535, raw))
        if self.filtered is None:
            self.filtered = float(raw)
            self.value = int(raw)
        else:
            self.filtered += self.alpha * (raw - self.filtered)
            value = int(self.filtered + 0.5)
            if value <= self.deadband:
                value = 0
            elif value >= 65535 - self.deadband:
                value = 65535
            if value in (0, 65535) or abs(value - self.value) >= self.deadband:
                self.value = value
        return self.value


class MainControls:
    """Last valid side-box state is retained indefinitely, including after 500 ms."""
    def __init__(self):
        self.faders = [2048] * 9
        self.keys = '0' * 12
        self.last_faders_ms = None
        self.last_keys_ms = None

    def receive(self, line, now_ms, source):
        try:
            if source == 'F':
                values = decode_faders(line)
                self.faders = values
                self.last_faders_ms = now_ms
            elif source == 'K':
                bits = decode_keys(line)
                self.keys = bits
                self.last_keys_ms = now_ms
            else:
                return False
        except (ValueError, UnicodeError):
            return False
        return True

    def build_v(self, knob_raw, enc, reset, sw2):
        analog = [v / 4095.0 for v in self.faders]
        return encode_v([raw_to_unit(knob_raw), 0.5] + analog[:4], analog[4:],
                        self.keys[4:], self.keys[:4], enc, reset, sw2)
