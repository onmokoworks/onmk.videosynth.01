#!/usr/bin/env python3
"""Vs-01 player: runs the shaders in shaders/index.js full screen on a Raspberry Pi Zero (KMS/DRM, no X).

Pure Python + ctypes (libdrm, libgbm, libEGL, libGLESv2 from the stock Raspberry Pi OS), so it needs no
installs on an offline Pi. Same uniforms and param mapping as emulator/index.html (see AGENTS.md).

  python3 player.py DIR       DIR holds index.js (shaders), config.json; log.txt is written there.

Controls arrive as lines on the UART (/dev/serial0, 115200):  V,k0..k5,f0..f4,keys,taps,enc,reset
(keys/taps are bit strings, k/f are 0..1, enc is the GOOD KNOB detent count). Without them the player runs
in demo mode (GOOD rises slowly, shaders cycle) so it shows something on its own.
"""
import ctypes as C, ctypes.util, faulthandler, json, math, os, re, select, signal, sys, time, traceback

DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(DIR, 'log.txt')

def log(*a):
    msg = time.strftime('%m-%d %H:%M:%S ') + ' '.join(str(x) for x in a)
    print(msg, flush=True)
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 200_000: os.replace(LOG, LOG + '.old')
        with open(LOG, 'a') as f: f.write(msg + '\n')
    except OSError: pass

def lib(name, soname):
    path = ctypes.util.find_library(name) or soname
    return C.CDLL(path)

# ---------------------------------------------------------------- DRM / GBM
class ModeInfo(C.Structure):
    _fields_ = [('clock', C.c_uint32), ('hdisplay', C.c_uint16), ('hsync_start', C.c_uint16), ('hsync_end', C.c_uint16),
                ('htotal', C.c_uint16), ('hskew', C.c_uint16), ('vdisplay', C.c_uint16), ('vsync_start', C.c_uint16),
                ('vsync_end', C.c_uint16), ('vtotal', C.c_uint16), ('vscan', C.c_uint16), ('vrefresh', C.c_uint32),
                ('flags', C.c_uint32), ('type', C.c_uint32), ('name', C.c_char * 32)]
class Res(C.Structure):
    _fields_ = [('count_fbs', C.c_int), ('fbs', C.POINTER(C.c_uint32)), ('count_crtcs', C.c_int), ('crtcs', C.POINTER(C.c_uint32)),
                ('count_connectors', C.c_int), ('connectors', C.POINTER(C.c_uint32)), ('count_encoders', C.c_int),
                ('encoders', C.POINTER(C.c_uint32)), ('min_width', C.c_uint32), ('max_width', C.c_uint32),
                ('min_height', C.c_uint32), ('max_height', C.c_uint32)]
class Connector(C.Structure):
    _fields_ = [('connector_id', C.c_uint32), ('encoder_id', C.c_uint32), ('connector_type', C.c_uint32),
                ('connector_type_id', C.c_uint32), ('connection', C.c_int), ('mmWidth', C.c_uint32), ('mmHeight', C.c_uint32),
                ('subpixel', C.c_int), ('count_modes', C.c_int), ('modes', C.POINTER(ModeInfo)), ('count_props', C.c_int),
                ('props', C.POINTER(C.c_uint32)), ('prop_values', C.POINTER(C.c_uint64)), ('count_encoders', C.c_int),
                ('encoders', C.POINTER(C.c_uint32))]
class Encoder(C.Structure):
    _fields_ = [('encoder_id', C.c_uint32), ('encoder_type', C.c_uint32), ('crtc_id', C.c_uint32),
                ('possible_crtcs', C.c_uint32), ('possible_clones', C.c_uint32)]
FLIP_CB = C.CFUNCTYPE(None, C.c_int, C.c_uint, C.c_uint, C.c_uint, C.c_void_p)
class EventContext(C.Structure):
    _fields_ = [('version', C.c_int), ('vblank_handler', C.c_void_p), ('page_flip_handler', FLIP_CB)]

