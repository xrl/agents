// pi-subagents workflow for the brief §Work packages lanes A–E (the core + SDK PR).
// Run from the PR worktree: subagent({ workflowScriptPath: "<BRIEF-DIR>/pi/lanes.workflow.js", args })
// args = { prRoot: "/abs/path/to/.worktrees/<PR WORKTREE>", prBranch: "<PR BRANCH>",
//          lanes: [{ key: "A", stage: 1, packages: ["<CRATE>"], worktree: "/abs/.worktrees/<LANE WORKTREE>", branch: "<LANE BRANCH>", brief: "…" }, …],
//          maxRounds: 3, measure: { sha, worktree, branch } /* optional baseline stage; omit when done */ }
// Preflight (the brief §Preflight) has already run and created every worktree from the same origin/main SHA.
// Stages (the brief §Decisions, lane order): stage-1 lanes edit in parallel; after their verification the gate-runner merges them and
// runs tiers 1–2; stage-2 lanes then start by merging the stage-1 branches into their own worktrees.
// Constraints of the script runtime: no nested async helpers; runs.all resolves to an ordered array.

const lanes = args.lanes;
const maxRounds = args.maxRounds || 3;
const stageOf = l => l.stage || 1;
const stages = [];
for (const l of lanes) if (stages.indexOf(stageOf(l)) === -1) stages.push(stageOf(l));
stages.sort();

// 0. Baseline measurement, when asked for: an editor adapts the harness (editing is never the
//    orchestrator's), then the gate-runner runs it in the container. Implementation lanes wait.
let baseline = null;
if (args.measure) {
  const harness = await runs.run("measure-harness", {
    agent: "lane-editor",
    cwd: args.measure.worktree,
    task: "Baseline-measurement harness, per the brief's preflight step 8 and §Acceptance. " +
          "Worktree " + args.measure.worktree + " on branch " + args.measure.branch + " at " +
          args.measure.sha + ". Cherry-pick the existing harness branches' commits (gateway branch " +
          "first, then broker) onto this branch, resolve conflicts toward measuring the new " +
          "code paths, keep any provider-repo hunks out of core, and commit. Report what " +
          "changed and how to run it.",
  });
  const run = await runs.run("measure-baseline", {
    agent: "gate-runner",
    cwd: args.measure.worktree,
    task: "Run the baseline measurement harness in the linux/arm64 container exactly as the " +
          "measurements documents describe (same cases, seeds, three runs, medians) and write " +
          "the table to measurements/baseline-" + args.measure.sha.slice(0, 8) + ".md. " +
          "Editor's notes:\n" + harness.output,
  });
  baseline = { harness: harness.output, run: run.output };
}

// 1–2. Per stage: lane editors in parallel, a fresh verifier each, one resumed fix pass on
//      FIX REQUIRED, then (for every stage but the last) a partial merge + tiers 1–2 so the next
//      stage starts from a compiling base.
const edits = new Array(lanes.length);
const verdicts = new Array(lanes.length);
for (let s = 0; s < stages.length; s++) {
  const idx = [];
  for (let i = 0; i < lanes.length; i++) if (stageOf(lanes[i]) === stages[s]) idx.push(i);
  const merged = lanes.filter(l => stageOf(l) < stages[s]).map(l => l.branch);
  const stageEdits = await runs.all(idx.map(i => ({
    key: "edit-" + lanes[i].key,
    agent: "lane-editor",
    cwd: lanes[i].worktree,
    task: "Lane " + lanes[i].key + " of <BRIEF> §4. Worktree: " + lanes[i].worktree +
          " on branch " + lanes[i].branch + "." +
          (merged.length ? "\nFirst: `git merge " + merged.join(" ") + "` into this worktree (they are committed and verified); read their committed code before editing." : "") +
          "\n\n" + lanes[i].brief,
  })));
  for (let k = 0; k < idx.length; k++) edits[idx[k]] = stageEdits[k];
  const stageVerdicts = await runs.all(idx.map(i => ({
    key: "verify-" + lanes[i].key,
    agent: "lane-verifier",
    context: "fresh",
    cwd: lanes[i].worktree,
    task: "Verify lane " + lanes[i].key + " at " + lanes[i].worktree + " (branch " + lanes[i].branch + ").\n" +
          "Editor's report:\n" + edits[i].output,
  })));
  for (let k = 0; k < idx.length; k++) verdicts[idx[k]] = stageVerdicts[k];
  // Two fix passes per lane (editor resumed, verifier resumed); a third FIX REQUIRED blocks the lane.
  for (const i of idx) {
    for (let pass = 1; pass <= 2 && verdicts[i].output.indexOf("FIX REQUIRED") !== -1; pass++) {
      edits[i] = await runs.run("fix-" + lanes[i].key + "-" + pass, {
        resume: edits[i].runId,
        task: "The verifier requires fixes (pass " + pass + " of 2). Apply exactly the contract and guideline findings and commit; taste is optional:\n" + verdicts[i].output,
      });
      verdicts[i] = await runs.run("reverify-" + lanes[i].key + "-" + pass, {
        resume: verdicts[i].runId,
        task: "Re-verify the same lane after the editor's fix pass " + pass + ". Editor's report:\n" + edits[i].output,
      });
    }
    if (verdicts[i].output.indexOf("FIX REQUIRED") !== -1) {
      throw new Error("Lane " + lanes[i].key + " still FIX REQUIRED after two fix passes; blocked for the owner. Last verdict:\n" + verdicts[i].output);
    }
  }
  if (s < stages.length - 1) {
    const partial = await runs.run("gate-stage-" + stages[s], {
      agent: "gate-runner",
      cwd: args.prRoot,
      task: "PR branch " + args.prBranch + ". Merge lane branches: " +
            lanes.filter(l => stageOf(l) <= stages[s]).map(l => l.branch).join(", ") +
            ". Run the brief §Gate tiers tier 0: tiers 1–2 SCOPED with -p to these packages only: " +
            lanes.filter(l => stageOf(l) <= stages[s]).map(l => (l.packages || []).join(" ")).join(" ") +
            "; plus each merged lane's stage-1 sanity line. Whole-workspace failures in packages outside that list are expected until stage 2 and are not failures.",
    });
    const report = JSON.parse(partial.output);
    const failed = report.tiers.filter(t => t.result === "fail");
    for (const f of failed) {
      const j = lanes.findIndex(l => l.key === f.lane);
      if (j === -1) throw new Error("Stage gate failure not attributable to a lane; supervisor must route it:\n" + f.output);
      edits[j] = await runs.run("stagefix-" + lanes[j].key, {
        resume: edits[j].runId,
        task: "Gate tier " + f.tier + " failed on the merged PR branch. Fix in your worktree and commit. " +
              "Verbatim output:\n" + f.output,
      });
    }
    if (failed.length) {
      const again = await runs.run("gate-stage-" + stages[s] + "-again", {
        agent: "gate-runner",
        cwd: args.prRoot,
        task: "PR branch " + args.prBranch + ". Merge lane branches: " +
              lanes.filter(l => stageOf(l) <= stages[s]).map(l => l.branch).join(", ") +
              ". Run the brief §Gate tiers tier 0: tiers 1–2 SCOPED with -p to these packages only: " +
              lanes.filter(l => stageOf(l) <= stages[s]).map(l => (l.packages || []).join(" ")).join(" ") + ".",
      });
      if (JSON.parse(again.output).tiers.some(t => t.result === "fail")) {
        throw new Error("Stage " + stages[s] + " still red after one fix round; stop and report:\n" + again.output);
      }
    }
  }
}

