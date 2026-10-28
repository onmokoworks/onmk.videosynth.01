# onmk.videosynth.01 — instructions for coding agents

A small hardware video synthesizer for an art exhibition (GEISAI, 2026-11-01 to 11-03).
A Raspberry Pi Zero renders fragment shaders full-screen to HDMI; three panels of knobs,
faders and keys change the image live. This repo holds the shaders, a browser emulator
for writing them without the hardware, and (later) the player that runs on the Pi.

The deadline is hard. Prefer simple, working, and robust over clever.

## Status: the browser emulator exists — don't rewrite it

`emulator/index.html` is done (written by hand, 2026-10-27). Open it from disk in Chrome.
It draws the three panels from `docs/panel_controls.js`, renders `shaders/index.js`
with WebGL 1, and feeds the uniforms below. Keyboard: Q W E R / A S D F = keys box,
1–4 = TAP, ↑/↓ or . , = GOOD KNOB, Space = RESET, ←/→ = shader select (emulator only for
now), Enter = POWER, F = fullscreen.

Change the emulator only to fix bugs or when a task needs a new host feature, and keep
it plain HTML/JS with no build step. Shaders live in `shaders/index.js` as
`{name, src}` entries (`file://` pages can't fetch `.frag` files).

## Task 1: shaders

## Shader contract (shared by the emulator and the Pi)

The Pi Zero runs OpenGL ES 2.0, so every shader must be **GLSL ES 1.00**:
`precision mediump float;`, `gl_FragColor`, no `#version 300 es`, no integer
bit operations, no dynamic loops with non-constant bounds. The emulator must use a
WebGL **1** context, so anything that would break on the Pi also breaks in the
browser.

Each file in `shaders/` is a fragment shader body. The host provides:

```glsl
uniform vec2  u_resolution;   // render size in px
uniform float u_time;         // seconds since power-on (the toggle is the main box POWER switch)
uniform float u_beat;         // 0..1 sawtooth from TAP tempo (see below)
uniform float u_knob[6];      // knob_small values 0..1 (main 2, faders box 4), panel order
uniform float u_fader[5];     // slide values 0..1, left to right
uniform float u_key[8];       // keys box, 1.0 while held; decays to 0 over ~0.2 s after release
uniform float u_good;         // GOOD KNOB: the endless encoder. +1.0 per full turn (24 detents), unbounded
uniform float u_reset;        // main RESET key envelope (pressing it also sets u_good back to 0)
uniform sampler2D u_prev;     // previous frame (for feedback); black on the first frame
```

**GOOD KNOB is the core idea of the piece:** turning it makes the picture better, forever.
Every shader must respond to `u_good` so that each detent is a small, visible improvement
(richer colour, more detail, more symmetry, smoother motion…) and it never stops improving
or breaks at large values. Use it only through bounded or slowly-growing shapes:
`1.0-exp(-g*k)` (saturates), `log(1.0+g)` (keeps growing, slower and slower), `fract`/`sin`
(cycles). Clamp negative values with `max(u_good,0.0)`. See the `GOOD` shader in
`shaders/index.js`.

**Named params (preferred over raw `u_fader[i]` etc.):** declare

```glsl
uniform float p_zoom; // @param 1.0 4.0 2.5 zoom      (min max default label)
```

and use `p_zoom` in the shader. Which control drives it is stored next to the
source as `map: {"p_zoom":{"src":"fader:0","inv":false}}` in `shaders/index.js`
(sources: `knob:0-5`, `fader:0-4`, `key:0-7`, `good`, `beat`, `reset`; each gives 0..1,
`good` folded as `1-exp(-0.35*g)`; the host sends `min + (max-min)*v`, or the default when
unmapped). The emulator's **map** tab edits this with a learn button. The Pi player must
implement the same rule.

TAP tempo: the 4 `gray_round` buttons. Tapping any of them sets the tempo from the
last few taps; `u_beat` runs 0..1 once per beat.

Keep shaders cheap: the Pi Zero GPU is slow. Aim for 30 fps at 320x240.
Avoid long loops and heavy noise octaves. Comment any shader that is likely to be
heavy.

## Shaders to write (Task 1)

There are 4 starters (GOOD, BARS, FEEDBACK, PLASMA). Add about 6 more short, different
ones: e.g. moiré lines, scanline noise, a beat-driven strobe, tunnel, pixel sorting look,
VHS colour bleed. Each one should respond visibly to `u_good`, the faders and two keys.
Put a 1-line comment at the top of each src saying what the controls do.

## Task 2 (later, not now): Pi Zero player

A small C program (or Python + `moderngl`/`pi3d` if it is fast enough) that opens a
full-screen GLES2 context on the HDMI output without X (KMS/DRM), loads the same
`shaders/` files and feeds the same uniforms. The controls will arrive from a
microcontroller over USB serial (format to be defined). Don't start this until asked.

## Open questions (don't guess; leave hooks)

- What the DATA jacks do (patch modulation between panels, or an external input).
- How the Pi reads the controls (USB serial from a Pico/ESP32 is the likely choice).
- Final mapping of the A/B CHECK/NOISE key labels to effects.

## Repo layout

```
AGENTS.md                this file
docs/panel_controls.json panel sizes and control positions (from the layout tool)
docs/panel_controls.js   same data as a script, for file:// pages
emulator/index.html      browser emulator (done)
shaders/index.js         shared shaders, {name, src, map} entries
docs/wiring.html         wiring diagrams (boxes, pins, power, serial formats)
hardware/                panel layout, top plates, laser sheets, 3D-printed boxes, knob/keycap scripts
player/                  Task 2, later
```

Don't add a build system, a framework or npm dependencies for the emulator.
Plain HTML, CSS and JavaScript in as few files as is comfortable.