drm = C.CDLL(ctypes.util.find_library('drm') or 'libdrm.so.2', use_errno=True); gbm = lib('gbm', 'libgbm.so.1')
def err(): e = C.get_errno(); return '%d (%s)' % (e, os.strerror(e))
drm.drmModeGetResources.restype = C.POINTER(Res); drm.drmModeGetConnector.restype = C.POINTER(Connector)
drm.drmModeGetEncoder.restype = C.POINTER(Encoder)
drm.drmModeAddFB.argtypes = [C.c_int, C.c_uint32, C.c_uint32, C.c_uint8, C.c_uint8, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint32)]
drm.drmModeSetCrtc.argtypes = [C.c_int, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint32), C.c_int, C.POINTER(ModeInfo)]
drm.drmModePageFlip.argtypes = [C.c_int, C.c_uint32, C.c_uint32, C.c_uint32, C.c_void_p]
drm.drmHandleEvent.argtypes = [C.c_int, C.POINTER(EventContext)]
gbm.gbm_create_device.restype = C.c_void_p; gbm.gbm_create_device.argtypes = [C.c_int]
gbm.gbm_surface_create.restype = C.c_void_p; gbm.gbm_surface_create.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32]
gbm.gbm_surface_lock_front_buffer.restype = C.c_void_p; gbm.gbm_surface_lock_front_buffer.argtypes = [C.c_void_p]
gbm.gbm_surface_release_buffer.argtypes = [C.c_void_p, C.c_void_p]
class BoHandle(C.Union):   # union gbm_bo_handle, returned BY VALUE: on 32-bit ARM that goes through a hidden pointer,
    _fields_ = [('ptr', C.c_void_p), ('s32', C.c_int32), ('u32', C.c_uint32), ('s64', C.c_int64), ('u64', C.c_uint64)]
gbm.gbm_bo_get_handle.restype = BoHandle; gbm.gbm_bo_get_handle.argtypes = [C.c_void_p]   # so it must be declared as a union, not uint64
gbm.gbm_bo_get_stride.restype = C.c_uint32; gbm.gbm_bo_get_stride.argtypes = [C.c_void_p]
GBM_FORMAT_XRGB8888 = 0x34325258; GBM_BO_USE_SCANOUT = 1; GBM_BO_USE_RENDERING = 4

def quiet_console():
    try:
        import fcntl
        fd = os.open('/dev/tty1', os.O_RDWR | os.O_NOCTTY)
        fcntl.ioctl(fd, 0x4B3A, 1)   # KDSETMODE KD_GRAPHICS
        log('tty1 set to graphics mode'); return fd
    except Exception as e: log('tty1 graphics mode failed:', e); return None

def open_drm():
    for card in ('/dev/dri/card0', '/dev/dri/card1', '/dev/dri/card2'):
        try: fd = os.open(card, os.O_RDWR | os.O_CLOEXEC)
        except OSError: continue
        res = drm.drmModeGetResources(fd)
        if not res: os.close(fd); continue
        r = res.contents
        for n in range(r.count_connectors):
            con = drm.drmModeGetConnector(fd, r.connectors[n])
            if con and con.contents.connection == 1 and con.contents.count_modes > 0:
                c = con.contents
                modes = [c.modes[k] for k in range(c.count_modes)]
                want = CFG.get('mode', [1280, 720])          # 720p keeps the final blit cheap on a Pi Zero
                mode = next((m for m in modes if m.hdisplay == want[0] and m.vdisplay == want[1]), modes[0])
                crtc = 0
                if c.encoder_id:
                    enc = drm.drmModeGetEncoder(fd, c.encoder_id)
                    if enc: crtc = enc.contents.crtc_id
                if not crtc:
                    for e in range(c.count_encoders):
                        enc = drm.drmModeGetEncoder(fd, c.encoders[e])
                        for k in range(r.count_crtcs):
                            if enc and enc.contents.possible_crtcs & (1 << k): crtc = r.crtcs[k]; break
                        if crtc: break
                log('drmSetMaster ->', drm.drmSetMaster(fd), err())
                log('drm', card, 'connector', c.connector_id, 'mode', mode.hdisplay, 'x', mode.vdisplay, '@', mode.vrefresh, 'crtc', crtc)
                return fd, c.connector_id, crtc, ModeInfo.from_buffer_copy(mode)
        os.close(fd)
    raise RuntimeError('no connected display (HDMI plugged in?)')

