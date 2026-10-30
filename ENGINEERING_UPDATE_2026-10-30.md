# 2026-10-30 Engineering change review

This change set implements code, not only a proposal.

## Implemented in this branch
- Graveyard right-click menu: Details, Open Folder, Protect/Unprotect, Move to Recycle Bin (only where eligible). Right-click selects the row under the mouse. Shift+F10/Menu are supported.
- Reuses existing, explicitly confirmed, revalidated Recycle Bin workflow. No alternate removal code, no automatic or permanent delete. Built-in protection stays fixed; parent Never Touch rules can only be changed in Settings.
- Recomputes Graveyard eligibility whenever an individual user protection changes, persists Never Touch settings, and offers toolbar access.
- Read-only ESO .txt and World of Warcraft .toc addon descriptor metadata (title, version, limited dependency list), with conservative disclosure that metadata is not proof of current use or safe deletion.
- WoW _retail_ / _classic_ / _classic_era_ / _ptr_ default addon locations, with protected WTF account/settings folders; customized installs still need manually supplied scan roots.
- Automated unit-test workflow for Windows and Linux pull requests.

## Validation actually run
- On a Linux development copy: 102 Python unit tests passed (previous baseline 92).
- Headless Tk desktop smoke test passed on Linux using Xvfb.
- Code compiled locally. This is NOT a claim of native Windows validation or completed Windows CI.

## Remaining priorities
- Native Windows tests: right-click placement, DPI, keyboard accessibility, genuine Recycle Bin and Undo Center, permission errors, hardlinks/junctions, installed release.
- Complete cross-launcher and addon-manager evidence engine, profile manifests, and strict active/probable orphan/uncertain classification. A known path or addon descriptor alone does not prove an orphan.
- Duplicate archive/hash scanner with careful space accounting.
- Extend mod game/platform identifiers and custom paths with fixture-driven tests.
- Reliable Windows installer, updates, licensing/payment, and fair Free/Pro features; keep safety features free.
- Gamer humor and Easter eggs remain post-MVP only.

## Principles
The Graveyard does not delete games, managed mods, saves, settings or uncertain folders. The per-file review workflow always requests approval and refuses an unsafe action. Recycle Bin movement is not equivalent to freeing physical storage space.
