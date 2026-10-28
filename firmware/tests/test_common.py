"""Host-only tests. Extract the real player functions via AST; never import player.

This deliberately executes read_uart, State and tap from the current source, so
format/behavior changes in player.py can break this compatibility check.
"""
import ast
import pathlib
import sys
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import common as c
from faders_pico import read_channel
from keys_rp2350pizero import sample_keys
from main_pico import poll_uart


class ProtocolTests(unittest.TestCase):
    def test_f_roundtrip(self):
        values = [0, 1, 2, 2047, 2048, 4093, 4094, 4095, 1000]
        line = c.encode_faders(values)
        self.assertEqual(line, 'F,0,1,2,2047,2048,4093,4094,4095,1000\n')
        self.assertEqual(c.decode_faders(line.encode()), values)
        self.assertEqual(c.decode_faders(line[:-1] + '\r\n'), values)

    def test_k_roundtrip_and_order(self):
        for i in range(12):
            bits = ''.join('1' if n == i else '0' for n in range(12))
            self.assertEqual(c.decode_keys(c.encode_keys(bits)), bits)

    def test_v_roundtrip(self):
        args = ([0, 0.5, 1, 0.25, 0.75, 0.125], [0, 0.25, 0.5, 0.75, 1],
                '01010101', '1010', -37, 1, 0)
        self.assertEqual(c.decode_v(c.encode_v(*args)), args)
        self.assertEqual(len(c.encode_v(*args).strip().split(',')), 17)

    def test_malformed_f(self):
        valid = 'F,' + ','.join(['0'] * 9)
        for line in ('', valid + ',0', valid[:-2], valid.replace('F', 'K'),
                     valid.replace(',0', ',4096', 1), valid.replace(',0', ',-1', 1),
                     valid.replace(',0', ',1.0', 1), valid.replace(',0', ', 1', 1),
                     valid.replace(',0', ',1_0', 1), valid + '\nBAD'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                c.decode_faders(line)

    def test_malformed_k(self):
        for line in ('K,0000', 'K,00000000000x', 'K,000000000000,', 'X,000000000000',
                     'K,00000000000１', 'K,00000000,0000'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                c.decode_keys(line)

    def test_malformed_v(self):
        good = c.encode_v([0.5] * 6, [0.5] * 5, '0' * 8, '0' * 4, 0, 0, 0).strip().split(',')
        for index, value in ((1, 'nan'), (2, 'inf'), (3, '-0.01'), (4, '1.01'),
                             (12, '0' * 7), (13, 'xxx1'), (14, '1.5'),
                             (15, '2'), (16, '-1')):
            parts = good[:]
            parts[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                c.decode_v(','.join(parts))
        with self.assertRaises(ValueError):
            c.decode_v(','.join(good[:-1]))

    def test_encoders_reject_invalid_inputs(self):
        for action in (lambda: c.encode_faders([0] * 8),
                       lambda: c.encode_faders([0] * 8 + [5000]),
                       lambda: c.encode_keys(''),
                       lambda: c.encode_v([0] * 5, [0] * 5, '0' * 8, '0' * 4, 0, 0, 0)):
            with self.assertRaises(ValueError):
                action()

    def test_line_assembly_fragmentation_and_crlf(self):
        buf = c.LineBuffer()
        self.assertEqual(buf.feed(b'K,000'), [])
        self.assertEqual(buf.feed(b'000000000\r\nF,1'), ['K,000000000000\r'])
        self.assertEqual(buf.feed(b'\nK,111111111111\n'), ['F,1', 'K,111111111111'])

    def test_overflow_and_non_ascii_drop_whole_line(self):
        for bad in (b'x' * 1000, b'K,\xff', b'K,\x00'):
            buf = c.LineBuffer(limit=20)
            self.assertEqual(buf.feed(bad), [])
            self.assertLessEqual(len(buf.buffer), 20)
            self.assertEqual(buf.feed(b'validsuffix\nK,000000000000\n'), ['K,000000000000'])

    def test_side_retention_and_port_validation(self):
        state = c.MainControls()
        f = [0, 4095, 1024, 2048, 1, 22, 333, 444, 555]
        self.assertTrue(state.receive(c.encode_faders(f), 10, 'F'))
        self.assertTrue(state.receive('K,101001100101', 20, 'K'))
        self.assertFalse(state.receive('K,000000000000', 30, 'F'))
        self.assertFalse(state.receive(b'F,\xff', 30, 'F'))
        self.assertFalse(state.receive('F,1', 1000, 'F'))
        self.assertEqual(state.last_faders_ms, 10)
        self.assertEqual(state.last_keys_ms, 20)
        knobs, faders, keys, taps, enc, reset, sw2 = c.decode_v(state.build_v(65535, -24, 1, 1))
        self.assertEqual(knobs[:2], [1, 0.5])
        for got, raw in zip(knobs[2:] + faders, f):
            self.assertAlmostEqual(got, raw / 4095, places=5)
        self.assertEqual((keys, taps, enc, reset, sw2), ('01100101', '1010', -24, 1, 1))
        # There is deliberately no timeout mutation: values persist at arbitrary age.
        self.assertEqual(state.faders, f)


class EncoderTests(unittest.TestCase):
    CW = (1, 0, 2, 3)
    CCW = (2, 0, 1, 3)

    def test_full_cycle_per_detent_both_directions(self):
        d = c.QuadratureDecoder()
        self.assertEqual(c.STEPS_PER_DETENT, 4)
        for _ in range(24):
            self.assertEqual([d.update(s) for s in self.CW], [0, 0, 0, 1])
        self.assertEqual(d.count, 24)
        for _ in range(48):
            self.assertEqual([d.update(s) for s in self.CCW], [0, 0, 0, -1])
        self.assertEqual(d.count, -24)

    def test_bounce_at_each_edge_in_both_directions(self):
        for cycle, expected in ((self.CW, 1), (self.CCW, -1)):
            d = c.QuadratureDecoder()
            old = 3
            for state in cycle:
                for s in (state, old, state, state):
                    d.update(s)
                old = state
            self.assertEqual(d.count, expected)

    def test_partial_reversal_not_a_detent(self):
        d = c.QuadratureDecoder()
        for s in (1, 0, 1, 3, 2, 3):
            self.assertEqual(d.update(s), 0)
        self.assertEqual(d.count, 0)

    def test_invalid_two_bit_jump_discards_partial_then_recovers(self):
        d = c.QuadratureDecoder()
        for s in (1, 2, 3, 0, 3):
            self.assertEqual(d.update(s), 0)
        for s in self.CW:
            d.update(s)
        self.assertEqual(d.count, 1)

    def test_start_mid_cycle_no_phantom_step(self):
        for initial, path in ((0, (2, 3)), (1, (0, 2, 3)), (2, (3,))):
            d = c.QuadratureDecoder(initial)
            for s in path:
                d.update(s)
            self.assertEqual(d.count, 0)


class DebounceADCTests(unittest.TestCase):
    def test_bounce_then_both_edges_once(self):
        d = c.Debouncer()
        samples = [(0, 0), (1, 1), (0, 2), (1, 3), (1, 7), (1, 8), (1, 20),
                   (0, 21), (1, 22), (0, 23), (0, 28), (0, 30)]
        events = [(t, d.value) for raw, t in samples if d.update(raw, t)]
        self.assertEqual(events, [(8, 1), (28, 0)])

    def test_short_noise_rejected(self):
        d = c.Debouncer()
        for raw, t in ((1, 0), (0, 4), (0, 10)):
            self.assertFalse(d.update(raw, t))
        self.assertEqual(d.value, 0)

    def test_adc_mapping_endpoints_and_midpoint(self):
        self.assertEqual([c.raw_to_unit(v) for v in (-1, 0, 65535, 70000)], [0, 0, 1, 1])
        self.assertEqual([c.raw_to_adc12(v) for v in (0, 32768, 65535)], [0, 2048, 4095])
        self.assertAlmostEqual(c.raw_to_unit(32768), 0.5, places=4)

    def test_iir_and_deadband(self):
        d = c.ADCSmoother()
        self.assertEqual(d.update(30000), 30000)
        for raw in (30020, 29980) * 20:
            self.assertEqual(d.update(raw), 30000)
        value = d.update(40000)
        self.assertGreater(value, 30000)
        self.assertLess(value, 40000)
        for _ in range(100):
            d.update(40000)
        self.assertLess(abs(d.value - 40000), 64)

    def test_endpoints_reachable_after_smoothing(self):
        d = c.ADCSmoother()
        d.update(32768)
        for endpoint in (65535, 0):
            for _ in range(100):
                d.update(endpoint)
            self.assertEqual(d.value, endpoint)

    def test_endpoint_reachable_from_inside_deadband(self):
        for start, endpoint in ((30, 0), (65505, 65535)):
            d = c.ADCSmoother()
            d.update(start)
            for _ in range(100):
                d.update(endpoint)
            self.assertEqual(d.value, endpoint)


class BoardBoundaryTests(unittest.TestCase):
    def test_mux_wait_discard_average_and_select_order(self):
        events = []
        class Pin:
            def __init__(self, bit): self.bit = bit
            def value(self, value): events.append(('pin', self.bit, value))
        class ADC:
            samples = iter((65535, 100, 200, 300, 400))
            def read_u16(self):
                events.append(('read',))
                return next(self.samples)
        value = read_channel([Pin(i) for i in range(4)], ADC(), 5,
                             lambda us: events.append(('wait', us)))
        self.assertEqual(value, 250)
        self.assertEqual(events[:5], [('pin', 0, 1), ('pin', 1, 0), ('pin', 2, 1),
                                          ('pin', 3, 0), ('wait', 20)])
        self.assertEqual(events[5:], [('read',)] * 5)

    def test_key_sampling_reports_press_and_release(self):
        class Pin:
            level = 1
            def value(self): return self.level
        pins = [Pin() for _ in range(12)]
        keys = [c.Debouncer() for _ in pins]
        pins[0].level = pins[11].level = 0
        self.assertEqual(sample_keys(pins, keys, 0), (False, '0' * 12))
        self.assertEqual(sample_keys(pins, keys, 5), (True, '100000000001'))
        pins[0].level = 1
        self.assertFalse(sample_keys(pins, keys, 6)[0])
        self.assertEqual(sample_keys(pins, keys, 11), (True, '000000000001'))

    def test_nonblocking_uart_fragmented_and_malformed(self):
        class UART:
            data = b''
            def any(self): return len(self.data)
            def read(self, n):
                result, self.data = self.data[:n], self.data[n:]
                return result
        uart, buf, state = UART(), c.LineBuffer(), c.MainControls()
        poll_uart(uart, buf, state, 'K', 0)
        uart.data = b'garbage\nK,1000'
        poll_uart(uart, buf, state, 'K', 1)
        self.assertEqual(state.keys, '0' * 12)
        uart.data = b'00000001\nK,invalid\n'
        poll_uart(uart, buf, state, 'K', 2)
        self.assertEqual(state.keys, '100000000001')
        self.assertEqual(state.last_keys_ms, 2)


class PlayerCompatibilityTests(unittest.TestCase):
    def setUp(self):
        path = pathlib.Path(__file__).resolve().parents[2] / 'player' / 'player.py'
        tree = ast.parse(path.read_text())
        names = {'State', 'read_uart', 'tap', 'good'}
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names)
        self.os = types.SimpleNamespace(read=lambda fd, n: self.data)
        self.ns = {'os': self.os}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), self.ns)
        self.ns['S'] = self.ns['State']()
        self.state = self.ns['S']

    def send(self, line, now):
        self.data = line.encode('ascii')
        self.assertEqual(self.ns['read_uart'](7, '', now), '')

    def test_real_player_accepts_appended_sw2_and_key_mapping(self):
        controls = c.MainControls()
        controls.receive(c.encode_faders([0, 4095, 1024, 3072, 0, 1, 2, 3, 4095]), 0, 'F')
        controls.receive('K,100010000001', 0, 'K')
        self.send(controls.build_v(65535, -48, 0, 1), 10.0)
        self.assertEqual(self.state.last_rx, 10.0)
        self.assertEqual(self.state.knob[:4], [1.0, 0.5, 0.0, 1.0])
        self.assertEqual(self.state.fader[-1], 1.0)
        self.assertEqual(self.state.held, [True, False, False, False, False, False, False, True])
        self.assertEqual(self.state.taps, [True, False, False, False])
        self.assertEqual(self.state.taps_t, [10.0])
        self.assertEqual(self.ns['good'](10.0), -2.0)

    def test_real_player_reset_uses_cumulative_detents(self):
        controls = c.MainControls()
        self.send(controls.build_v(0, 100, 1, 0), 10)
        self.assertEqual(self.state.enc0, 100)
        self.send(controls.build_v(0, 124, 0, 0), 11)
        self.assertEqual(self.ns['good'](11), 1.0)
        self.assertEqual(self.state.reset_rel, 11)


if __name__ == '__main__':
    unittest.main()
