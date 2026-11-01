# Issue4 presentation implementation plan

> Execute inline using superpowers:executing-plans. The user has approved the detailed Issue4 specification; no additional design approval is needed.

**Goal:** Rebuild 18 independent presentation videos from preserved Issue3 RGB, without simulation or learning.
**Architecture:** A simulator-independent Python goal/timeline core, saved-calibration HUD renderer, and offline provenance/QA pipeline. Preserve all source bytes; retain physical surface/section and camera motion.
**Spec:** docs/issue4-spec.md

## Global constraints
- Source main 8fe46546679bb06b9b167104aace3ba5bf601153; new branch issue4/video-goal-hud.
- No new native run, PPO, heldout, source alteration, publication, or video combination.
- 25fps, 1280x720 H.264 BT.709, 2s explicitly nonsimulation end card; one run and view per output.
- 4m presentation goal is independent of immutable historical 20s gates; F remains pending.
- Track this authorized presentation task separately from the exhausted experimental allocation. Do not debit additional experiments or contingency.

## Review focus
- Early fall/boundary/error versus goal; missing flags must produce UNKNOWN.
- First sample crossing can occur between real 25fps frames or after backtracking.
- Calibration and PNG mapping must reject stale paths, hashes and timestamps.
- The preserved side cameras actually track Z; do not claim source fixed-Z or warp RGB.
- Original gates may FAIL after the goal cutoff; clearly refer to full historical 20s gate.

### Task 1: goal and saved-camera HUD primitives
- [x] Write tests for fixed Y, X projection/translation, nonzero start, backward motion, crossing bracket, absent crossing, fall/bounds/error/unknown, nonfoot separation, real frame cutoff and independent end-card time.
- [x] Run tests RED, implement src/go2_ppo/presentation.py, run GREEN.
Interface: analyse_trial(states,result,contacts) -> dict; ruler_ticks(calibration,values) -> list; select_frames(goal,frame_times) -> list; timeline(frame_times,end_card_frames=50) -> list.

### Task 2: offline individual video reconstruction and QA
- [x] Add src/go2_ppo/presentation_media.py and CLI; save source hashes before touching output, audit 100Hz/50Hz/frame-map/K/E/raw RGB and actual terrain input.
- [x] Generate six trials x three independent views into new reports/generated/issue4/; preserve raw/old annotations; draw fixed HUD and actual unchanged section, add nonsimulation endcard.
- [x] Full decode/PTS/codec/frame count/SHA/HUD projection and source preservation checks; save start/middle/end/card images, CSV, metadata and HTML index.
- [x] Existing regression suite plus new tests; update code-port module hashes.

### Task 3: report, review and Git
- [x] Save lightweight result/spec/report; one fresh whole-branch review per executing-plans skill, address important findings with regression tests.
- [x] Commit/push verified source, tests and lightweight reports only; safely fast-forward main and read back heads/status.
- [ ] Post complete Issue4 report with 18 paths, old-gate limitations, camera discrepancy and presentation time; read back; stop.
