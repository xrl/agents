---
name: future-tabletop
description: Stress-test a plan or design before the owner reviews it. A Sonnet subagent pretends the plan has fully landed and walks concrete failure timelines (what breaks, who acts, how long recovery takes, where everything jams), citing the real code. Use when Xavier asks to "experience the future state", "tabletop", "pretend it's post-merge" or "what happens when this plan's X goes out", and run it on any new design that changes how work ships, recovers or holds credentials, before the owner reviews it.
---

# Future-state tabletop

A plan reads as complete to its author. This skill tests it against the code it will run on. A fresh, skeptical subagent is told the plan has already landed and walks real scenarios forward in time. Its findings change the plan before the owner sees it.

## Run it

1. **Write the plan to a file first.** The subagent reads the file, not a summary.
2. **Spawn one `Plan` subagent** (`model: sonnet`, the owner's choice for tabletops, 2026-11-25). Run it in the background when there is other work.
3. **Brief it with the template below.** Fill in the plan path, the real code and config to read (repos, files, and how to read a remote main, e.g. `git show origin/main:<path>`), and four to six scenario groups specific to this plan.
4. **Verify before folding in.** Check the 3-5 findings that would change the design against the code yourself (read the cited `path:line`). A subagent's claim is a lead, not evidence.
5. **Revise the plan,** citing the tabletop. Name each finding the revision answers. Leftover risks the plan accepts become owner calls, stated flatly. Then the plan goes to its fresh Fable review: this is [LAWS.md](../../LAWS.md) §52's scenario walk run cheap first, and it replaces neither that review nor §52's second-family review.
6. **Re-run on a major revision.** Skip the re-run for wording changes.

## Brief template

```
Read-only tabletop exercise; edit nothing. Pretend the plan at <PLAN PATH>
(section "<SECTION>") has fully landed. Read it first. You are a skeptical
<SRE / security reviewer / user of the feature>. Ground every claim in the real
files with path:line; where the plan is silent, say so rather than assume it works.

Real code and config to read: <repos, paths, how to read origin/main>.
How things run today (verify, don't trust): <2-5 bullets of current mechanics>.
Query no live system. Production values come from <deploy repo> at origin/main,
not defaults in source.

Walk each as a timeline (T+0 = <trigger>): who or what acts at each step (human,
model, script, controller), how long it takes, where it stalls.
1. <happy path end to end>
2. <the failure classes this plan claims to handle>
3. <failures in our own tooling, config and credentials it depends on>
4. Recovery time for each, until the system is good AND the ledger (cm, git,
   receipts) agrees with reality.
5. Full jams: anything where every recovery path depends on the broken thing,
   or harms with no automatic undo (money, accounts, data, standing).
6. Ranked top 5 gaps: the smallest fix and the owner of each.

Report under ~900 words, tables welcome, concrete, no generic advice.
Timebox: 15 minutes, 100 tool calls or 300k tokens; at the limit, report what you have.
```

## Rules

- **One agent, one plan section.** Run separate tabletops for separate designs, in parallel if they are independent.
- **Size the grant by worst text, don't add defences.** For a design holding a credential or an account, ask what an injected page could make the agent do with it, and where the credential could travel.
