# M3 Resurrection Kit: Windows acceptance matrix

**Status: OPEN.** This is not the M6 closed beta. Use synthetic files or explicitly disposable mod-manager fixtures. Preserve a second independent backup; never modify live saves, MO2/Vortex records, Steam libraries or game installations for a test.

| Test | Disposable setup | Acceptance |
|---|---|---|
| M3-01 | Saves and Mods folders with Unicode filenames | Each role saved, SHA-256 and CRC verified, source bytes unchanged |
| M3-02 | Saves+Mods+Profiles with MO2-style modlist | Missing enabled entries highlighted; disabled entries not labeled disposable; dependencies unknown |
| M3-03 | Tampered sidecar/ZIP, unsupported Windows names | Restore refuses before changing any existing game directory |
| M3-04 | Existing ZIP, manifest or partial output name | No overwrite; no unrelated temporary output removed |
| M3-05 | Archive changes between preview and restore | Exact reviewed SHA-256 rechecked, staged recovery rolled back |
| M3-06 | Unicode, case collision, existing restored folder | Valid names recover; unsafe collision refused |
| M3-07 | Symlink/junction in source, rehearsal, history, transfer parent | Stops without following any redirected ancestor |
| M3-08 | Disk full, locked files, interrupted extraction | Clear errors, no live overwrite; incomplete transfers labeled |
| M3-09 | Isolated Resurrection Rehearsal | SHA checks pass, temporary scratch cleaned, game launch not falsely claimed |
| M3-10 | Living Kit version and Time Machine comparison | Old kit unchanged, fresh approval for changes, versions not overwritten |
| M3-11 | Portable copy transferred to different disposable Windows PC | ZIP+manifest checksum verified, no licenses/game executables copied |
| M3-12 | Clean *disposable* MO2 instance | User approves exact reconnect paths; new profile and missing folders only; existing manager state preserved |
| M3-13 | Vortex or unsupported manager | No LevelDB mutation or misleading live-state restoration claim |
| M3-14 | Windows 10/11 interactive GUI, scaling 100%–200% | Buttons reachable, keyboard workflow, accurate error messages, bounded responsiveness |

Each report records OS build (no username), source commit, fabricated test paths, expected/actual, pass/fail/N/A and redacted evidence. Unit tests are necessary but not enough. Attach reviews to [M3 issue #12](https://github.com/wrightausername/Game-Grave/issues/12).

**M6 beta:** Once M1–M5 have been signed off, use [BETA_TEST_PROTOCOL.md](BETA_TEST_PROTOCOL.md) with exactly the same 12 questions and safe task order for every participant. No testers recruited beforehand.