# ---------------------------------------------------------------- EGL / GLES2
egl = lib('EGL', 'libEGL.so.1'); gl = lib('GLESv2', 'libGLESv2.so.2')
for f, rt, at in [('eglGetDisplay', C.c_void_p, [C.c_void_p]), ('eglInitialize', C.c_uint, [C.c_void_p, C.c_void_p, C.c_void_p]),
                  ('eglBindAPI', C.c_uint, [C.c_uint]), ('eglGetConfigs', C.c_uint, [C.c_void_p, C.c_void_p, C.c_int, C.POINTER(C.c_int)]),
                  ('eglChooseConfig', C.c_uint, [C.c_void_p, C.POINTER(C.c_int), C.c_void_p, C.c_int, C.POINTER(C.c_int)]),
                  ('eglGetConfigAttrib', C.c_uint, [C.c_void_p, C.c_void_p, C.c_int, C.POINTER(C.c_int)]),
                  ('eglCreateContext', C.c_void_p, [C.c_void_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]),
                  ('eglCreateWindowSurface', C.c_void_p, [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]),
                  ('eglMakeCurrent', C.c_uint, [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]),
                  ('eglSwapBuffers', C.c_uint, [C.c_void_p, C.c_void_p]), ('eglGetError', C.c_int, [])]:
    getattr(egl, f).restype = rt; getattr(egl, f).argtypes = at

def init_egl(gbm_dev, gbm_surf):
    dpy = egl.eglGetDisplay(C.c_void_p(gbm_dev))
    if not dpy or not egl.eglInitialize(dpy, None, None): raise RuntimeError('eglInitialize failed %x' % egl.eglGetError())
    egl.eglBindAPI(0x30A0)   # EGL_OPENGL_ES_API
    attrs = (C.c_int * 13)(0x3033, 4, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 0, 0x3040, 4, 0x3038)
    n = C.c_int(); egl.eglChooseConfig(dpy, attrs, None, 0, C.byref(n))
    cfgs = (C.c_void_p * n.value)(); egl.eglChooseConfig(dpy, attrs, cfgs, n.value, C.byref(n))
    cfg = None
    for k in range(n.value):   # the config must match the GBM surface format
        vid = C.c_int(); egl.eglGetConfigAttrib(dpy, cfgs[k], 0x302E, C.byref(vid))
        if vid.value == GBM_FORMAT_XRGB8888: cfg = cfgs[k]; break
    cfg = cfg or (cfgs[0] if n.value else None)
    if not cfg: raise RuntimeError('no EGL config')
    ctx = egl.eglCreateContext(dpy, cfg, None, (C.c_int * 3)(0x3098, 2, 0x3038))
    surf = egl.eglCreateWindowSurface(dpy, cfg, C.c_void_p(gbm_surf), None)
    if not ctx or not surf or not egl.eglMakeCurrent(dpy, surf, surf, ctx): raise RuntimeError('EGL context/surface failed %x' % egl.eglGetError())
    return dpy, surf

GLf = {'glCreateShader': (C.c_uint, [C.c_uint]), 'glShaderSource': (None, [C.c_uint, C.c_int, C.POINTER(C.c_char_p), C.c_void_p]),
       'glCompileShader': (None, [C.c_uint]), 'glGetShaderiv': (None, [C.c_uint, C.c_uint, C.POINTER(C.c_int)]),
       'glGetShaderInfoLog': (None, [C.c_uint, C.c_int, C.c_void_p, C.c_char_p]), 'glDeleteShader': (None, [C.c_uint]),
       'glCreateProgram': (C.c_uint, []), 'glAttachShader': (None, [C.c_uint, C.c_uint]),
       'glBindAttribLocation': (None, [C.c_uint, C.c_uint, C.c_char_p]), 'glLinkProgram': (None, [C.c_uint]),
       'glGetProgramiv': (None, [C.c_uint, C.c_uint, C.POINTER(C.c_int)]), 'glGetProgramInfoLog': (None, [C.c_uint, C.c_int, C.c_void_p, C.c_char_p]),
       'glUseProgram': (None, [C.c_uint]), 'glGetUniformLocation': (C.c_int, [C.c_uint, C.c_char_p]),
       'glUniform1f': (None, [C.c_int, C.c_float]), 'glUniform2f': (None, [C.c_int, C.c_float, C.c_float]),
       'glUniform1fv': (None, [C.c_int, C.c_int, C.POINTER(C.c_float)]), 'glUniform1i': (None, [C.c_int, C.c_int]),
       'glGenBuffers': (None, [C.c_int, C.POINTER(C.c_uint)]), 'glBindBuffer': (None, [C.c_uint, C.c_uint]),
       'glBufferData': (None, [C.c_uint, C.c_ssize_t, C.c_void_p, C.c_uint]), 'glEnableVertexAttribArray': (None, [C.c_uint]),
       'glVertexAttribPointer': (None, [C.c_uint, C.c_int, C.c_uint, C.c_ubyte, C.c_int, C.c_void_p]),
       'glDrawArrays': (None, [C.c_uint, C.c_int, C.c_int]), 'glViewport': (None, [C.c_int, C.c_int, C.c_int, C.c_int]),
       'glClearColor': (None, [C.c_float] * 4), 'glClear': (None, [C.c_uint]),
       'glGenTextures': (None, [C.c_int, C.POINTER(C.c_uint)]), 'glBindTexture': (None, [C.c_uint, C.c_uint]),
       'glTexImage2D': (None, [C.c_uint, C.c_int, C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_void_p]),
       'glTexParameteri': (None, [C.c_uint, C.c_uint, C.c_int]), 'glActiveTexture': (None, [C.c_uint]),
       'glGenFramebuffers': (None, [C.c_int, C.POINTER(C.c_uint)]), 'glBindFramebuffer': (None, [C.c_uint, C.c_uint]),
       'glFramebufferTexture2D': (None, [C.c_uint, C.c_uint, C.c_uint, C.c_uint, C.c_int]),
       'glCheckFramebufferStatus': (C.c_uint, [C.c_uint]), 'glDeleteProgram': (None, [C.c_uint]), 'glFinish': (None, [])}
