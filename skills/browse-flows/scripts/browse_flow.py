#!/usr/bin/env python3
"""browse-flows runner: drive a browser tab through a flow of page states, trace every step, yield when stuck.

  browse_flow.py check FLOW.toml
  browse_flow.py run FLOW.toml --tab NAME [--var k=v]... [--trace-dir DIR] [--run DIR] [--dry-run]
                 [--wait SECONDS] [--owner-timeout SECONDS] [--max-steps N] [--no-goto]
  browse_flow.py decide RUN_DIR (--click N | --fill N --var NAME | --owner | --abort | --learn STATE.json)

A flow is a list of states matched on what the page shows (host, path, visible text, controls), so a run resumes
from wherever the page is. Exit codes: 0 done, 75 yielded (answer with `decide`, then rerun with --run), 3 aborted,
4 owner timeout, 2 usage or flow error. Stdlib only; drives `playwright-cli -s=<tab> run-code`.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

AUTO = {'nav', 'dismiss'}
OWNER = {'owner', 'consent', 'payment', 'permission'}
KINDS = AUTO | OWNER | {'secret', 'done'}
YIELDED, ABORTED, OWNER_TIMEOUT, USAGE = 75, 3, 4, 2

# Controls are found in the page by one CSS union, in document order; an action addresses the k-th match.
UNION = ('button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], '
         '[role=menuitem], [role=menuitemradio], [role=option], [role=tab], [role=checkbox], [role=radio], '
         '[role=combobox], [role=textbox], [role=searchbox]')
INVENTORY_JS = r"""
const UNION = %s;
const vis = e => !!(e.offsetParent || e.getClientRects().length);
const roleOf = e => {
  const r = e.getAttribute('role'); if (r) return r;
  const t = e.tagName;
  if (t === 'BUTTON' || t === 'SUMMARY') return 'button';
  if (t === 'A') return 'link';
  if (t === 'SELECT') return 'combobox';
  if (t === 'TEXTAREA') return 'textbox';
  if (t === 'INPUT') return ({checkbox: 'checkbox', radio: 'radio', submit: 'button', button: 'button',
    password: 'password', search: 'searchbox'})[e.type] || 'textbox';
  return 'generic';
};
const nameOf = (e, role) => {
  const by = e.getAttribute('aria-labelledby');
  const n = e.getAttribute('aria-label') || (by && by.split(' ').map(i => document.getElementById(i)?.innerText || '').join(' '))
    || (e.labels && e.labels[0] && e.labels[0].innerText)
    || (['textbox', 'password', 'searchbox', 'combobox'].includes(role) ? e.placeholder : e.innerText)
    || e.title || (e.tagName === 'INPUT' && ['submit', 'button'].includes(e.type) ? e.value : '') || '';
  return n.trim().replace(/\s+/g, ' ').slice(0, 80);
};
const all = [...document.querySelectorAll(UNION)];
const inventory = all.map((e, k) => ({k, e})).filter(x => vis(x.e)).slice(0, 120)
  .map(x => { const role = roleOf(x.e); return {k: x.k, role, name: nameOf(x.e, role)}; });
