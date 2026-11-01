# Issue6 paired twelve recordings — 2026-11-02
Authority: Issue6 current top section (updated 2026-11-01T17:23:32Z); user selected actual post-goal capture = 3 seconds.
Base: 7a06280fd6dd5e63e06713c3f8d0d78651bb14bc. Work on dedicated branch, no main changes.

1. Snapshot prior artifacts/model/terrain and read native code. Preserve historical evaluator and all prior outputs.
2. RED→GREEN: optional recording window latches first four-foot goal without hold; actual physics continues three seconds; errors remain errors. Preserve old tracker defaults.
3. RED→GREEN: paired standard MP4 uses exactly raw source frames/PTS, existing layout/camera/viridis; no result cards. Save numeric frame/profile/ruler mapping.
4. Run new c2 FLAT + approved ROLLING_UNEVEN native simulations with same D13550 and controls; record three views before first step; save all evidence.
5. Independently verify all twelve MP4s and source hashes, physical prefixes/camera calibration/sync/goals/tail, tests; fresh-context whole-change review. Commit/push dedicated branch, report all twelve absolute paths and findings to Issue6; stop.

Ruling: During the requested three-second post-goal recording, boundary/fall observations remain logged but do not cut the recording; before the goal the existing stop rules apply. Engine/nonfinite/resource/wall errors always stop. Goal achievement and post-goal safety are separate results. This preserves physical terrain/policy and records any real fall off the finite terrain rather than inventing a runway or fake motion. Cost if wrong: the tail may show a boundary excursion/fall, which must be reported and cannot be described as safe walking.

Progress: 118 tests GREEN (including preserved113); new FLAT native27.56→30.56s, UNEVEN native29.90→32.90s. UNEVEN post-goal boundary30.18s, nonfoot30.50s, fall30.88s; actual finite-terrain fall retained. Initial 8m display-axis assumption was insufficient (actual base8.358m); both standard displays now use a9m visual axis while the physical terrain remains[-1,7]. All earlier attempts retained. Final encoding/independent QA pending.

Completion: final six standards encoded from immutable RGB; independent all12 decode/provenance/camera/profile QA PASS; preserved224 SHA matches; all118 tests PASS. Fresh-context review: no critical/important findings. Earlier pending sentence is historical; QA is now complete.
Final: minor (deferred): Future goals after approximately57s can have their3s tail truncated by the60s outer-loop ceiling; not encountered in either delivered run.
Final: Ruling: reviewer did not rerun physical reproduction/all12decode or inspect remote; this executor performed both actual native runs, independent all12decode/hash audit and will verify remote afterpush. F perceptual acceptance remains user-pending. Cost if wrong: subjective framing acceptance may still need user review; no human approval is claimed.
