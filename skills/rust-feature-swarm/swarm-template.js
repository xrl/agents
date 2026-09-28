export const meta = {
  name: 'rust-feature-swarm',
  description: 'Concurrent lane editors -> one tiered cargo gate (check, lint, test) -> failures routed back to the causing lane -> adversarial acceptance verify -> full CI lane set. Args carry the lanes, briefs, acceptance lines and gate commands.',
  phases: [
    { title: 'Implement', detail: 'one opus editor per lane, disjoint authoring prefixes, no cargo' },
    { title: 'Shared', detail: 'single writer syncs shared files (changelog) from what lanes returned' },
    { title: 'Gate', detail: 'one sonnet agent runs the current tier and returns typed failures' },
    { title: 'Fix', detail: 'fresh opus editor per failing lane: brief + own diff + verbatim failures' },
    { title: 'Verify', detail: 'at most two adversarial opus verifiers split the lanes and try to refute acceptance' },
  ],
}

// ---- args ---------------------------------------------------------------------------------------
// {
//   worktree: '/abs/path',            scratch: '/abs/scratch',    review: '/abs/review.md' (optional),
//   mode: 'implement' | 'continue' | 'fix' | 'verify',  loop: false (implement only, return after fan-out),
//   summaries: {A: <lane return>} (continue/fix/verify: the last call's summaries, as a JSON object),
//   messagesByLane: {A: ['verbatim failures']} (fix),
//   lanes: [{ key, name, items: ['S1'], author: ['crates/x/'], blast: ['crates/y/'], forbid: [], allowed: 'cheap checks', brief }],
//   acceptance: { S1: 'acceptance line' },
//   gates: { check: ['cmd', ...], lint: [...], test: [...], full: [...] },   // each a list of 'label: shell'
//   changelog: 'CHANGELOG.md' | null,  changelogOwner: 'D' | null,
//   maxFixPerLane: 3, maxGateRounds: 8, maxVerifiers: 2, extraRules: '' (optional)
// }
const A = args
const WT = A.worktree, SCRATCH = A.scratch
const KEYS = A.lanes.map(l => l.key)
const LANE = Object.fromEntries(A.lanes.map(l => [l.key, l]))
const EDIT = Object.fromEntries(A.lanes.map(l => [l.key, [...l.author, ...(l.blast || [])]]))
const MAX_FIX = A.maxFixPerLane || 3
const MAX_GATE = A.maxGateRounds || 8
const MAX_VERIFY = A.maxVerifiers || 2
const TIERS = ['check', 'lint', 'test']
const ITEM_IDS = Object.keys(A.acceptance)
const ITEM_LANE = Object.fromEntries(A.lanes.flatMap(l => l.items.map(id => [id, l.key])))

const RULES = `Worktree (absolute; use it for every path and command): ${WT}
${A.review ? `The brief/review that defines the work is at ${A.review}; read it once.` : ''}
HARD RULES
1. Edit ONLY files under your editable prefixes (below): your authoring prefixes plus the blast radius your change can break (test fixtures, consumers). If a fix needs a file outside them, do not touch it: report it in items[].blocked_on_path (the repo-relative path) with the exact change in items[].summary. The router decides who edits it; never name a lane yourself.
2. NEVER run cargo, rustc, clippy, cargo test, or any workspace build. One gate runs over everyone's work and routes verbatim diagnostics back to you. Reason statically. Allowed cheap checks are listed per lane; nothing else.
3. NEVER run git add/commit/stash/checkout/restore/reset/switch/rebase/clean. The coordinator commits. To undo an edit, write the file back from 'git show HEAD:<path>'. Deleting a file is 'rm'.
4. Other lanes edit the same tree concurrently. Never report their work as missing or wrong; the gate is the only judge of the tree. Never touch a file another lane is authoring, even to 'help'.
5. AGENTS.md / CLAUDE.md apply. Failure-path tests assert the surfaced cause, not is_err(). New pub items and error variants need a non-test consumer. No local paths, TODOs, or model/session identifiers in the tree.
${A.changelog ? `6. Do not edit ${A.changelog} unless you are lane ${A.changelogOwner}. Return the bullets your change needs as changelog_bullets; a single writer inserts them.` : ''}
7. Your final output is the structured object only. items[].acceptance_evidence cites file:line of the code and test satisfying the acceptance line. files_touched lists every file this lane has created, edited, or deleted so far, repo-relative.
${A.extraRules || ''}`

