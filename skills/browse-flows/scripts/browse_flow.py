#!/usr/bin/env python3
"""browse-flows runner: drive a browser tab through a flow of page states, trace every step, yield when stuck.

  browse_flow.py check FLOW.toml
  browse_flow.py run FLOW.toml --tab NAME [--var k=v]... [--trace-dir DIR] [--run DIR] [--dry-run]
                 [--owner-timeout SECONDS] [--max-steps N] [--no-goto]
  browse_flow.py decide RUN_DIR (--click N | --fill N --var NAME | --owner [--says TEXT] | --abort | --learn STATE.json)

A flow is a list of states matched on what the page shows (host, path, visible text, controls), so a run resumes
from wherever the page is. Exit codes: 0 done, 75 yielded (answer with `decide`, then rerun with --run), 3 aborted,
4 owner timeout, 2 usage, flow or browser error. Stdlib only; drives `playwright-cli -s=<tab> run-code`.
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

# One CSS union, evaluated through page.locator(UNION) both to list controls and to act on the k-th: the same
# Playwright engine (it pierces open shadow roots and orders matches in composed-tree order) builds both lists.
UNION = ('button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], '
         '[role=menuitem], [role=menuitemradio], [role=option], [role=tab], [role=checkbox], [role=radio], '
         '[role=combobox], [role=textbox], [role=searchbox]')
DESCRIBE_JS = r"""
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
"""


class FlowError(Exception):
    pass


class ActionRefused(Exception):
    pass


def check_state(s):
    if not s.get('id'):
        raise FlowError('a state needs an id')
    if s.get('kind') not in KINDS:
        raise FlowError(f"state {s['id']}: kind must be one of {sorted(KINDS)}")
    if s['kind'] in AUTO and not s.get('do'):
        raise FlowError(f"state {s['id']}: a {s['kind']} state needs do")
    if s['kind'] not in AUTO and s.get('do'):
        raise FlowError(f"state {s['id']}: a {s['kind']} state never acts; drop do")
    m = s.get('match', {})
    if not isinstance(m.get('text', []), list) or not all(isinstance(x, str) for x in m.get('text', [])):
        raise FlowError(f"state {s['id']}: match.text is a list of strings")
    for c in m.get('controls', []):
        if 'role' not in c:
            raise FlowError(f"state {s['id']}: every match control names a role")
    acts = actions_of(s)
    for i, a in enumerate(acts):
        verb = next(iter(a))
        if verb not in ('click', 'fill', 'press', 'wait'):
            raise FlowError(f"state {s['id']}: unknown action {verb}")
        if verb in ('click', 'press') and i != len(acts) - 1:
            # A click or key press can change the page; later actions would address a stale control list.
            raise FlowError(f"state {s['id']}: {verb} must be the last action in do")


def load_flow(path):
    flow = tomllib.loads(Path(path).read_text())
    for key in ('name', 'hosts', 'state'):
        if key not in flow:
            raise FlowError(f'flow lacks {key!r}')
    ids = set()
    for s in flow['state']:
        check_state(s)
        if s['id'] in ids:
            raise FlowError(f"state id repeated: {s['id']}")
        ids.add(s['id'])
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
    # Order-sensitive: decisions address controls by index, so a reordered page must invalidate them.
    body = json.dumps([fp['host'], fp['path'], [(c['role'], c['name']) for c in fp['controls']]])
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def resolve(spec, fp):
    """The one control an action addresses; None when zero or several match."""
    hits = [c for c in fp['controls'] if control_matches(spec, c)]
    return hits[0] if len(hits) == 1 else None


class PlaywrightCli:
    """Backend over `playwright-cli -s=<tab> run-code`. Raw output stays in memory; only a first error line escapes."""

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
        try:
            res = subprocess.run(['playwright-cli', f'-s={self.tab}', 'run-code', f'--filename={code}'], cwd=self.dir,
                                 capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise FlowError('playwright-cli failed: ' + type(e).__name__)
        text = res.stdout + res.stderr
        if '### Result' not in text:
            first = next((ln for ln in text.splitlines() if ln.strip() and not ln.startswith('###')), 'no result')
            raise FlowError('run-code failed: ' + first[:200])
        return json.loads(text.split('### Result', 1)[1].split('\n### Ran Playwright code', 1)[0].strip())

    def fingerprint(self, texts, capture_headings):
        return self.run("""async page => {
          try { await page.waitForLoadState('domcontentloaded', {timeout: 5000}); } catch (e) {}
          return await page.locator(%s).evaluateAll((all, [texts, heads]) => {%s
            const controls = all.map((e, k) => ({k, e})).filter(x => vis(x.e)).slice(0, 120)
              .map(x => { const role = roleOf(x.e); return {k: x.k, role, name: nameOf(x.e, role)}; });
            const body = (document.body && document.body.innerText || '').toLowerCase();
            const text_hits = {};
            for (const [id, subs] of Object.entries(texts)) text_hits[id] = subs.every(s => body.includes(s.toLowerCase()));
            return {host: location.host, path: location.pathname, window_name: window.name, controls, text_hits,
              headings: heads ? [...document.querySelectorAll('h1,h2')].map(h => h.innerText.trim().slice(0, 80)).filter(Boolean).slice(0, 4) : []};
          }, %s);
        }""" % (json.dumps(UNION), DESCRIBE_JS, json.dumps([texts, capture_headings])))

    def stamp(self):
        return self.run('async page => page.evaluate(n => { window.name = n; return n }, %s)' % json.dumps(self.tab))

    def goto(self, url):
        return self.run('async page => { await page.goto(%s); return page.url().split("?")[0] }' % json.dumps(url))

    def act(self, action, k=None, value=None, expect=None):
        """Act on the k-th control, but only if it is still the expected (role, name) in the expected tab: the
        find and the act are separate run-code calls, and a page that re-rendered in between is refused."""
        if action == 'press':
            out = self.run('async page => { if (await page.evaluate(() => window.name) !== %s) return "refused: tab renamed";'
                           ' await page.keyboard.press(%s); return "pressed" }' % (json.dumps(self.tab), json.dumps(value)))
            if str(out).startswith('refused'):
                raise ActionRefused(out)
            return out
        loc = 'page.locator(%s).nth(%d)' % (json.dumps(UNION), k)
        verb = 'click({timeout: 8000})' if action == 'click' else 'fill(%s, {timeout: 8000})' % json.dumps(value)
        out = self.run("""async page => {
          const [tab, role, name] = %s;
          const got = await %s.evaluate((e, tab) => {%s
            const role = roleOf(e); return {role, name: nameOf(e, role), tab: window.name};
          }, tab);
          if (got.tab !== tab) return 'refused: tab renamed';
          if (got.role !== role || got.name !== name) return 'refused: control changed';
          await %s.%s;
          return %s;
        }""" % (json.dumps([self.tab, expect[0], expect[1]]), loc, DESCRIBE_JS, loc, verb, json.dumps(action + 'ed')))
        if str(out).startswith('refused'):
            raise ActionRefused(out)
        return out


class Run:
    def __init__(self, flow, backend, run_dir, args):
        self.flow, self.backend, self.dir, self.args = flow, backend, Path(run_dir), args
        try:
            self.vars = dict(v.split('=', 1) for v in args.var)
        except ValueError:
            raise FlowError('--var takes name=value')
        for name, spec in flow.get('vars', {}).items():
            if spec.get('required') and name not in self.vars:
                raise FlowError(f'missing --var {name}')
            if name in self.vars and spec.get('pattern') and not re.fullmatch(spec['pattern'], self.vars[name]):
                raise FlowError(f'--var {name} does not match its pattern')
        learned = self.dir / 'learned.jsonl'
        self.states = flow['state'] + ([json.loads(ln) for ln in learned.read_text().splitlines() if ln.strip()]
                                       if learned.exists() else [])
        trace = self.dir / 'trace.jsonl'
        self.step = len(trace.read_text().splitlines()) if trace.exists() else 0

    def trace(self, **rec):
        rec = {'step': self.step, 'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'flow': self.flow['name'], **rec}
        with open(self.dir / 'trace.jsonl', 'a') as f:
            f.write(json.dumps(rec) + '\n')
        self.step += 1

    def fingerprint(self, allow_unnamed=False):
        texts = {s['id']: s['match']['text'] for s in self.states if s.get('match', {}).get('text')}
        fp = self.backend.fingerprint(texts, self.flow.get('capture_headings', True))
        name = fp.get('window_name')
        if name == self.backend.tab:
            return fp
        home = fp['host'] in self.flow['hosts']
        if not name and allow_unnamed and home:
            # An owner's cross-site sign-in clears window.name; an owner wait claims the tab back once it is home.
            self.backend.stamp()
            fp['window_name'] = self.backend.tab
            return fp
        if not name and not home:
            return fp  # mid-SSO on another site: nothing acts off the allowlist, so reading it is safe
        raise FlowError(f"the controller's tab is not named {self.backend.tab}; refusing to drive another tab")

    def matching(self, fp):
        return [s for s in self.states if state_matches(s, fp, self.flow)]

    @staticmethod
    def is_secret(matches):
        return any(s.get('secret') or s['kind'] == 'secret' for s in matches)

    def public(self, fp, secret):
        out = {'host': fp['host'], 'path': fp['path'], 'sig': signature(fp)}
        out['headings'] = [] if secret else fp['headings']
        out['controls'] = [[i, c['role'], '' if secret else c['name']] for i, c in enumerate(fp['controls'])]
        return out

    def yield_to_agent(self, fp, reason, state=None, secret=False):
        secret = secret or self.is_secret(self.matching(fp))
        packet = {'reason': reason, 'state': state, 'page': self.public(fp, secret),
                  'answer': f'browse_flow.py decide {self.dir} (--click N | --fill N --var NAME | --owner | --abort | --learn STATE.json)'}
        (self.dir / 'yield.json').write_text(json.dumps(packet, indent=2))
        self.trace(event='yield', reason=reason, state=state, page=packet['page'])
        print(json.dumps({'yield': reason, 'state': state, 'packet': str(self.dir / 'yield.json')}))
        return YIELDED

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
        """Apply an agent decision to the page it was made on (fp is fresh and its signature matched)."""
        self.trace(event='decision', decision={k: v for k, v in d.items() if k != 'sig'})
        if d['action'] == 'abort':
            return ABORTED
        if d['action'] == 'owner':
            return self.wait_owner(fp, d.get('says') or 'the owner acts in the tab')
        if d['action'] == 'learn':
            check_state(d['state'])
            with open(self.dir / 'learned.jsonl', 'a') as f:
                f.write(json.dumps(d['state']) + '\n')
            self.states.append(d['state'])
            return None
        owner = [s['id'] for s in self.matching(fp) if s['kind'] in OWNER]
        if owner or fp['host'] not in self.flow['hosts']:
            # An agent never clicks or fills an owner-kind page or a page off the allowlist; that is the human's.
            why = f"owner-kind page ({', '.join(owner)})" if owner else f"off-allowlist host {fp['host']}"
            self.trace(event='decision-refused', reason=why)
            return self.wait_owner(fp, f'{why}: the owner acts in the tab')
        if not 0 <= d['control'] < len(fp['controls']):
            raise FlowError('decision names a control outside the packet')
        if d['action'] == 'fill' and d.get('var') not in self.vars:
            raise FlowError(f"decision fills unknown var {d.get('var')!r}")
        ctl = fp['controls'][d['control']]
        try:
            result = self.backend.act(d['action'], ctl['k'], self.vars.get(d.get('var')), (ctl['role'], ctl['name']))
        except (ActionRefused, FlowError) as e:
            self.trace(event='act-failed', by='agent', error=str(e)[:200])
            return self.yield_to_agent(self.fingerprint(), f"{d['action']} failed: {str(e)[:120]}")
        secret = self.is_secret(self.matching(fp))
        self.trace(event='act', by='agent', action=d['action'], control=[ctl['role'], '' if secret else ctl['name']], result=result)
        time.sleep(float(self.flow.get('settle', 1.5)))
        return None

    def wait_owner(self, fp, says):
        print(f'OWNER: {says}', flush=True)
        self.trace(event='owner-wait', says=says)
        sig, deadline = signature(fp), time.time() + self.args.owner_timeout
        while time.time() < deadline:
            time.sleep(5)
            if signature(self.fingerprint(allow_unnamed=True)) != sig:
                self.trace(event='owner-acted')
                return None
        return OWNER_TIMEOUT

    def go(self):
        flow, args = self.flow, self.args
        start = flow.get('start')
        if start and not args.run and not args.no_goto and not args.dry_run:
            # A fresh run always starts at the flow's start URL, so a tab left on an old "done" page can't end it.
            # It navigates, so it needs the named tab itself: an unnamed tab (perhaps the owner's own) is refused.
            if self.fingerprint()['window_name'] != self.backend.tab:
                raise FlowError(f"the controller's tab is not named {self.backend.tab}; refusing to drive another tab")
            self.trace(event='goto', url=start.split('?')[0], result=self.backend.goto(start))
            self.backend.stamp()
            time.sleep(2)
        last, acted = None, False
        for _ in range(args.max_steps):
            fp = self.fingerprint()
            pending = self.decision(fp)
            if pending:
                code = self.apply(pending, fp)
                if code is not None:
                    return code
                acted, last = True, None
                continue
            matches = self.matching(fp)
            ids, secret = [s['id'] for s in matches], self.is_secret(matches)
            self.trace(event='page', matched=ids, page=self.public(fp, secret))
            if fp['host'] not in flow['hosts']:
                reason, state = 'off-allowlist host', None
            elif len(matches) != 1:
                reason, state = ('no state matches' if not matches else 'ambiguous: ' + ', '.join(ids)), None
            else:
                reason, state = None, matches[0]
            if args.dry_run:
                plan = None if reason else {'state': state['id'], 'kind': state['kind'], 'do': actions_of(state)}
                print(json.dumps({'dry_run': True, 'reason': reason, 'plan': plan, 'page': self.public(fp, secret)}))
                return 0
            if reason:
                return self.yield_to_agent(fp, reason, secret=secret)
            if state['kind'] == 'done':
                self.trace(event='done', state=state['id'])
                print(json.dumps({'done': state['id'], 'trace': str(self.dir / 'trace.jsonl')}))
                return 0
            if state['kind'] in OWNER:
                code = self.wait_owner(fp, state.get('owner_says', f"{state['kind']} page: the owner decides"))
                if code is not None:
                    return code
                continue
            if state['kind'] == 'secret':
                return self.yield_to_agent(fp, 'secret fill', state['id'], secret=True)
            if acted and (state['id'], signature(fp)) == last:
                # Never act twice on an unchanged page: a second submit of a one-time code is worse than a yield.
                return self.yield_to_agent(fp, 'page unchanged after acting', state['id'], secret=secret)
            last = (state['id'], signature(fp))
            for a in actions_of(state):
                verb, spec = next(iter(a.items()))
                if verb == 'wait':
                    time.sleep(float(spec))
                    continue
                if verb == 'fill' and spec.get('var') not in self.vars:
                    raise FlowError(f"state {state['id']} fills undeclared var {spec.get('var')!r}")
                try:
                    if verb == 'press':
                        result = self.backend.act('press', value=spec)
                        self.trace(event='act', state=state['id'], action='press', key=spec, result=result)
                        continue
                    ctl = resolve(spec, fp)
                    if ctl is None:
                        return self.yield_to_agent(fp, f'{verb} target not unique or absent', state['id'], secret=secret)
                    result = self.backend.act(verb, ctl['k'], self.vars.get(spec.get('var')), (ctl['role'], ctl['name']))
                    self.trace(event='act', state=state['id'], action=verb,
                               control=[ctl['role'], '' if secret else ctl['name']], result=result)
                except (ActionRefused, FlowError) as e:
                    self.trace(event='act-failed', state=state['id'], error=str(e)[:200])
                    return self.yield_to_agent(self.fingerprint(), f'{verb} failed: {str(e)[:120]}', state['id'])
            acted = True
            time.sleep(float(flow.get('settle', 1.5)))
        return self.yield_to_agent(fp, 'max steps reached')


def positive(text):
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return n


def cmd_decide(args):
    run = Path(args.run_dir)
    packet = json.loads((run / 'yield.json').read_text())
    d = {'sig': packet['page']['sig']}
    n = len(packet['page']['controls'])
    if args.click is not None or args.fill is not None:
        idx = args.click if args.click is not None else args.fill
        if not 0 <= idx < n:
            raise FlowError(f'control {idx} is outside the packet (0..{n - 1})')
        if args.fill is not None and not args.var:
            raise FlowError('--fill needs --var NAME')
        d.update(action='click', control=idx) if args.click is not None else d.update(action='fill', control=idx, var=args.var)
    elif args.owner:
        d.update(action='owner', says=args.says or 'the owner acts in the tab')
    elif args.abort:
        d.update(action='abort')
    else:
        state = json.loads(Path(args.learn).read_text())
        check_state(state)
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
    r.add_argument('--run'); r.add_argument('--dry-run', action='store_true')
    r.add_argument('--owner-timeout', type=float, default=600); r.add_argument('--max-steps', type=positive, default=40)
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
    except (FlowError, tomllib.TOMLDecodeError, json.JSONDecodeError, OSError, KeyError, ValueError) as e:
        print(f'browse-flow: {type(e).__name__}: {e}', file=sys.stderr)
        return USAGE


if __name__ == '__main__':
    raise SystemExit(main())