for f, (rt, at) in GLf.items(): getattr(gl, f).restype = rt; getattr(gl, f).argtypes = at

HEADER = """precision mediump float;
uniform vec2 u_resolution;uniform float u_time;uniform float u_beat;
uniform float u_knob[6];uniform float u_fader[5];uniform float u_key[8];
uniform float u_good;uniform float u_reset;uniform sampler2D u_prev;
"""
HLINES = HEADER.count('\n')
VS = b'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}'
BLIT = b'precision mediump float;uniform sampler2D t;uniform vec4 r;void main(){gl_FragColor=texture2D(t,(gl_FragCoord.xy-r.xy)/r.zw);}'

def compile_shader(kind, src):
    s = gl.glCreateShader(kind); buf = C.c_char_p(src); gl.glShaderSource(s, 1, C.byref(buf), None); gl.glCompileShader(s)
    ok = C.c_int(); gl.glGetShaderiv(s, 0x8B81, C.byref(ok))
    if not ok.value:
        msg = C.create_string_buffer(4096); gl.glGetShaderInfoLog(s, 4096, None, msg); gl.glDeleteShader(s)
        raise RuntimeError(re.sub(r'0:(\d+)', lambda m: 'line %d' % (int(m.group(1)) - HLINES), msg.value.decode(errors='replace')))
    return s

def program(fs):
    p = gl.glCreateProgram(); gl.glAttachShader(p, compile_shader(0x8B31, VS)); gl.glAttachShader(p, compile_shader(0x8B30, fs))
    gl.glBindAttribLocation(p, 0, b'p'); gl.glLinkProgram(p)
    ok = C.c_int(); gl.glGetProgramiv(p, 0x8B82, C.byref(ok))
    if not ok.value:
        msg = C.create_string_buffer(4096); gl.glGetProgramInfoLog(p, 4096, None, msg); raise RuntimeError(msg.value.decode(errors='replace'))
    return p

# ---------------------------------------------------------------- shaders/index.js
def parse_index_js(text):
    """Pull {name, map, src} entries out of shaders/index.js (JS object literals with template-string sources)."""
    out, i = [], 0
    while True:
        m = re.compile(r"\{\s*name:\s*'((?:[^'\\]|\\.)*)'\s*,").search(text, i)
        if not m: break
        name, j, mp = m.group(1).replace("\\'", "'"), m.end(), {}
        mm = re.compile(r'\s*map:\s*').match(text, j)
        if mm:
            k, depth = mm.end(), 0
            for e in range(k, len(text)):
                depth += {'{': 1, '}': -1}.get(text[e], 0)
                if depth == 0: mp = json.loads(text[k:e + 1]); j = e + 1; break
            j = re.compile(r'\s*,').match(text, j).end()
        ms = re.compile(r'\s*src:\s*`').match(text, j)
        if not ms: i = m.end(); continue
        k, buf = ms.end(), []
        while text[k] != '`':
            if text[k] == '\\': buf.append(text[k + 1]); k += 2
            else: buf.append(text[k]); k += 1
        out.append({'name': name, 'map': mp, 'src': ''.join(buf)}); i = k + 1
    return out

