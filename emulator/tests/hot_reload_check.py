#!/usr/bin/env python3
"""Isolated file:// Chrome check; all copied files, profiles and logs stay under E1 scratch."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / 'orchestra/state/E1/hot_reload_check'
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

    def run(label, query, expected):
        profile = SCRATCH / ('profile-' + label)
        log = SCRATCH / (label + '.log')
        with log.open('w') as stderr, (SCRATCH / (label + '.html')).open('w') as stdout:
            result = subprocess.run([
                str(CHROME), '--headless=new', '--use-angle=swiftshader',
                '--enable-unsafe-swiftshader', '--enable-logging=stderr', '--v=0',
                '--no-first-run', '--no-default-browser-check',
                '--user-data-dir=' + str(profile), '--virtual-time-budget=6000',
                '--dump-dom', (SCRATCH / 'emulator/index.html').as_uri() + query,
            ], env=env, stdout=stdout, stderr=stderr, timeout=60)
        text = log.read_text()
        shutil.rmtree(profile, ignore_errors=True)
        if result.returncode or expected not in text or re.search(r'(SELFTEST|SMOKE) FAIL:', text):
            print(text[-5000:])
            sys.exit(label + ' failed; see ' + str(log))
        print(label + ': ' + next(line.split('"')[1] for line in text.splitlines() if expected in line))

    run('selftest', '?selftest=1', 'SELFTEST OK')
    # Observe the normal (no-query) startup on the isolated copy, including real script polling.
    page = SCRATCH / 'emulator/index.html'
    html = page.read_text()
    html = html.replace('<script src="../docs/panel_controls.js">',
                        '''<script>window.smokeErrors=[];window.smokePolls=0;window.addEventListener('error',e=>smokeErrors.push(e.message));
new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes)
  if(n.tagName==='SCRIPT'&&n.src.includes('index.js?t='))smokePolls++}).observe(document.head,{childList:true});</script>\n'''
                        '<script src="../docs/panel_controls.js">', 1)
    html = html.replace('</body>', '''<script>
const initialProgram=progs[curShader()].p;
setTimeout(()=>console.log(smokeErrors.length||shaders[curShader()].name!=='GOOD'||progs.some(p=>p.err)||
  progs[curShader()].p!==initialProgram||liveError||liveBusy||document.hidden||smokePolls<2||
  document.querySelector('script[src*="?t="]')?
  'SMOKE FAIL: '+JSON.stringify({errors:smokeErrors,name:shaders[curShader()].name,liveError,liveBusy,hidden:document.hidden,polls:smokePolls}):
  'SMOKE OK (GOOD compiled, no page errors, file polling unchanged)'),4500);
</script></body>''', 1)
    page.write_text(html)
    run('smoke', '', 'SMOKE OK')
    print('Logs: ' + str(SCRATCH))


if __name__ == '__main__':
    main()
