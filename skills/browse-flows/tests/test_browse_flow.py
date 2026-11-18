#!/usr/bin/env python3
"""No browser: the runner against a scripted fake page. Matching, policy, tracing, yield and resume."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('browse_flow', HERE.parent / 'scripts' / 'browse_flow.py')
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)
DEVICE = HERE.parent / 'flows' / 'openai-codex-device.toml'


def page(path, controls, host='auth.openai.com', text=None):
    return {'host': host, 'path': path, 'controls': [{'k': i, 'role': r, 'name': n} for i, (r, n) in enumerate(controls)],
            'text': (text or '').lower(), 'headings': []}


class Fake:
    """A page that moves on when the scripted control is clicked, or when the 'owner' advances it."""
    tab = 'sitting'

    def __init__(self, pages, transitions, owner_moves=None):
        self.pages, self.transitions, self.i, self.log = pages, transitions, 0, []
        self.owner_moves = owner_moves or {}
        self.polls = 0

    def fingerprint(self, texts, heads):
        if self.i in self.owner_moves:
            self.polls += 1
            if self.polls >= 2:
                self.i = self.owner_moves.pop(self.i)
        p = self.pages[self.i]
        hits = {sid: all(s.lower() in p['text'] for s in subs) for sid, subs in texts.items()}
        return {**p, 'window_name': self.tab, 'text_hits': hits}

    def act(self, action, k=None, value=None):
        self.log.append((action, k, value))
        nxt = self.transitions.get((self.i, action, k))
        if nxt is not None:
            self.i = nxt
        return action

    def goto(self, url):
        self.log.append(('goto', url))
        return url

    def stamp(self):
        return self.tab

    def permissions(self, origin, grant, deny):
        self.log.append(('permissions', origin, tuple(grant), tuple(deny)))
        return {'granted': grant, 'denied': deny, 'errors': []}


def args(**kw):
    base = dict(var=['user_code=OCME-VHMHU'], dry_run=False, wait=0, owner_timeout=1, max_steps=12, no_goto=False)
    base.update(kw)
    return argparse.Namespace(**base)


def run(fake, **kw):
    d = tempfile.mkdtemp()
    r = bf.Run(bf.load_flow(DEVICE), fake, d, args(**kw))
    bf.time.sleep = lambda s: None
    return r.go(), Path(d), r


class Flow(unittest.TestCase):
    def test_happy_path_with_owner_consent(self):
        pages = [page('/choose-an-account', [('button', 'Select account Xavier x@example.com'), ('button', 'Remove account: x@example.com')]),
                 page('/codex/device', [('textbox', 'Code'), ('button', 'Continue')]),
                 page('/sign-in-with-chatgpt/codex/consent', [('button', 'Continue')]),
                 page('/deviceauth/callback', [], text='Signed in to Codex')]
        fake = Fake(pages, {(0, 'click', 0): 1, (1, 'click', 1): 2}, owner_moves={2: 3})
        code, d, _ = run(fake)
        self.assertEqual(code, 0)
        self.assertIn(('fill', 0, 'OCME-VHMHU'), fake.log)
        self.assertEqual([x for x in fake.log if x[0] == 'click'], [('click', 0, None), ('click', 1, None)])  # never the consent
        events = [json.loads(l)['event'] for l in (d / 'trace.jsonl').read_text().splitlines()]
        self.assertIn('owner-wait', events)
        self.assertEqual(events[-1], 'done')
        self.assertTrue(any(x[0] == 'permissions' and x[3] == ('notifications',) for x in fake.log))

    def test_consent_is_never_clicked(self):
        pages = [page('/sign-in-with-chatgpt/codex/consent', [('button', 'Continue')])]
        fake = Fake(pages, {})
        code, _, _ = run(fake)
        self.assertEqual(code, bf.OWNER_TIMEOUT)
        self.assertFalse([x for x in fake.log if x[0] == 'click'])

    def test_unknown_page_yields_then_resumes_on_decision(self):
        pages = [page('/codex/device/upsell', [('button', 'Not now'), ('button', 'Upgrade')]),
                 page('/deviceauth/callback', [], text='Signed in to Codex')]
        fake = Fake(pages, {(0, 'click', 0): 1})
        code, d, r = run(fake)
        self.assertEqual(code, bf.YIELDED)
        packet = json.loads((d / 'yield.json').read_text())
        self.assertEqual(packet['reason'], 'no state matches')
        self.assertEqual(packet['page']['controls'][0], [0, 'button', 'Not now'])
        bf.main(['decide', str(d), '--click', '0'])
        code2 = bf.Run(bf.load_flow(DEVICE), fake, d, args()).go()
        self.assertEqual(code2, 0)
        self.assertIn(('click', 0, None), fake.log)
        self.assertNotIn(('click', 1, None), fake.log)

    def test_stale_decision_is_ignored(self):
        pages = [page('/codex/device/upsell', [('button', 'Not now')]), page('/elsewhere', [('button', 'Other')])]
        fake = Fake(pages, {})
        code, d, _ = run(fake)
        bf.main(['decide', str(d), '--click', '0'])
        fake.i = 1
        bf.Run(bf.load_flow(DEVICE), fake, d, args()).go()
        self.assertFalse([x for x in fake.log if x[0] == 'click'])
        self.assertIn('decision-stale', (d / 'trace.jsonl').read_text())

    def test_learn_adds_a_state_for_this_run(self):
        pages = [page('/codex/device/upsell', [('button', 'Not now')]),
                 page('/deviceauth/callback', [], text='Signed in to Codex')]
        fake = Fake(pages, {(0, 'click', 0): 1})
        _, d, _ = run(fake)
        learn = d / 'state.json'
        learn.write_text(json.dumps({'id': 'upsell', 'kind': 'dismiss', 'match': {'path': '^/codex/device/upsell'},
                                     'do': {'click': {'role': 'button', 'name': 'Not now'}}}))
        bf.main(['decide', str(d), '--learn', str(learn)])
        self.assertEqual(bf.Run(bf.load_flow(DEVICE), fake, d, args()).go(), 0)
        self.assertTrue((d / 'learned.jsonl').exists())

    def test_off_allowlist_host_yields(self):
        fake = Fake([page('/signin', [('button', 'Continue')], host='accounts.google.com')], {})
        code, d, _ = run(fake, no_goto=True)
        self.assertEqual(code, bf.YIELDED)
        self.assertEqual(json.loads((d / 'yield.json').read_text())['reason'], 'off-allowlist host')

    def test_dry_run_never_acts(self):
        fake = Fake([page('/codex/device', [('textbox', 'Code'), ('button', 'Continue')])], {})
        code, _, _ = run(fake, dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(fake.log, [])

    def test_wrong_tab_refused(self):
        fake = Fake([page('/codex/device', [])], {})
        fake.tab = 'other'
        orig = fake.fingerprint
        fake.fingerprint = lambda t, h: {**orig(t, h), 'window_name': 'someone-else'}
        with self.assertRaises(bf.FlowError):
            run(fake)


class Schema(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False)
        f.write(text)
        f.close()
        return f.name

    def test_consent_state_cannot_act(self):
        with self.assertRaises(bf.FlowError):
            bf.load_flow(self.write('name="x"\nhosts=["a"]\n[[state]]\nid="c"\nkind="consent"\ndo={click={role="button"}}\n'))

    def test_secret_vars_refused(self):
        with self.assertRaises(bf.FlowError):
            bf.load_flow(self.write('name="x"\nhosts=["a"]\n[vars.pw]\nsecret=true\n[[state]]\nid="d"\nkind="done"\n'))

    def test_owner_tab_refused(self):
        with self.assertRaises(bf.FlowError):
            bf.PlaywrightCli('dekopon')


if __name__ == '__main__':
    unittest.main()