def parse_params(src):
    ps = []
    for m in re.finditer(r'uniform\s+float\s+(p_\w+)\s*;[ \t]*(?://[ \t]*@param\b([^\n]*))?', src):
        t = (m.group(2) or '').split(); nums = []
        for x in t[:3]:
            try: nums.append(float(x))
            except ValueError: break
        lo, hi = (nums[0], nums[1]) if len(nums) >= 2 else (0.0, 1.0)
        ps.append({'name': m.group(1), 'min': lo, 'max': hi, 'def': nums[2] if len(nums) >= 3 else lo})
    return ps

# ---------------------------------------------------------------- controls (UART) and state
class State:
    knob = [0.5] * 6; fader = [0.5] * 5; keys = [0] * 8; taps = [0] * 4; enc = 0; enc0 = 0; reset = 0
    key_rel = [-1e9] * 8; reset_rel = -1e9; held = [False] * 8; reset_held = False
    beat_period = 0.5; beat_origin = 0.0; taps_t = []; last_rx = -1e9; demo_good = 0.0
S = State()

def env(held, rel, now): return 1.0 if held else max(0.0, 1.0 - (now - rel) / 0.2)

def open_uart():
    for dev in ('/dev/serial0', '/dev/ttyAMA0'):
        try:
            fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
            import termios, tty
            tty.setraw(fd); a = termios.tcgetattr(fd); a[4] = a[5] = termios.B115200; termios.tcsetattr(fd, termios.TCSANOW, a)
            log('uart', dev); return fd
        except Exception as e: log('uart', dev, 'unavailable', e)
    return None

def read_uart(fd, buf, now):
    try: data = os.read(fd, 4096)
    except (BlockingIOError, OSError): return buf
    buf += data.decode(errors='ignore')
    *lines, buf = buf.split('\n')
    for line in lines[-4:]:
        p = line.strip().split(',')
        if len(p) < 16 or p[0] != 'V': continue
        try:
            S.knob = [float(x) for x in p[1:7]]; S.fader = [float(x) for x in p[7:12]]
            keys, taps, enc, reset = p[12], p[13], int(p[14]), p[15] == '1'
            for n in range(8):
                h = n < len(keys) and keys[n] == '1'
                if S.held[n] and not h: S.key_rel[n] = now
                S.held[n] = h
            for n in range(4):
                t = n < len(taps) and taps[n] == '1'
                if t and not S.taps[n]: tap(now)
                S.taps[n] = t
            if reset and not S.reset_held: S.enc0 = enc
            if S.reset_held and not reset: S.reset_rel = now
            S.reset_held = reset; S.enc = enc; S.last_rx = now
        except ValueError: pass
    return buf[-512:]

def tap(now):
    S.taps_t = [t for t in S.taps_t if now - t < 2.5] + [now]
    if len(S.taps_t) >= 2: d = [b - a for a, b in zip(S.taps_t, S.taps_t[1:])]; S.beat_period = sum(d) / len(d)
    S.beat_origin = now; S.taps_t = S.taps_t[-5:]

def good(now):
    if now - S.last_rx < 3: return (S.enc - S.enc0) / 24.0
    return S.demo_good

def src_value(sid, now):
    k, _, n = sid.partition(':')
    if k == 'knob': return S.knob[int(n)]
    if k == 'fader': return S.fader[int(n)]
    if k == 'key': return env(S.held[int(n)], S.key_rel[int(n)], now)
    if k == 'good': return 1 - math.exp(-max(good(now), 0) * 0.35)
    if k == 'beat': return ((now - S.beat_origin) / S.beat_period) % 1
    if k == 'reset': return env(S.reset_held, S.reset_rel, now)
    return 0.0

# ---------------------------------------------------------------- main
CFG = {'render': [320, 240], 'mode': [1280, 720], 'cycle_seconds': 45, 'demo_good_per_second': 0.03, 'start': 0}

