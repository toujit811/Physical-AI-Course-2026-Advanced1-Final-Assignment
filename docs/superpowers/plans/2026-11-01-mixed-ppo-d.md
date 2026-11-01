# Mixed PPO model D implementation plan

> Execute with superpowers:executing-plans, task by task. User explicitly requests autonomous execution; no plan approval checkpoint.

**Goal:** Safely integrate proven Mac code, continue the complete6500 PPO state into one FLAT/ROLLING policy, then evaluate that same checkpoint.
**Architecture:** One gs.init, two independent Scenes,32 FLAT+32 rolling, concatenated TensorDict/reward/done, one OnPolicyRunner/actor/critic/optimizer. Preserve verified controller and evaluation thresholds; add only versioned training rewards/reset handling.
**Tech stack:** Existing unchanged Python3.12/Genesis1.4.5/RSL5 runtime; isolated terrain venv only for bootstrap.
**Spec:** GitHub Issue2, copied to reports/generated/issue2/authority.json.

## Constraints and review focus

- Old repository/assets and6500 SHA remain immutable; clone branch startsf98e4d0. Private setting and Actions unchanged. No large models/media or local identifiers inGit.
- Obs45/action12, Kp20/Kd.5/RLcalf1, latency1, margin.12,50Hz/2substeps; approved evaluation NPZ SHA69979149... unchanged.
- Full actor/critic/Adam resume. Synchronize adaptive LR scalar from restored optimizer1e-5, never replace slots/config LR.
- Reset independence/contact clearing/command/finite states; terminal reward/done/timeouts remain aligned in the two-Scene wrapper.
- Per-child deep-copy rewards; per-environment batched terrain queries; no multiple collision Terrains in one Scene.
- Seeds disjoint; no heldout geometry instantiation until selected checkpoint hash fixed; preserve every failure.
- Experimental remaining8528s; retain submission8h+reserve3h. Measure speed before choosing training count; real updates mandatory.

## Task1: Safe port and bootstrap

- [x] Copy only transitive execution dependencies into src/go2_ppo, adjust local imports/ROOT only, record before/after hashes and source manifests.
- [x] Import/setup regression and original terrain tests; bootstrap isolated environment without modifying Genesis venv. Record generation mismatch if any; validated original NPZ remains native source.

## Task2: Mixed VecEnv and genuine PPO smoke

- [x] RED wrapper concatenation/timeout/split episode length tests; implement andGREEN.
- [x] Implement training-only reset fixes/bounds/rewards, versioned config; test reset native independence for4+4 environments.
- [x] Restore actor/critic/Adam exactly; verify adaptiveLR, finite gradients,20 Adam steps/update andchanged actor+critic after actual PPO. Save andreload all states exactly.
- [x] Smoke8env×5updates, then64env benchmark includingrollout/update/reset.128 onlyif clearly useful; never default256.

## Task3: Bounded mixed training and evaluation

- [x] Resume original6500, train50:50 at64, save multiple checkpoints,CSV/TensorBoard, per-groupsteps andresource data. Budget runtime reserves evaluation/report/review time.
- [x] Evaluate identical finalcandidate onFLAT A-E andapprovedROLLING gates, preserve failures andFpending; selectonecheckpoint withoutheldouttuning.
- [x] Afterfreezingselectedhash, evaluate3unseen smooth-rollingseeds iftimepermits; neverretunethoseseeds.
- [x] Recordrepresentative true90 close-side/oblique/overhead only, full decode.

## Task4: Stable Git and report

- [ ] Regression/native/update/save-load/evaluation/provenance/oldSHA checks. Onefresh whole-branch review; fixCritical/Important withRED-GREEN coverage.
- [ ] Commit/push stable code/config/docs/smalltests only onissue2/mixed-ppo-d; keepheavy artifactsignored, noPublic/submit/Actionschanges.
- [ ] Readback remotecommit andIssue2report, report measuredupdates/time/checkpoint/failures/remnants. Stop.

## Decisions

- User-specified separateclone supplies isolation; do not create a redundant worktree or mutate old unbornmain.
- User explicitly authorizes commit/push and no sequential approvals; skill handoff approval flows do not apply.
- Preserve this execution ledger and all run artifacts; skill cleanup guidance never overrides user preservation.

Execution outcome: actual mixed PPO and all planned evaluation actions completed; scientific acceptance NOT met. D13550 flat3/3, rolling1/3; heldout refused before opening because rolling nonfoot gate fails2/3. Original6500 adoption preserved; v4 regression rejected. This plan is the precommit review snapshot; see Issue2 for final review/Git/report outcomes.
