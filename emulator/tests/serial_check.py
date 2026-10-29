#!/usr/bin/env python3
"""Run the emulator's Web Serial check in file:// Chrome, without USB hardware."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / 'orchestra/state/E2/serial_check'
CHROME = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')


def main():
    if not CHROME.is_file():
        sys.exit('Chrome missing: ' + str(CHROME))
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    for folder in ('emulator', 'shaders', 'docs'):
        shutil.copytree(ROOT / folder, SCRATCH / folder)
    tmp = SCRATCH / 'temp'
    tmp.mkdir()
    env = dict(os.environ, TMPDIR=str(tmp), TMP=str(tmp), TEMP=str(tmp))
    page = SCRATCH / 'emulator/index.html'
    # Console exceptions and unhandled asynchronous failures must fail the check too.
    html = page.read_text()
    html = html.replace('<script src="../docs/panel_controls.js">', '''<script>
window.addEventListener('error',e=>console.log('SERIALTEST FAIL: page error: '+e.message));
window.addEventListener('unhandledrejection',e=>console.log('SERIALTEST FAIL: unhandled rejection: '+e.reason));
</script><script src="../docs/panel_controls.js">''', 1)
    page.write_text(html)
    profile = SCRATCH / 'profile'
    log = SCRATCH / 'serial.log'
    try:
        with log.open('w') as stderr, (SCRATCH / 'serial.html').open('w') as stdout:
            result = subprocess.run([
                str(CHROME), '--headless=new', '--use-angle=swiftshader',
                '--enable-unsafe-swiftshader', '--enable-logging=stderr', '--v=0',
                '--no-first-run', '--no-default-browser-check',
                '--user-data-dir=' + str(profile), '--virtual-time-budget=6000',
                '--dump-dom', page.as_uri() + '?serialtest=1',
            ], env=env, stdout=stdout, stderr=stderr, timeout=60)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    text = log.read_text()
    if result.returncode or 'SERIALTEST OK' not in text or 'SERIALTEST FAIL:' in text:
        print(text[-5000:])
        sys.exit('serial check failed (Chrome exit ' + str(result.returncode) + '); see ' + str(log))
    print(re.search(r'SERIALTEST OK \([^"\n]+\)', text).group())
    print('Logs: ' + str(SCRATCH))


if __name__ == '__main__':
    main()
