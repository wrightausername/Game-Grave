# Game Grave 1.0 | Closed-beta test protocol and identical questionnaire

**Status: PREPARED ONLY. Do not invite testers yet.** Use this same versioned questionnaire for every beta participant so reports can be compared. The closed beta is **Milestone 6**, after M1–M5 have passed their release gates; M7 is the stable release *after* the beta, not a prerequisite for conducting it.

**Questionnaire version:** GG-BETA-Q1 / 2026-10-30. Freeze question wording, answer scales, task order and test-build identifier before opening the beta. Changes require a new Q2 version and should not be pooled as identical responses.

## Eligibility and safe environment

- Windows 10 or 11, ordinary desktop account, representative Steam/Epic/GOG and optionally MO2/Vortex/Workshop/FiveM/MMO installs.
- Install only a signed release-candidate build with a published checksum, **not an unsigned engineering preview**.
- Test cleanup and recovery on **disposable test files only**. Never instruct people to remove active saves, game libraries or managed mods for the beta.
- No required telemetry or account, no remote screen sharing, and no upload of unredacted paths, usernames, mods, licenses, gaming account identifiers or save data.
- Optional game-manager use is not an eligibility requirement. When a feature is unavailable, mark **Not applicable**, not Failed.
- Participants may stop at any time without penalty and decline follow-up contact. Age 18+ and explicit opt-in.
- Record OS family/build, test build and installed launchers as broad categories only. Do not collect hardware serials or account names.

## Identical task sequence

Use the same instructions and task order. Observers record whether each task succeeded **without assistance**, succeeded **with assistance**, failed, or was **not applicable**.

| ID | Safe exercise | Expected observation |
|---|---|---|
| T01 | Install the signed candidate and launch Game Grave | App opens normally with no security or first-run data loss |
| T02 | Run a read-only Scan PC | No game files are altered; cancellation and status are clear |
| T03 | Open Game DNA → View visual map | Can distinguish confirmed associations from unknown/needs-review |
| T04 | Open Game Mods / Mod Radar audit | Can explain Find → Match → Protect and locate ambiguous mods |
| T05 | Find and mark a **disposable** test file for protected/manual review | The Graveyard does not imply unknown game data is safe |
| T06 | Move a new disposable non-game file to Recycle Bin with approval, then restore through Undo Center | Exact bytes returned; no overwrite of an existing target |
| T07 | Create a Resurrection Kit using only newly created disposable sample Saves and Mods folders | User understands selected roles and missing-source warnings |
| T08 | Preview then rehearse that kit in a new, isolated folder | Preview, integrity result and temporary cleanup understandable |
| T09 | Create a second Living Kit version; compare using Time Machine | Old version retained, differences understandable |
| T10 | Prepare a disposable PC-to-PC transfer folder | Copies only the verified kit and manifest; guide is understandable |
| T11 | Test how the app explains an unsupported or unknown mod manager | Reports limitations instead of promising complete restoration |
| T12 | Close/reopen app, verify saved settings; perform approved upgrade/uninstall on disposable test installation | No removal of game/mod/save data or unexpected background behavior |

Never test permanent deletion or attempt to break real mod installations.

## The exact same questions for EVERY tester

For **Q01–Q10**, use the **same five-point scale**: 1 = Strongly disagree, 2 = Disagree, 3 = Neither, 4 = Agree, 5 = Strongly agree, with **N/A** where a task is unsupported. Keep all wording below unchanged for every respondent.

1. **Q01**: "It was easy to understand what Game Grave does before I started scanning."
2. **Q02**: "I could tell which game and mod information Game Grave had actually verified."
3. **Q03**: "The Game DNA relationship graphic helped me understand what belongs together."
4. **Q04**: "The Mod Radar visual explanation helped me understand why some files require review."
5. **Q05**: "I understood the difference between apparently occupied space and disk space I would actually free."
6. **Q06**: "The Graveyard clearly explained which items were protected and why."
7. **Q07**: "I felt confident that Game Grave would not delete my real games, mods, or saves without permission."
8. **Q08**: "The Undo Center recovery steps were easy to follow for my disposable test file."
9. **Q09**: "The Resurrection Kit preview and rehearsal made its limitations clear."
10. **Q10**: "The interface was easy to navigate, read, and use at my screen size."