const RETURN = {
  type: 'object',
  properties: {
    lane: { type: 'string', enum: KEYS },
    files_touched: { type: 'array', items: { type: 'string' } },
    changelog_bullets: { type: 'array', items: { type: 'object', properties: { category: { type: 'string' }, text: { type: 'string' } }, required: ['category', 'text'] } },
    items: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string', enum: ITEM_IDS }, done: { type: 'boolean' }, summary: { type: 'string' },
      acceptance_evidence: { type: 'string' }, blocked_on_path: { type: 'string' },
    }, required: ['id', 'done', 'summary', 'acceptance_evidence'] } },
    notes: { type: 'string' },
  },
  required: ['lane', 'files_touched', 'changelog_bullets', 'items'],
}
const GATE = {
  type: 'object',
  properties: {
    tier: { type: 'string' }, green: { type: 'boolean' },
    failures: { type: 'array', items: { type: 'object', properties: { stage: { type: 'string' }, path: { type: 'string' }, crate: { type: 'string' }, test: { type: 'string' }, message: { type: 'string' } }, required: ['stage', 'message'] } },
    skipped: { type: 'array', items: { type: 'object', properties: { stage: { type: 'string' }, reason: { type: 'string' } }, required: ['stage', 'reason'] } },
    summary: { type: 'string' },
  },
  required: ['tier', 'green', 'failures', 'skipped', 'summary'],
}
const VERDICT = { type: 'object', properties: { items: { type: 'array', items: { type: 'object', properties: { id: { type: 'string', enum: ITEM_IDS }, met: { type: 'boolean' }, blocking: { type: 'boolean' }, evidence: { type: 'string' }, gap: { type: 'string' } }, required: ['id', 'met', 'blocking', 'evidence', 'gap'] } }, notes: { type: 'string' } }, required: ['items'] }
const SHARED = { type: 'object', properties: { inserted: { type: 'array', items: { type: 'string' } }, removed: { type: 'array', items: { type: 'string' } } }, required: ['inserted', 'removed'] }

