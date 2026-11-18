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
bf.time.sleep = lambda s: None
DEVICE = HERE.parent / 'flows' / 'openai-codex-device.toml'
CODE = 'ABCD-EFGHI'


def page(path, controls, host='auth.openai.com', text=None):
    return {'host': host, 'path': path, 'controls': [{'k': i, 'role': r, 'name': n} for i, (r, n) in enumerate(controls)],
            'text': (text or '').lower(), 'headings': ['Heading']}


class Fake:
    """A page that moves on when a scripted control is clicked, or when the 'owner' advances it."""
    tab = 'sitting'

    def __init__(self, pages, transitions, owner_moves=None, fail=None, window_name=None, sso=False):
        self.pages, self.transitions, self.i, self.log = pages, transitions, 0, []
        self.owner_moves, self.fail, self.window_name, self.polls = owner_moves or {}, fail or set(), window_name, 0
        self.sso, self.name = sso, self.tab  # sso: the owner's move went through another site, clearing window.name

    def fingerprint(self, texts, heads):
        if self.i in self.owner_moves:
            self.polls += 1
            if self.polls >= 2:
                self.i = self.owner_moves.pop(self.i)
                if self.sso:
                    self.name = ''
        p = self.pages[self.i]
        hits = {sid: all(s.lower() in p['text'] for s in subs) for sid, subs in texts.items()}
        name = self.window_name(self) if self.window_name else self.name
        return {**p, 'window_name': name, 'text_hits': hits}

    def act(self, action, k=None, value=None, expect=None):
        if action != 'press':
            ctl = self.pages[self.i]['controls'][k]
            if (ctl['role'], ctl['name']) != tuple(expect):
                raise bf.ActionRefused('refused: control changed')
            if (self.i, action, k) in self.fail:
                raise bf.ActionRefused('refused: overlay intercepts')
        self.log.append((action, k, value))
        nxt = self.transitions.get((self.i, action, k))
        if nxt is not None:
            self.i = nxt
        return action

    def goto(self, url):
        self.log.append(('goto', url))
        return url

    def stamp(self):
        self.log.append(('stamp',))
        self.name = self.tab
        return self.tab


def args(**kw):
    base = dict(var=[f'user_code={CODE}'], dry_run=False, owner_timeout=1, max_steps=12, no_goto=True, run=None)
    base.update(kw)
    return argparse.Namespace(**base)


def run(fake, d=None, **kw):
    d = d or tempfile.mkdtemp()
    return bf.Run(bf.load_flow(DEVICE), fake, d, args(**kw)).go(), Path(d)


def clicks(fake):
    return [x for x in fake.log if x[0] == 'click']


CONSENT = page('/sign-in-with-chatgpt/codex/consent', [('button', 'Continue')])
DONE = page('/deviceauth/callback', [], text='Signed in to Codex')