// 3. Gate rounds: merge every lane into the PR branch, run tiers 1–5, route verbatim failures to the causing lane.
let gate = null;
for (let round = 1; round <= maxRounds; round++) {
  gate = await runs.run("gate-" + round, {
    agent: "gate-runner",
    cwd: args.prRoot,
    task: "PR branch " + args.prBranch + ". Merge lane branches: " +
          lanes.map(l => l.branch).join(", ") + ". Run the brief §Gate tiers tiers 1–5.",
  });
  const report = JSON.parse(gate.output);
  const failed = report.tiers.filter(t => t.result === "fail");
  if (failed.length === 0) break;
  for (const f of failed) {
    const idx = lanes.findIndex(l => l.key === f.lane);
    if (idx === -1) {
      throw new Error("Gate failure not attributable to a lane; supervisor must route it:\n" + f.output);
    }
    edits[idx] = await runs.run("gatefix-" + round + "-" + lanes[idx].key, {
      resume: edits[idx].runId,
      task: "Gate tier " + f.tier + " failed on the merged PR branch. Fix in your worktree and commit. " +
            "Verbatim output:\n" + f.output,
    });
  }
  if (round === maxRounds) throw new Error("Gate still red after " + maxRounds + " rounds; stop and report.");
}

// 4. Whole-PR adversarial review (fresh context), one fix round, one more gate run.
const review = await runs.run("review", {
  agent: "pr-reviewer",
  context: "fresh",
  cwd: args.prRoot,
  task: "Review the assembled PR on branch " + args.prBranch + " against <BRIEF>.",
});
if (review.output.indexOf("FIX REQUIRED") !== -1) {
  for (let i = 0; i < lanes.length; i++) {
    if (review.output.indexOf("Lane " + lanes[i].key) !== -1) {
      edits[i] = await runs.run("reviewfix-" + lanes[i].key, {
        resume: edits[i].runId,
        task: "The PR reviewer requires fixes for your lane. Apply exactly these and commit:\n" + review.output,
      });
    }
  }
  gate = await runs.run("gate-final", {
    agent: "gate-runner",
    cwd: args.prRoot,
    task: "PR branch " + args.prBranch + ". Merge lane branches: " +
          lanes.map(l => l.branch).join(", ") + ". Run the brief §Gate tiers tiers 1–5.",
  });
}

// 5. Hand back. The parent (orchestrator) runs §9.4 tiers 6–8: measurement re-run, then opens the PR.
return {
  head: JSON.parse(gate.output).head,
  gate: gate.output,
  review: review.output,
  baseline: baseline,
  lanes: lanes.map((l, i) => ({ key: l.key, stage: stageOf(l), branch: l.branch, report: edits[i].output })),
};
