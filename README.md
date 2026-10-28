# onmk.videosynth.01 (Vs-01)

A hardware video synthesizer for GEISAI 2026 (11/1–3). A Raspberry Pi Zero renders GLSL fragment shaders to HDMI;
three panels of knobs, faders and keys change the picture. The GOOD KNOB (an endless encoder) makes the picture
better with every detent, forever.

| folder | what |
|---|---|
| `emulator/` | browser emulator + shader editor + control mapping. Open `emulator/index.html` in Chrome (no server). |
| `shaders/` | the shaders (`index.js`, GLSL ES 1.00) and their control maps |
| `docs/` | `wiring.html` (wiring diagrams), `panel_controls.json` (panel parts and positions) |
| `hardware/layout/` | panel layout v08d (from the layout tool, the source of truth) |
| `hardware/panel_topplates/` | top plates 3 mm: DXF / SVG / STL / STEP |
| `hardware/laser_acrylic/` | laser-cut sheets (white matte top+bottom, opal LED ring, test coupon) |
| `hardware/enclosure_3dp/` | 3D-printed tray boxes (STL) and the CadQuery script |
| `hardware/knobs_keycaps/` | CadQuery scripts for the C14 knobs and the keycaps (STLs are large; regenerate) |
| `AGENTS.md` | instructions for coding agents (shader contract, mapping rules, tasks) |

The scripts in `hardware/` are copies for reference; they were run from the working folders, so their input
paths point there.