def main():
    try: CFG.update(json.load(open(os.path.join(DIR, 'config.json'))))
    except (OSError, ValueError) as e: log('config.json not used:', e)
    os.system('systemctl stop getty@tty1.service >/dev/null 2>&1')   # the auto-login console would fight over the screen
    tty = quiet_console()
    fd, conn, crtc, mode = open_drm()
    W, H = mode.hdisplay, mode.vdisplay
    dev = gbm.gbm_create_device(fd)
    surf = gbm.gbm_surface_create(dev, W, H, GBM_FORMAT_XRGB8888, GBM_BO_USE_SCANOUT | GBM_BO_USE_RENDERING)
    dpy, esurf = init_egl(dev, surf)

    shaders = parse_index_js(open(os.path.join(DIR, 'index.js'), encoding='utf-8').read())
    progs = []
    for s in shaders:
        try: progs.append(program((HEADER + s['src']).encode())); log('shader ok', s['name'])
        except RuntimeError as e: progs.append(None); log('shader FAILED', s['name'], e)
    if not any(progs): raise RuntimeError('no shader compiled')
    params = [parse_params(s['src']) for s in shaders]
    blit = program(BLIT)
    loc = {}
    def U(p, n):
        if (p, n) not in loc: loc[(p, n)] = gl.glGetUniformLocation(p, n.encode())
        return loc[(p, n)]

    vbo = C.c_uint(); gl.glGenBuffers(1, C.byref(vbo)); gl.glBindBuffer(0x8892, vbo)
    tri = (C.c_float * 6)(-1, -1, 3, -1, -1, 3); gl.glBufferData(0x8892, C.sizeof(tri), tri, 0x88E4)
    gl.glEnableVertexAttribArray(0); gl.glVertexAttribPointer(0, 2, 0x1406, 0, 0, None)
    RW, RH = CFG['render']
    fbs = []
    for _ in range(2):   # ping-pong render targets at the low "synth" resolution (u_prev = last frame)
        t = C.c_uint(); gl.glGenTextures(1, C.byref(t)); gl.glBindTexture(0x0DE1, t)
        gl.glTexImage2D(0x0DE1, 0, 0x1908, RW, RH, 0, 0x1908, 0x1401, None)
        for k, v in ((0x2801, 0x2600), (0x2800, 0x2600), (0x2802, 0x812F), (0x2803, 0x812F)): gl.glTexParameteri(0x0DE1, k, v)
        f = C.c_uint(); gl.glGenFramebuffers(1, C.byref(f)); gl.glBindFramebuffer(0x8D40, f)
        gl.glFramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, t, 0)
        gl.glClearColor(0, 0, 0, 1); gl.glClear(0x4000); fbs.append((t, f))
    # 4:3 picture, letterboxed in the display mode
    vh = H; vw = H * RW // RH
    if vw > W: vw = W; vh = W * RH // RW
    vx, vy = (W - vw) // 2, (H - vh) // 2

    fb_of = {}
    def fb_for(bo):
        if bo not in fb_of:
            fid = C.c_uint32()
            r = drm.drmModeAddFB(fd, W, H, 24, 32, gbm.gbm_bo_get_stride(bo), gbm.gbm_bo_get_handle(bo).u32, C.byref(fid))
            if len(fb_of) < 4: log('drmModeAddFB ->', r, err() if r else '', 'fb', fid.value, 'stride', gbm.gbm_bo_get_stride(bo))
            fb_of[bo] = fid.value
        return fb_of[bo]
    flip_pending = [False]; use_flip = [CFG.get('page_flip', True)]; conn_arr = (C.c_uint32 * 1)(conn)
    @FLIP_CB
    def on_flip(fd_, frame, sec, usec, data): flip_pending[0] = False
    evctx = EventContext(2, None, on_flip)

    uart = open_uart(); ubuf = ''
    cur = CFG.get('start', 0) % len(shaders); t0 = last = time.monotonic(); switched = t0; prev_bo = None; ping = 0
    frames, fps_t = 0, t0
    log('running', len(shaders), 'shaders, render', RW, 'x', RH, 'on', W, 'x', H)
    while True:
        now = time.monotonic(); dt = min(0.1, now - last); last = now
        if uart is not None: ubuf = read_uart(uart, ubuf, now)
        if now - S.last_rx > 3: S.demo_good += dt * CFG['demo_good_per_second']
        if CFG['cycle_seconds'] and now - switched > CFG['cycle_seconds'] and now - S.last_rx > 3:
            cur = (cur + 1) % len(shaders); switched = now
            while progs[cur] is None: cur = (cur + 1) % len(shaders)
            log('shader ->', shaders[cur]['name'])
        p = progs[cur] or next(x for x in progs if x)
        src_t, dst_f = fbs[ping][0], fbs[1 - ping][1]
        gl.glBindFramebuffer(0x8D40, dst_f); gl.glViewport(0, 0, RW, RH); gl.glUseProgram(p)
        gl.glActiveTexture(0x84C0); gl.glBindTexture(0x0DE1, src_t)
        gl.glUniform1i(U(p, 'u_prev'), 0); gl.glUniform2f(U(p, 'u_resolution'), RW, RH)
        gl.glUniform1f(U(p, 'u_time'), now - t0); gl.glUniform1f(U(p, 'u_beat'), ((now - S.beat_origin) / S.beat_period) % 1)
        gl.glUniform1fv(U(p, 'u_knob'), 6, (C.c_float * 6)(*S.knob)); gl.glUniform1fv(U(p, 'u_fader'), 5, (C.c_float * 5)(*S.fader))
        gl.glUniform1fv(U(p, 'u_key'), 8, (C.c_float * 8)(*[env(S.held[n], S.key_rel[n], now) for n in range(8)]))
        gl.glUniform1f(U(p, 'u_good'), good(now)); gl.glUniform1f(U(p, 'u_reset'), env(S.reset_held, S.reset_rel, now))
        mp = shaders[cur]['map']
        for prm in params[cur]:
            m = mp.get(prm['name']); v = prm['def']
            if m: x = src_value(m['src'], now); v = prm['min'] + (prm['max'] - prm['min']) * ((1 - x) if m.get('inv') else x)
            gl.glUniform1f(U(p, prm['name']), v)
        gl.glDrawArrays(4, 0, 3)
        gl.glBindFramebuffer(0x8D40, 0); gl.glViewport(0, 0, W, H); gl.glClearColor(0, 0, 0, 1); gl.glClear(0x4000)
        gl.glViewport(vx, vy, vw, vh); gl.glUseProgram(blit); gl.glBindTexture(0x0DE1, fbs[1 - ping][0])
        gl.glUniform1i(U(blit, 't'), 0); gl_u4(U(blit, 'r'), vx, vy, vw, vh)
        gl.glDrawArrays(4, 0, 3)
        ping = 1 - ping
        if frames < 1: log('frame 1 drawn, swapping')
        sw = egl.eglSwapBuffers(dpy, esurf)
        bo = gbm.gbm_surface_lock_front_buffer(surf)
        if frames < 1: log('eglSwapBuffers ->', sw, 'front bo', bo)
        fid = fb_for(bo)
        if prev_bo is None or not use_flip[0]:
            r = drm.drmModeSetCrtc(fd, crtc, fid, 0, 0, conn_arr, 1, C.byref(mode))
            if r or frames < 2: log('drmModeSetCrtc ->', r, err() if r else 'ok')
            if not use_flip[0]: time.sleep(max(0, 1 / 60 - (time.monotonic() - now)))
            if prev_bo is not None: gbm.gbm_surface_release_buffer(surf, prev_bo)
        else:
            flip_pending[0] = True
            r = drm.drmModePageFlip(fd, crtc, fid, 1, None)   # DRM_MODE_PAGE_FLIP_EVENT
            if r == 0:
                while flip_pending[0]:
                    rr, _, _ = select.select([fd], [], [], 0.1)
                    if rr: drm.drmHandleEvent(fd, C.byref(evctx))
                    else: break
            else:
                log('drmModePageFlip ->', r, err(), '-> falling back to SetCrtc every frame'); use_flip[0] = False
            gbm.gbm_surface_release_buffer(surf, prev_bo)
        prev_bo = bo
        frames += 1
        if now - fps_t > 10: log('fps %.1f' % (frames / (now - fps_t)), shaders[cur]['name'], 'good %.2f' % good(now)); frames, fps_t = 0, now

_u4 = gl.glUniform4f; _u4.restype = None; _u4.argtypes = [C.c_int] + [C.c_float] * 4
def gl_u4(l, a, b, c, d): _u4(l, a, b, c, d)

if __name__ == '__main__':
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try: faulthandler.enable(open(LOG, 'a'))
    except OSError: pass
    try: main()
    except Exception:
        log('CRASH', traceback.format_exc()); time.sleep(3); sys.exit(1)