""" % json.dumps(UNION)


class FlowError(Exception):
    pass


def load_flow(path):
    flow = tomllib.loads(Path(path).read_text())
    for key in ('name', 'hosts', 'state'):
        if key not in flow:
            raise FlowError(f'flow lacks {key!r}')
    ids = set()
    for s in flow['state']:
        if s.get('id') in ids or not s.get('id'):
            raise FlowError(f'state id missing or repeated: {s.get("id")!r}')
        ids.add(s['id'])
        if s.get('kind') not in KINDS:
            raise FlowError(f"state {s['id']}: kind must be one of {sorted(KINDS)}")
        if s['kind'] in AUTO and not s.get('do'):
            raise FlowError(f"state {s['id']}: a {s['kind']} state needs do")
        if s['kind'] in OWNER | {'done', 'secret'} and s.get('do'):
            raise FlowError(f"state {s['id']}: a {s['kind']} state never acts; drop do")
        for c in s.get('match', {}).get('controls', []):
            if 'role' not in c:
                raise FlowError(f"state {s['id']}: every match control names a role")
    for name, spec in flow.get('vars', {}).items():
        if spec.get('secret'):
            raise FlowError(f'var {name}: secret values never enter page code; use a secret state that yields')
    return flow


def actions_of(state):
    do = state.get('do', [])
    return do if isinstance(do, list) else [do]


def control_matches(spec, ctl):
    if spec['role'] != ctl['role']:
        return False
    if 'name' in spec and spec['name'] != ctl['name']:
        return False
    if 'name_re' in spec and not re.search(spec['name_re'], ctl['name']):
        return False
    return True


def state_matches(state, fp, flow):
    m = state.get('match', {})
    if fp['host'] not in m.get('hosts', flow['hosts']):
        return False
    if 'path' in m and not re.search(m['path'], fp['path']):
        return False
    if m.get('text') and not fp['text_hits'].get(state['id']):
        return False
    return all(any(control_matches(spec, c) for c in fp['controls']) for spec in m.get('controls', []))


def signature(fp):
    body = json.dumps([fp['host'], fp['path'], sorted((c['role'], c['name']) for c in fp['controls'])])
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def resolve(spec, fp):
    """The one control an action addresses; None when zero or several match."""
    hits = [c for c in fp['controls'] if control_matches(spec, c)]
    return hits[0] if len(hits) == 1 else None


class PlaywrightCli:
    """Backend over `playwright-cli -s=<tab> run-code`. Raw output stays in a private temp dir and is deleted."""

    def __init__(self, tab):
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', tab) or tab == 'dekopon':
            raise FlowError("--tab must be a purpose tab name, never the owner's 'dekopon' controller")
        self.tab = tab
        self.dir = tempfile.mkdtemp(prefix='browse-flow-')
        os.chmod(self.dir, 0o700)

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run(self, body):
        code = os.path.join(self.dir, 'code.js')
        with open(code, 'w') as f:
            f.write(body)
        res = subprocess.run(['playwright-cli', f'-s={self.tab}', 'run-code', f'--filename={code}'], cwd=self.dir,
                             capture_output=True, text=True, timeout=120)
        shutil.rmtree(os.path.join(self.dir, '.playwright-cli'), ignore_errors=True)
        text = res.stdout + res.stderr
        if '### Result' not in text:
            first = next((ln for ln in text.splitlines() if ln.strip() and not ln.startswith('###')), 'no result')
            raise FlowError('run-code failed: ' + first[:200])
        return json.loads(text.split('### Result', 1)[1].split('### Ran', 1)[0].strip())

    def fingerprint(self, texts, capture_headings):
        return self.run('async page => await page.evaluate(([texts, heads]) => {' + INVENTORY_JS + """
          const body = (document.body && document.body.innerText || '').toLowerCase();
          const text_hits = {};
          for (const [id, subs] of Object.entries(texts)) text_hits[id] = subs.every(s => body.includes(s.toLowerCase()));
          return {host: location.host, path: location.pathname, window_name: window.name, controls: inventory, text_hits,
            headings: heads ? [...document.querySelectorAll('h1,h2')].map(h => h.innerText.trim().slice(0, 80)).filter(Boolean).slice(0, 4) : []};
        }, %s)""" % json.dumps([texts, capture_headings]))

    def stamp(self):
        return self.run('async page => page.evaluate(n => { window.name = n; return n }, %s)' % json.dumps(self.tab))

    def goto(self, url):
        return self.run('async page => { await page.goto(%s); return page.url().split("?")[0] }' % json.dumps(url))

    def act(self, action, k=None, value=None):
        loc = 'page.locator(%s).nth(%d)' % (json.dumps(UNION), k if k is not None else -1)
        if action == 'click':
            body = f'async page => {{ await {loc}.click({{timeout: 8000}}); return "clicked" }}'
        elif action == 'fill':
            body = f'async page => {{ await {loc}.fill({json.dumps(value)}, {{timeout: 8000}}); return "filled" }}'
        elif action == 'press':
            body = f'async page => {{ await page.keyboard.press({json.dumps(value)}); return "pressed" }}'
        else:
            raise FlowError(f'unknown action {action}')
        return self.run(body)

    def permissions(self, origin, grant, deny):
        return self.run("""async page => {
          const out = {granted: [], denied: [], errors: []};
          if (%(grant)s.length) { try { await page.context().grantPermissions(%(grant)s, {origin: %(origin)s}); out.granted = %(grant)s; }
            catch (e) { out.errors.push('grant: ' + String(e).split('\\n')[0]); } }
          if (%(deny)s.length) { try { const s = await page.context().browser().newBrowserCDPSession();
              for (const name of %(deny)s) { await s.send('Browser.setPermission', {permission: {name}, setting: 'denied', origin: %(origin)s}); out.denied.push(name); }
              await s.detach(); } catch (e) { out.errors.push('deny: ' + String(e).split('\\n')[0]); } }
          return out; }""" % {'grant': json.dumps(grant), 'deny': json.dumps(deny), 'origin': json.dumps(origin)})


class Run:
    def __init__(self, flow, backend, run_dir, args):
        self.flow, self.backend, self.dir, self.args = flow, backend, Path(run_dir), args
        self.vars = dict(v.split('=', 1) for v in args.var)
        for name, spec in flow.get('vars', {}).items():
            if spec.get('required') and name not in self.vars:
                raise FlowError(f'missing --var {name}')
            if name in self.vars and spec.get('pattern') and not re.fullmatch(spec['pattern'], self.vars[name]):
                raise FlowError(f'--var {name} does not match its pattern')
        learned = self.dir / 'learned.jsonl'
        self.states = flow['state'] + ([json.loads(ln) for ln in learned.read_text().splitlines() if ln.strip()]
                                       if learned.exists() else [])
        self.step = sum(1 for _ in open(self.dir / 'trace.jsonl')) if (self.dir / 'trace.jsonl').exists() else 0

    def trace(self, **rec):
        rec = {'step': self.step, 'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'flow': self.flow['name'], **rec}
        with open(self.dir / 'trace.jsonl', 'a') as f:
            f.write(json.dumps(rec) + '\n')
        self.step += 1

    def fingerprint(self):
        texts = {s['id']: s['match']['text'] for s in self.states if s.get('match', {}).get('text')}
        fp = self.backend.fingerprint(texts, self.flow.get('capture_headings', True))
        if fp.get('window_name') != self.backend.tab:
            raise FlowError(f"the controller's tab is not named {self.backend.tab}; refusing to drive another tab")
        return fp

    def public(self, fp, secret=False):
        out = {'host': fp['host'], 'path': fp['path'], 'sig': signature(fp)}
        if not secret:
            out['headings'] = fp['headings']
            out['controls'] = [[i, c['role'], c['name']] for i, c in enumerate(fp['controls'])]
        else:
            out['controls'] = [[i, c['role'], ''] for i, c in enumerate(fp['controls'])]
        return out

    def yield_to_agent(self, fp, reason, state=None):
        packet = {'reason': reason, 'state': state, 'page': self.public(fp, secret=state_secret(self.states, state)),
                  'answer': f'browse_flow.py decide {self.dir} (--click N | --fill N --var NAME | --owner | --abort | --learn STATE.json)'}
        (self.dir / 'yield.json').write_text(json.dumps(packet, indent=2))
        self.trace(event='yield', reason=reason, state=state, page=packet['page'])
        print(json.dumps({'yield': reason, 'state': state, 'packet': str(self.dir / 'yield.json')}))
        if not self.args.wait:
            return None
        deadline = time.time() + self.args.wait
        while time.time() < deadline:
            d = self.decision(fp)
            if d:
                return d
            time.sleep(2)
        return None

    def decision(self, fp):
        path = self.dir / 'decision.json'
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        path.unlink()
        if d.get('sig') != signature(fp):
            self.trace(event='decision-stale', decision=d.get('action'))
            return None
        return d

    def apply(self, d, fp):
        self.trace(event='decision', decision={k: v for k, v in d.items() if k != 'sig'})
        if d['action'] == 'abort':
            return ABORTED
        if d['action'] == 'owner':
            return self.wait_owner(fp, d.get('says', 'the owner acts in the tab'))
        if d['action'] == 'learn':
            with open(self.dir / 'learned.jsonl', 'a') as f:
                f.write(json.dumps(d['state']) + '\n')
            self.states.append(d['state'])
            return None
        ctl = fp['controls'][d['control']]
        if d['action'] == 'fill' and d.get('var') not in self.vars:
            raise FlowError(f"decision fills unknown var {d.get('var')!r}")
        value = self.vars[d['var']] if d['action'] == 'fill' else None
        self.trace(event='act', by='agent', action=d['action'], control=[ctl['role'], ctl['name']],
                   result=self.backend.act(d['action'], ctl['k'], value))
        time.sleep(1.5)
        return None

    def wait_owner(self, fp, says):
        print(f'OWNER: {says}', flush=True)
        self.trace(event='owner-wait', says=says)
        sig, deadline = signature(fp), time.time() + self.args.owner_timeout
        while time.time() < deadline:
            time.sleep(5)
            if signature(self.fingerprint()) != sig:
                self.trace(event='owner-acted')
                return None
        return OWNER_TIMEOUT

    def go(self):
        flow, args = self.flow, self.args
        fp = self.fingerprint()
        start = flow.get('start')
        if start and not args.no_goto and not args.dry_run and fp['host'] not in flow['hosts']:
            self.trace(event='goto', url=start.split('?')[0], result=self.backend.goto(start))
            self.backend.stamp()
            time.sleep(2)
        perms = flow.get('permissions', {})
        if not args.dry_run and (perms.get('grant') or perms.get('deny')) and start:
            origin = re.match(r'https?://[^/]+', start).group(0)
            self.trace(event='permissions', result=self.backend.permissions(origin, perms.get('grant', []), perms.get('deny', [])))
        repeats, last = 0, None
        for _ in range(args.max_steps):
            fp = self.fingerprint()
            pending = self.decision(fp)
            if pending:
                code = self.apply(pending, fp)
                if code is not None:
                    return code
                continue
            matches = [s for s in self.states if state_matches(s, fp, flow)]
            ids = [s['id'] for s in matches]
            self.trace(event='page', matched=ids, page=self.public(fp, secret=any(s.get('secret') for s in matches)))
            if fp['host'] not in flow['hosts']:
                reason, state = 'off-allowlist host', None
            elif len(matches) != 1:
                reason, state = ('no state matches' if not matches else 'ambiguous: ' + ', '.join(ids)), None
            else:
                reason, state = None, matches[0]
            if args.dry_run:
                plan = None if reason else {'state': state['id'], 'kind': state['kind'], 'do': actions_of(state)}
                print(json.dumps({'dry_run': True, 'reason': reason, 'plan': plan, 'page': self.public(fp)}))
                return 0
            if reason:
                d = self.yield_to_agent(fp, reason)
                if not d:
                    return YIELDED
                code = self.apply(d, fp)
                if code is not None:
                    return code
                continue
            repeats = repeats + 1 if (state['id'], signature(fp)) == last else 0
            last = (state['id'], signature(fp))
            if state['kind'] == 'done':
                self.trace(event='done', state=state['id'])
                print(json.dumps({'done': state['id'], 'trace': str(self.dir / 'trace.jsonl')}))
                return 0
            if state['kind'] in OWNER:
                code = self.wait_owner(fp, state.get('owner_says', f"{state['kind']} page: the owner decides"))
                if code is not None:
                    return code
                continue
            if state['kind'] == 'secret' or repeats >= 2:
                d = self.yield_to_agent(fp, 'secret fill' if state['kind'] == 'secret' else 'page unchanged after acting',
                                        state['id'])
                if not d:
                    return YIELDED
                code = self.apply(d, fp)
                if code is not None:
                    return code
                continue
            for a in actions_of(state):
                verb = next(iter(a))
                spec = a[verb]
                if verb == 'wait':
                    time.sleep(float(spec))
                    continue
                if verb == 'press':
                    self.trace(event='act', state=state['id'], action='press', key=spec, result=self.backend.act('press', value=spec))
                    continue
                ctl = resolve(spec, fp)
                if ctl is None:
                    d = self.yield_to_agent(fp, f'{verb} target not unique or absent', state['id'])
                    if not d:
                        return YIELDED
                    code = self.apply(d, fp)
                    if code is not None:
                        return code
                    break
                value = self.vars[spec['var']] if verb == 'fill' else None
                self.trace(event='act', state=state['id'], action=verb, control=[ctl['role'], ctl['name']],
                           result=self.backend.act(verb, ctl['k'], value))
            time.sleep(float(flow.get('settle', 1.5)))
        self.yield_to_agent(fp, 'max steps reached')
        return YIELDED


def state_secret(states, sid):
    return any(s['id'] == sid and s.get('secret') for s in states)


def cmd_decide(args):
    run = Path(args.run_dir)
    packet = json.loads((run / 'yield.json').read_text())
    d = {'sig': packet['page']['sig']}
    if args.click is not None:
        d.update(action='click', control=args.click)
    elif args.fill is not None:
        d.update(action='fill', control=args.fill, var=args.var)
    elif args.owner:
        d.update(action='owner', says=args.says or 'the owner acts in the tab')
    elif args.abort:
        d.update(action='abort')
    elif args.learn:
        state = json.loads(Path(args.learn).read_text())
        if state.get('kind') not in KINDS:
            raise FlowError('learned state needs a valid kind')
        d.update(action='learn', state=state)
    (run / 'decision.json').write_text(json.dumps(d))
    print(json.dumps({'decided': d['action'], 'run': str(run)}))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check'); c.add_argument('flow')
    r = sub.add_parser('run'); r.add_argument('flow'); r.add_argument('--tab', required=True)
    r.add_argument('--var', action='append', default=[]); r.add_argument('--trace-dir', default=os.path.expanduser('~/.cache/browse-flows'))
    r.add_argument('--run'); r.add_argument('--dry-run', action='store_true'); r.add_argument('--wait', type=float, default=0)
    r.add_argument('--owner-timeout', type=float, default=600); r.add_argument('--max-steps', type=int, default=40)
    r.add_argument('--no-goto', action='store_true')
    d = sub.add_parser('decide'); d.add_argument('run_dir')
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument('--click', type=int); g.add_argument('--fill', type=int); g.add_argument('--owner', action='store_true')
    g.add_argument('--abort', action='store_true'); g.add_argument('--learn')
    d.add_argument('--var'); d.add_argument('--says')
    args = p.parse_args(argv)
    try:
        if args.cmd == 'check':
            flow = load_flow(args.flow)
            print(json.dumps({'flow': flow['name'], 'states': [s['id'] for s in flow['state']]}))
            return 0
        if args.cmd == 'decide':
            return cmd_decide(args)
        flow = load_flow(args.flow)
        run_dir = Path(args.run) if args.run else Path(args.trace_dir) / f"{flow['name']}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
        run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        backend = PlaywrightCli(args.tab)
        try:
            return Run(flow, backend, run_dir, args).go()
        finally:
            backend.close()
    except (FlowError, tomllib.TOMLDecodeError) as e:
        print(f'browse-flow: {e}', file=sys.stderr)
        return USAGE


if __name__ == '__main__':
    raise SystemExit(main())