**Q11** (single choice, required): "Would you install Game Grave again on your own gaming PC?" Answer: **Yes / Maybe / No**.

**Q12** (free text, optional): "What was the single most confusing, unsafe-feeling, broken, or missing part of your experience?" If possible, cite task ID, not file paths or screenshots.

## Fixed issue-report questions (if a task fails)

Use exactly the same five labels on every report: **Task ID; what I expected; what happened; steps to repeat using disposable files; severity**. Severity options:
- **P0**: Data loss, unexpected deletion, security/privacy breach (stop testing, no release).
- **P1**: Unsafe apparent behavior, failed verified restore, installer corruption, frequent crash (block release).
- **P2**: Incorrect classification or major usability blocker (triage before candidate sign-off).
- **P3**: Minor appearance, wording or optional visual issue.

A reviewer should reproduce and classify each report. An unverified claim is not silently dismissed.

## Acceptance analysis (do not move the goalposts after collection)

- Report counts per task across **independent testers**, including assisted, failed and N/A. Never divide by all testers when a task is unsupported.
- Report the median and full distribution for Q01–Q10, and Yes/Maybe/No counts for Q11.
- Summarize Q12 themes without quoting personal data. Track the top confusing steps and visual guide feedback separately.
- Any confirmed P0/P1 blocks the release candidate until fixed and re-tested; beta does not pass just because the average satisfaction score is high.
- Require a documented test matrix spanning Windows 10 and 11, varying screen scaling, launcher combinations and some heavily modded setups. Exact tester count and pass thresholds must be approved **before** enrollment and linked in issue #15.
- Privacy: store participant responses using a chosen secure collection workflow, collect no file inventory, and retain only necessary, redacted reports. Publish a retention/deletion schedule before inviting anyone.
- Link the final anonymized aggregate analysis and manual sign-off evidence to [M6 issue #15](https://github.com/wrightausername/Game-Grave/issues/15). Only then consider M7 1.0.0 stable.

**Release gate:** BETA NOT STARTED. Completing this document is planning, not recruitment, beta execution, QA certification, or release approval.


## Frozen Q1 responses and offline aggregate analyzer (prepared, not launched)

The exact T01–T12 tasks and Q01–Q12 wording above remain unchanged. For each
tester's optional **local** structured result, run
`python tools/beta_feedback.py --blank-form new-response.json`. Complete
`os`, every `tasks.T01`–`tasks.T12`, every `ratings.Q01`–`ratings.Q10`,
and `q11` after the **signed**, owner-approved beta test. Use task outcomes
`succeeded without assistance`, `succeeded with assistance`, `failed`,
or `not applicable`. For ratings use integer 1–5, or `N/A` only where
applicable. Issue entries use the five fixed report fields
`task_id`, `expected`, `actual`, `steps_disposable`, `severity`
(P0–P3). Do not put usernames, account IDs or other personal data into results.

Once an authorized coordinator has redacted and collected the completed files,
create one local JSON object `{"schema":1,"responses":[...completed records...]}`
and run `python tools/beta_feedback.py --analyze completed.json --output aggregate.json`.
The analyzer refuses mismatched build identifiers and questionnaire versions,
missing ratings, malformed scales, duplicate JSON keys or oversized input. It
produces task outcome counts, Q01–Q10 distributions and medians, Q11 counts,
issue severity/task counts and OS coverage only, **not** any free-text responses
or user paths. Aggregate totals cannot establish independent testers by
themselves. The CLI never uploads or sends messages. A new output never
overwrites an existing report.

The analyzer always marks `m6_beta_complete=false` and
`m7_1_0_release_authorized=false`. Human reviewers must approve a tester
count, success thresholds, P0/P1 issue dispositions, privacy retention policy
and final signed candidate before changing the release gates. The prepared
tool is not permission to recruit testers or declare M6 complete.
