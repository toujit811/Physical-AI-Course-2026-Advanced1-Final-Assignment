# Native full-course completion implementation plan

> Execute inline with superpowers:executing-plans; approved specification is Issue5, no further design questions.

**Goal:** New native D13550 FLATc2 then ROLLING_UNEVENc2 runs from t0 until full-foot finish or actual failure, with three independent views.
**Spec:** docs/issue5-spec.md
**Architecture:** New stdlib goal-state machine and isolated native recorder/runner. Existing20s evaluation/Issue4 outputs immutable. Offline QA independently verifies actual source times and terminal full4foot predicate.

## Global constraints
- Base dfcadd4275a26b7d3a25a2ff936275b492147dc9; branch issue5/native-course-completion. Main unchanged.
- Fixed D13550 SHA,45obs/12actions, oldcontroller/terrain/URDF/20s gates. No PPO/heldout/model switch.
- Approved integer-mm heightfield nonzero X0.20..6.35, first flat exit X6.40; finish6.40m, native foot-sphere trailing X must strictly exceed line for0.20s, with base beyond line and no fall/boundary/error. Existing source footprint max0.689m means limited exit margin; preserve safety and report true failure rather than move goal after seeing result.
- Max60sim seconds, per-run wall cap900s, six-second progress<0.10m stalls. Stop at first fatal physical substep.
- Native raw frames from t0, fixed world cameraZ, actual saved K/E.25fps real frames, terminal off-grid snapshot explicitly maps real sim time to next videoPTS; no future physics.
- Each run/view independent raw+presentation MP4; endcard50frames outside sim, no clips or combinations. Failed runs preserved.
- New task measured separately as user-authorized extra work; no rewriting old negative experimental balance or taking fictional reserve.

## Review focus
- Base/one-front-foot crossing is insufficient; trailing foot sphere and confirmation reset on retreat.
- Odd100Hz failure must stop physics immediately; final off-grid real snapshot not fictitious regular time.
- Native recorder should not change terrain or collisions; visual-only gates and fixed cameraZ must be verified.
- Completion is distinct from historical20s and new full-run joint/contact safety.
- Partial/error runs preserve logs/images; no upgrade of missing/timeout to success.

### Task1: completion state machine
- [x] Test RED then implement course_completion.py. Fixed timing, four foot trailing extents,0.2s dwell, safety precedence, backward resets, stall/60s timeout, finite/missing and immutable result.
Interface: CourseTracker.update(row) -> result state; summary() -> serializable completion evidence.

### Task2: isolated native runner/recorder
- [x] Add course_native.py with same original construction, controller, actions, native measurement; old evaluator untouched.
- [x] Add course_media.py inheriting source capture semantics and fixed HUD; append all scheduled25fps frames plus one off-grid terminal real frame if needed. Record native START/FINISH visual lines with no collision.
- [x] Test cameraZ, full timeline preservation and endcard mapping before native execution. Keep code-port hashes in sync.

### Task3: actual native runs and QA
- [x] Preserve important model/terrain/URDF/old run andIssue4 media SHA; audit approved terrain activity and physical setup.
- [x] Execute FLATc2, then ROLLING_UNEVENc2; finish full runs/true failure and verify all three views before optional additions. Never use original20s cutoff.
- [x] Independent readback of goal predicate at100Hz, actualfeet/FK/safety/contacts, nativeZ/calibration/frame maps/rawhashes/PTS/full decode and fixedHUD; source preservation. Save data/plots/index and failures.

### Task4: review and report
- [x] Full old87+new tests, syntax, whole-branch fresh review per executing-plans; fix important issues.
- [x] Commit/push lightweight verified code/spec/report to dedicated branch only, readback HEAD/status. Report Issue5 with raw/presentation links, completion/failure and time, then stop.