class Flow(unittest.TestCase):
    def test_happy_path_with_owner_consent(self):
        pages = [page('/choose-an-account', [('button', 'Select account Pat x@example.com'), ('button', 'Remove account: x@example.com')]),
                 page('/codex/device', [('textbox', 'Code'), ('button', 'Continue')]), CONSENT, DONE]
        fake = Fake(pages, {(0, 'click', 0): 1, (1, 'click', 1): 2}, owner_moves={2: 3})
        code, d = run(fake, no_goto=False)
        self.assertEqual(code, 0)
        self.assertEqual(fake.log[0][0], 'goto')  # a fresh run always starts at the flow's start URL
        self.assertIn(('fill', 0, CODE), fake.log)
        self.assertEqual(clicks(fake), [('click', 0, None), ('click', 1, None)])  # never the consent
        events = [json.loads(ln)['event'] for ln in (d / 'trace.jsonl').read_text().splitlines()]
        self.assertIn('owner-wait', events)
        self.assertEqual(events[-1], 'done')

    def test_consent_is_never_clicked(self):
        fake = Fake([CONSENT], {})
        code, _ = run(fake)
        self.assertEqual(code, bf.OWNER_TIMEOUT)
        self.assertFalse(clicks(fake))

    def test_unknown_page_yields_then_resumes_on_decision(self):
        fake = Fake([page('/codex/device/upsell', [('button', 'Not now'), ('button', 'Upgrade')]), DONE], {(0, 'click', 0): 1})
        code, d = run(fake)
        self.assertEqual(code, bf.YIELDED)
        packet = json.loads((d / 'yield.json').read_text())
        self.assertEqual(packet['reason'], 'no state matches')
        self.assertEqual(packet['page']['controls'][0], [0, 'button', 'Not now'])
        bf.main(['decide', str(d), '--click', '0'])
        self.assertEqual(run(fake, d, run=str(d))[0], 0)
        self.assertEqual(clicks(fake), [('click', 0, None)])

    def test_stale_decision_is_ignored(self):
        fake = Fake([page('/codex/device/upsell', [('button', 'Not now')]), page('/elsewhere', [('button', 'Other')])], {})
        _, d = run(fake)
        bf.main(['decide', str(d), '--click', '0'])
        fake.i = 1
        run(fake, d, run=str(d))
        self.assertFalse(clicks(fake))
        self.assertIn('decision-stale', (d / 'trace.jsonl').read_text())

    def test_reordered_page_makes_a_decision_stale(self):
        a = page('/codex/device/upsell', [('button', 'Not now'), ('button', 'Upgrade')])
        b = page('/codex/device/upsell', [('button', 'Upgrade'), ('button', 'Not now')])
        fake = Fake([a, b], {})
        _, d = run(fake)
        bf.main(['decide', str(d), '--click', '0'])
        fake.i = 1
        run(fake, d, run=str(d))
        self.assertFalse(clicks(fake))

    def test_learn_adds_a_state_for_this_run(self):
        fake = Fake([page('/codex/device/upsell', [('button', 'Not now')]), DONE], {(0, 'click', 0): 1})
        _, d = run(fake)
        learn = d / 'state.json'
        learn.write_text(json.dumps({'id': 'upsell', 'kind': 'dismiss', 'match': {'path': '^/codex/device/upsell'},
                                     'do': {'click': {'role': 'button', 'name': 'Not now'}}}))
        bf.main(['decide', str(d), '--learn', str(learn)])
        self.assertEqual(run(fake, d, run=str(d))[0], 0)
        self.assertTrue((d / 'learned.jsonl').exists())

    def test_agent_click_refused_on_owner_kind_page(self):
        # A learned nav state that also matches the consent page makes it ambiguous; the agent's click is refused.
        fake = Fake([CONSENT], {})
        d = Path(tempfile.mkdtemp())
        (d / 'learned.jsonl').write_text(json.dumps({'id': 'cont', 'kind': 'nav', 'match': {'path': '^/sign-in'},
                                                     'do': {'click': {'role': 'button', 'name': 'Continue'}}}) + '\n')
        run(fake, d)
        self.assertEqual(json.loads((d / 'yield.json').read_text())['reason'], 'ambiguous: consent, cont')
        bf.main(['decide', str(d), '--click', '0'])
        self.assertEqual(run(fake, d, run=str(d))[0], bf.OWNER_TIMEOUT)
        self.assertFalse(clicks(fake))
        self.assertIn('decision-refused', (d / 'trace.jsonl').read_text())

    def test_agent_click_refused_off_allowlist(self):
        fake = Fake([page('/signin', [('button', 'Continue')], host='accounts.google.com')], {})
        code, d = run(fake)
        self.assertEqual((code, json.loads((d / 'yield.json').read_text())['reason']), (bf.YIELDED, 'off-allowlist host'))
        bf.main(['decide', str(d), '--click', '0'])
        run(fake, d, run=str(d))
        self.assertFalse(clicks(fake))

    def test_resume_does_not_navigate(self):
        fake = Fake([page('/codex/device/upsell', [('button', 'Not now')])], {})
        _, d = run(fake)
        run(fake, d, run=str(d), no_goto=False)
        self.assertFalse([x for x in fake.log if x[0] == 'goto'])

    def test_failed_action_yields_instead_of_dying(self):
        fake = Fake([page('/codex/device', [('textbox', 'Code'), ('button', 'Continue')])], {}, fail={(0, 'click', 1)})
        code, d = run(fake)
        self.assertEqual(code, bf.YIELDED)
        self.assertTrue(json.loads((d / 'yield.json').read_text())['reason'].startswith('click failed'))

    def test_changed_control_is_refused_at_act_time(self):
        fake = Fake([page('/codex/device', [('textbox', 'Code'), ('button', 'Continue')])], {})
        real_act = fake.act

        def swap_then_act(action, k=None, value=None, expect=None):
            if action == 'click':
                fake.pages[0] = page('/codex/device', [('textbox', 'Code'), ('button', 'Upgrade')])
            return real_act(action, k, value, expect)
        fake.act = swap_then_act
        code, _ = run(fake)
        self.assertEqual(code, bf.YIELDED)
        self.assertFalse(clicks(fake))

    def test_never_acts_twice_on_an_unchanged_page(self):
        fake = Fake([page('/codex/device', [('textbox', 'Code'), ('button', 'Continue')])], {})
        code, d = run(fake)
        self.assertEqual(code, bf.YIELDED)
        self.assertEqual(len(clicks(fake)), 1)
        self.assertEqual(json.loads((d / 'yield.json').read_text())['reason'], 'page unchanged after acting')

    def test_secret_pages_are_redacted_everywhere(self):
        flow = Path(tempfile.mkdtemp()) / 'f.toml'
        flow.write_text('name="s"\nhosts=["h"]\n[[state]]\nid="pw"\nkind="secret"\nmatch={path="^/pw"}\n'
                        '[[state]]\nid="pw2"\nkind="secret"\nmatch={path="^/pw"}\n')
        fake = Fake([page('/pw', [('button', 'hunter2-in-a-label')], host='h')], {})
        d = Path(tempfile.mkdtemp())
        bf.Run(bf.load_flow(flow), fake, d, args(var=[])).go()  # ambiguous between two secret states
        for f in ('trace.jsonl', 'yield.json'):
            self.assertNotIn('hunter2', (d / f).read_text())
            self.assertNotIn('Heading', (d / f).read_text())

    def test_unnamed_tab_after_sso_is_reclaimed_during_owner_wait(self):
        fake = Fake([CONSENT, DONE], {}, owner_moves={0: 1}, sso=True)
        code, _ = run(fake)
        self.assertEqual(code, 0)
        self.assertIn(('stamp',), fake.log)

    def test_fallback_yields_are_redacted_on_secret_pages(self):
        flow = Path(tempfile.mkdtemp()) / 'f.toml'
        flow.write_text('name="s"\nhosts=["h"]\n[[state]]\nid="admin"\nkind="nav"\nsecret=true\nmatch={path="^/admin"}\n'
                        'do={click={role="button",name="Save"}}\n')
        p = page('/admin', [('button', 'Save'), ('button', 'hunter2-in-a-label')], host='h')
        p['headings'] = ['admin password: hunter2']
        fake = Fake([p], {}, fail={(0, 'click', 0)})
        d = Path(tempfile.mkdtemp())
        self.assertEqual(bf.Run(bf.load_flow(flow), fake, d, args(var=[])).go(), bf.YIELDED)
        for f in ('trace.jsonl', 'yield.json'):
            self.assertNotIn('hunter2', (d / f).read_text())

    def test_click_timeout_yields(self):
        fake = Fake([page('/codex/device', [('textbox', 'Code'), ('button', 'Continue')])], {})
        real_act = fake.act

        def timeout(action, k=None, value=None, expect=None):
            if action == 'click':
                raise bf.FlowError('run-code failed: TimeoutError: locator.click: Timeout 8000ms exceeded')
            return real_act(action, k, value, expect)
        fake.act = timeout
        code, d = run(fake)
        self.assertEqual(code, bf.YIELDED)
        self.assertTrue(json.loads((d / 'yield.json').read_text())['reason'].startswith('click failed'))

    def test_resume_refuses_an_unnamed_tab_at_home(self):
        fake = Fake([page('/codex/device/upsell', [('button', 'Not now')])], {}, window_name=lambda f: '')
        with self.assertRaises(bf.FlowError):
            run(fake, run='x')

    def test_max_steps_must_be_positive(self):
        with self.assertRaises(SystemExit):
            bf.main(['run', str(DEVICE), '--tab', 'sitting', '--max-steps', '0'])

    def test_dry_run_never_acts(self):
        fake = Fake([page('/codex/device', [('textbox', 'Code'), ('button', 'Continue')])], {})
        code, _ = run(fake, dry_run=True, no_goto=False)
        self.assertEqual((code, fake.log), (0, []))

    def test_wrong_tab_refused(self):
        fake = Fake([page('/codex/device', [])], {}, window_name=lambda f: 'someone-else')
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

    def test_click_must_be_last(self):
        with self.assertRaises(bf.FlowError):
            bf.load_flow(self.write('name="x"\nhosts=["a"]\n[[state]]\nid="n"\nkind="nav"\n'
                                    'do=[{click={role="button",name="A"}},{click={role="button",name="B"}}]\n'))

    def test_secret_vars_refused(self):
        with self.assertRaises(bf.FlowError):
            bf.load_flow(self.write('name="x"\nhosts=["a"]\n[vars.pw]\nsecret=true\n[[state]]\nid="d"\nkind="done"\n'))

    def test_owner_tab_refused(self):
        with self.assertRaises(bf.FlowError):
            bf.PlaywrightCli('dekopon')

    def test_decide_refuses_out_of_range(self):
        d = Path(tempfile.mkdtemp())
        (d / 'yield.json').write_text(json.dumps({'page': {'sig': 'x', 'controls': [[0, 'button', 'A']]}}))
        self.assertEqual(bf.main(['decide', str(d), '--click', '-1']), bf.USAGE)
        self.assertEqual(bf.main(['decide', str(d), '--click', '1']), bf.USAGE)


if __name__ == '__main__':
    unittest.main()