function norm(p) { if (!p) return null; let s = String(p).trim().replace(/^\.\//, ''); if (s.startsWith(WT + '/')) s = s.slice(WT.length + 1); return s }
function ownerOf(path, crate) {
  const p = norm(path), c = crate ? `crates/${String(crate).replace(/_/g, '-')}/` : null
  const hit = (list) => list.some(pre => (p && p.startsWith(pre)) || (c && c.startsWith(pre)))
  for (const k of KEYS) if (hit(LANE[k].author)) return k
  for (const k of KEYS) if (hit(LANE[k].blast || [])) return k
  return null
}
function testCrate(test) { const m = test && String(test).match(/^([a-z0-9_]+)::/); return m ? m[1] : null }
function route(failures) {
  const by = {}, un = []
  for (const f of failures) { const k = ownerOf(f.path, f.crate) || ownerOf(null, testCrate(f.test)); if (k) (by[k] = by[k] || []).push(f); else un.push(f) }
  return { by, un }
}
function violations(k, r) { return (r.files_touched || []).map(norm).filter(p => !EDIT[k].some(pre => p.startsWith(pre)) || (LANE[k].forbid || []).includes(p)) }
function renderFailures(fs) { return fs.map((f, i) => `--- failure ${i + 1} [${f.stage}]${f.path ? ' ' + f.path : ''}${f.test ? ' test ' + f.test : ''}\n${f.message}`).join('\n\n') }
function editList(k) { return EDIT[k].map(p => '  ' + p).join('\n') + ((LANE[k].forbid || []).length ? `\n  (never: ${LANE[k].forbid.join(', ')})` : '') }
function acceptLines(k) { return LANE[k].items.map(id => `  ${id}: ${A.acceptance[id]}`).join('\n') }

function implPrompt(k) {
  const l = LANE[k]
  return `You are lane ${k} (${l.name}) in a coordinated Rust change.\n${RULES}\n\nYOUR EDITABLE PREFIXES (author first, then blast radius):\n${editList(k)}\nAllowed cheap checks: ${l.allowed || 'none'}\n\nACCEPTANCE LINES YOU MUST SATISFY:\n${acceptLines(k)}\n\nBRIEF:\n${l.brief}\n\nWork item by item. Read every cited location and its callers before editing. Re-read your diff once as a reviewer would (git -C ${WT} diff -- ${EDIT[k].join(' ')}). Return the structured object with one items[] entry per acceptance id (ids are fixed; never invent one).`
}
function fixPrompt(k, prev, msgs) {
  const l = LANE[k]
  return `You are a fix agent for lane ${k} (${l.name}). Previous agents implemented this lane's brief; the gate or verifier found problems attributed to it. Fix them; do not redo unaffected work.\n${RULES}\n\nYOUR EDITABLE PREFIXES:\n${editList(k)}\nAllowed cheap checks: ${l.allowed || 'none'}\n\nACCEPTANCE LINES:\n${acceptLines(k)}\n\nBRIEF:\n${l.brief}\n\nPREVIOUS RETURN:\n${JSON.stringify(prev || {}, null, 1)}\n\nFirst read the current state: git -C ${WT} diff -- ${EDIT[k].join(' ')} and git -C ${WT} status --short.\n\nPROBLEMS TO FIX (verbatim; do not argue with a compiler):\n${msgs.join('\n\n=====\n\n')}\n\nReturn the structured object covering every acceptance id (done=true only when complete), files_touched = every file this lane has changed so far, changelog_bullets = the complete current set.`
}
function gatePrompt(tier, round) {
  const cmds = (A.gates[tier] || []).map((c, i) => `${i + 1} ${c}`).join('\n')
  return `You are the build gate (round ${round}, tier ${tier}). Worktree: ${WT}. Run every command from that directory.
DO NOT modify any file: no cargo fmt without --check, no fixes, no git write operations, no stash. Observe and report only.
Every cargo command: Bash timeout 600000. HANG HANDLING: if a test run exceeds its timeout, read its log, list tests that started and never finished, report each as a failure with message 'HUNG > 10 minutes', then rerun with each hung test skipped to collect the rest. Save each command's output with tee to ${SCRATCH}/gate-${round}-<n>.log and record its exit code. Continue past failures so one round reports everything; skip only what an earlier failure makes impossible and list it in skipped.
COMMANDS:
${cmds}

RETURN one failures[] entry per distinct diagnostic: stage = the label; path = repo-relative file from the diagnostic ('-->' line, traceback, 'Diff in <path>', template path), omit if none; crate = Cargo package name with hyphens from the Compiling/Running context, omit if none; test = full test path for a failing test, omit if none; message = the VERBATIM diagnostic block (rustc error with code, --> location and snippet; failing test name plus its complete panic output; python FAIL block; helm error; fmt diff), cut at 4000 chars. Never paraphrase. green = every non-skipped command exited 0. summary = one line per stage.`
}
function verifyPrompt(keys) {
  const lanes = keys.map(k => `LANE ${k} (${LANE[k].name}); editable: ${EDIT[k].join(', ')}\nClaims:\n${JSON.stringify(summaries[k] || {}, null, 1)}\nItems:\n${acceptLines(k)}`).join('\n\n')
  return `You are an adversarial verifier for lane${keys.length > 1 ? 's' : ''} ${keys.join(', ')}. Worktree: ${WT}. READ-ONLY: no edits, no cargo, no git write operations.
${A.review ? `The defining brief/review is at ${A.review}.` : ''}
For each item, try to REFUTE that its acceptance line is satisfied by reading the actual code and tests (git -C ${WT} diff -- <paths>, plus the unchanged surroundings and every caller). Cite file:line. Also check: each behavior change has a changelog bullet${A.changelog ? ` in ${A.changelog}` : ''}; no local paths/TODOs/identifiers; failure-path tests assert the cause; validations report every conflict at once where asked; nothing outside a lane's editable prefixes changed on its behalf.
If you cannot find concrete evidence an acceptance line is met, met=false with a precise gap. Grade every gap: blocking=true only when the acceptance line is NOT satisfied or the code is wrong (a false claim in shipped prose counts); blocking=false for wording, style, and hardening suggestions. Only blocking gaps go back to the lane; nits reach the human reviewer. Return one items[] entry per listed item id and use only those ids; anything else (ownership, hygiene, process) goes in notes. Do not accept a lane's claims as evidence.

${lanes}`
}
function sharedPrompt(changes) {
  return `Worktree: ${WT}. Edit ONLY ${A.changelog}. Under the unreleased section, apply the bullet changes below under their categories (create a missing category heading in Keep a Changelog order), matching the file's voice and wrap width; change no existing bullet. Where 'remove' lists bullets, delete those exact bullets if present. No cargo, no git write operations.\n${changes.map(c => `LANE ${c.lane}\n  remove: ${JSON.stringify(c.remove)}\n  insert: ${JSON.stringify(c.insert)}`).join('\n')}\nReturn {inserted, removed} listing the bullet texts as written.`
}

// ---- state -------------------------------------------------------------------------------------
const summaries = {}
const pending = Object.fromEntries(KEYS.map(k => [k, []]))   // [{kind: 'gate'|'verify'|'bookkeeping', text}]
const fixCount = Object.fromEntries(KEYS.map(k => [k, 0]))    // rounds that carried gate/verify information
const bookCount = Object.fromEntries(KEYS.map(k => [k, 0]))   // bookkeeping-only rounds (ownership, coverage, cross-lane)
const MAX_BOOK = 2
const nits = []
function push(k, kind, text) { pending[k].push({ kind, text }) }
const inserted = Object.fromEntries(KEYS.map(k => [k, []]))
let lastVerdicts = null, lastGate = null

function afterReturn(k, r) {
  const v = violations(k, r)
  if (v.length) push(k, 'bookkeeping', `Ownership violation: you changed ${v.join(', ')}, outside lane ${k}'s editable prefixes. Restore each with 'git -C ${WT} show HEAD:<path> > <path>' (rm if new). If the change is needed, report it in items[].blocked_on_path.`)
  const got = new Set((r.items || []).map(i => i.id))
  const missing = LANE[k].items.filter(id => !got.has(id))
  if (missing.length) push(k, 'bookkeeping', `Your return had no items[] entry for ${missing.join(', ')}. Do them and report them.`)
  for (const it of r.items || []) {
    if (it.blocked_on_path) {
      const owner = ownerOf(it.blocked_on_path)
      if (owner && owner !== k) push(owner, 'bookkeeping', `Cross-lane request from lane ${k} for ${it.id}, file ${norm(it.blocked_on_path)} (in your editable prefixes): ${it.summary}\nEvidence so far: ${it.acceptance_evidence}`)
      else {
        // Nobody else may edit it: repair ownership follows the causing change. Widen this lane.
        const dir = norm(it.blocked_on_path).replace(/[^/]*$/, '')
        if (!EDIT[k].some(pre => dir.startsWith(pre))) EDIT[k].push(dir)
        push(k, 'bookkeeping', `No other lane may edit ${norm(it.blocked_on_path)}; it is now in your editable prefixes (${dir}). Make the change yourself for ${it.id}: ${it.summary}`)
        log(`lane ${k} widened to ${dir}`)
      }
    } else if (!it.done) push(k, 'bookkeeping', `Item ${it.id} is reported not done: ${it.summary}. Finish it.`)
  }
}
function mergeReturn(old, r) { const files = new Set([...(old && old.files_touched || []), ...(r.files_touched || [])].map(norm)); return { ...r, files_touched: [...files] } }
async function syncShared() {
  if (!A.changelog) return
  const changes = []
  for (const k of KEYS) {
    if (k === A.changelogOwner) continue
    const want = (summaries[k] && summaries[k].changelog_bullets) || []
    if (JSON.stringify(want) !== JSON.stringify(inserted[k])) changes.push({ lane: k, remove: inserted[k].map(b => b.text), insert: want })
  }
  if (!changes.length) return
  phase('Shared')
  const r = await agent(sharedPrompt(changes), { label: 'shared:changelog', phase: 'Shared', schema: SHARED, model: 'sonnet', effort: 'medium' })
  if (r) for (const c of changes) inserted[c.lane] = c.insert
}
async function fixRound(due) {
  phase('Fix')
  log(`fix round for ${due.join(', ')} (counts ${JSON.stringify(fixCount)})`)
  await parallel(due.map(k => () => {
    const entries = pending[k].splice(0)
    const informative = entries.some(e => e.kind !== 'bookkeeping')
    if (informative) fixCount[k] += 1; else bookCount[k] += 1
    const msgs = entries.map(e => e.text)
    return agent(fixPrompt(k, summaries[k], msgs), { label: `fix:${k}:${fixCount[k]}${informative ? '' : 'b'}`, phase: 'Fix', schema: RETURN, model: 'opus' })
      .then(r => { if (r) { summaries[k] = mergeReturn(summaries[k], r); afterReturn(k, r) } else pending[k].push(...entries) })
  }))
  await syncShared()
}
function verifierGroups() {
  const n = Math.max(1, Math.min(MAX_VERIFY, KEYS.length))
  const groups = Array.from({ length: n }, () => [])
  KEYS.forEach((k, i) => groups[i % n].push(k))
  return groups
}
// One verdict per lane (null when its verifier returned nothing), items filtered to that lane's ids.
async function runVerify() {
  phase('Verify')
  const groups = verifierGroups()
  const raw = await parallel(groups.map(keys => () => agent(verifyPrompt(keys), { label: `verify:${keys.join('+')}`, phase: 'Verify', schema: VERDICT, model: 'opus' })))
  const byLane = {}
  groups.forEach((keys, i) => {
    const v = raw[i]
    if (!v) log(`verifier for lane(s) ${keys.join(', ')} returned nothing`)
    for (const k of keys) byLane[k] = v ? { items: (v.items || []).filter(it => ITEM_LANE[it.id] === k), notes: v.notes || '' } : null
  })
  return byLane
}

// ---- run ---------------------------------------------------------------------------------------
if (A.mode === 'continue' || A.mode === 'fix' || A.mode === 'verify') {
  if (!A.summaries || typeof A.summaries !== 'object') throw new Error(`mode '${A.mode}' needs args.summaries: the last call's summaries as a JSON object`)
  for (const k of KEYS) { summaries[k] = A.summaries[k]; inserted[k] = (summaries[k] && summaries[k].changelog_bullets) || [] }
} else {
  phase('Implement')
  log(`fan-out: ${KEYS.length} lane editors in ${WT}`)
  const first = await parallel(KEYS.map(k => () => agent(implPrompt(k), { label: `impl:${k}`, phase: 'Implement', schema: RETURN, model: 'opus' })))
  KEYS.forEach((k, i) => { const r = first[i]; if (!r) { push(k, 'bookkeeping', 'The implementer run returned nothing. Do the full brief (check git status first; some edits may exist).'); return } summaries[k] = mergeReturn(null, r); afterReturn(k, r) })
  await syncShared()
}

// Coordinator-driven modes: the main session runs cargo itself (cheap, no gate agent) and calls
// the script only for a fleet. 'fix' takes args.messagesByLane {A: ['verbatim failures', ...]} and
// runs one routed round; 'verify' runs one verifier round. Both return the lane summaries.
if (A.mode === 'fix') {
  for (const [k, msgs] of Object.entries(A.messagesByLane || {})) for (const m of msgs) push(k, 'gate', m)
  const due = KEYS.filter(k => pending[k].length)
  if (due.length) await fixRound(due)
  return { mode: 'fix', fixCount, bookCount, summaries, pending }
}
if (A.mode === 'verify') return { mode: 'verify', verdicts: await runVerify(), summaries }
if (A.mode === 'implement' && A.loop === false) return { mode: 'implement', summaries, pending }

let tier = 0, round = 0, verified = false
while (round < MAX_GATE) {
  const due = KEYS.filter(k => pending[k].length)
  if (due.length) {
    const over = due.filter(k => (pending[k].some(e => e.kind !== 'bookkeeping') && fixCount[k] >= MAX_FIX) || (!pending[k].some(e => e.kind !== 'bookkeeping') && bookCount[k] >= MAX_BOOK))
    if (over.length) { log(`repair cap hit for lane(s) ${over.join(', ')} (fix ${JSON.stringify(fixCount)}, bookkeeping ${JSON.stringify(bookCount)}); stopping for the coordinator`); break }
    await fixRound(due)
    tier = 0; verified = false           // any edit restarts at the cheapest tier
    continue
  }
  const name = tier < TIERS.length ? TIERS[tier] : (verified ? 'full' : 'verify')
  if (name === 'verify') {
    lastVerdicts = await runVerify()
    let gaps = 0
    for (const k of KEYS) {
      const v = lastVerdicts[k]
      if (!v) continue
      for (const it of v.items) {
        if (!it.met && it.blocking) { gaps += 1; push(k, 'verify', `Verifier refuted ${it.id}.\nGap: ${it.gap}\nEvidence: ${it.evidence}`) }
        else if (!it.met) nits.push({ lane: k, id: it.id, gap: it.gap, evidence: it.evidence })
      }
    }
    if (gaps) { log(`${gaps} acceptance gap(s) routed back`); continue }
    verified = true; log('acceptance verified; running the full lane set'); continue
  }
  if (!(A.gates[name] || []).length) { log(`tier ${name} has no commands; skipping`); if (name === 'full') return { green: true, gateRounds: round, fixCount, bookCount, summaries, verdicts: lastVerdicts, nits }; tier += 1; continue }
  round += 1
  phase('Gate')
  log(`gate round ${round}: tier ${name}`)
  const gate = await agent(gatePrompt(name, round), { label: `gate:${round}:${name}`, phase: 'Gate', schema: GATE, model: 'sonnet', effort: 'medium' })
  lastGate = gate
  if (!gate) { log('gate returned nothing; rerunning'); continue }
  log(`gate ${round} (${name}): ${gate.green ? 'GREEN' : (gate.failures || []).length + ' failure(s)'}; skipped ${(gate.skipped || []).map(s => s.stage).join(', ') || 'none'}`)
  if (!gate.green) {
    const { by, un } = route(gate.failures || [])
    if (un.length) log(`${un.length} unroutable failure(s): ${un.map(f => f.stage + (f.path ? ' ' + f.path : '')).join('; ')}`)
    if (!Object.keys(by).length) { log('only unroutable failures remain; stopping for the coordinator'); break }
    for (const [k, fs] of Object.entries(by)) push(k, 'gate', `Gate round ${round} (${name}) failures attributed to your files:\n\n${renderFailures(fs)}`)
    continue
  }
  if (name === 'full') return { green: true, gateRounds: round, fixCount, bookCount, summaries, verdicts: lastVerdicts, nits, gate }
  tier += 1
}
return { green: false, gateRounds: round, fixCount, bookCount, summaries, pending, verdicts: lastVerdicts, nits, lastGate }
