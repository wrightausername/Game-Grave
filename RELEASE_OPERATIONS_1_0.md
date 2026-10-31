# Game Grave 1.0 | Release operations, rollback and support

**Current status: NOT APPROVED FOR PUBLICATION.** This is an operator runbook, not evidence that any release gate has passed. Never publish a `v1.0.0` tag while `release_gate_status.json` says `NOT_READY` or `tools/release_audit.py --strict` blocks.

## Ownership and prerequisites

A designated release owner must sign off all M1–M6 acceptance items with traceable links in [RELEASE_1_0_PLAN.md](RELEASE_1_0_PLAN.md). Required independent evidence includes Windows 10 and 11 installed-app testing, byte-exact Undo Center recovery, real launcher/mod-manager fixtures, accessible keyboard/screen reader and DPI testing, signed installer identity, privacy/legal review, and the fixed closed-beta test results. A green CI check alone cannot sign a human acceptance gate.

A production release also requires an owned code-signing certificate and a secure approved signing process, a versioned immutable distribution location, a support contact and privacy policy, and an owner-approved rollout/rollback decision. A **live, legitimate lifetime Pro issuer and payment settlement** must be verified if Pro is sold. Do not collect payment before that exists. Free continues without license keys or forced accounts.

## Build and trust procedure

1. Freeze the reviewed source commit and generate an unsigned Windows installer candidate. Run unit, native Recycle Bin, M3 restore, M4 Tk and installer lifecycle checks. Preserve each relevant CI run URL and redacted evidence.
2. Run independent Windows 10/11 clean-install, cross-version upgrade, uninstall and rollback rehearsals on disposable test profiles. Verify settings, Never Touch entries, Undo Center recovery records, saves and mod folders survive correctly.
3. Freeze candidate approval, sign with an authorized trusted publisher certificate in secure release infrastructure, timestamp it, and compute the **final signed executable's** SHA-256. Signing changes file bytes. Do not reuse the unsigned hash.
4. Record the exact final signed installer filename, final SHA-256, source commit, pinned publisher thumbprint and timestamp in an independently approved immutable release record. These values cannot originate solely from a candidate's own JSON.
5. Produce the final signed metadata `GameGrave_Setup_v1.0.0.build.json` with the required exact fields described in [M5_WINDOWS_QA.md](M5_WINDOWS_QA.md). Confirm all seven ledger milestones and total gate status are READY with evidence and actual verifiers.
6. Run `python tools/verify_signed_release.py --installer <final-exe> --manifest <build-json> --trusted-sha256 <independently-reviewed-digest> --reviewed-source-commit <exact-commit> --pinned-publisher-thumbprint <trusted-thumbprint>`. The command is read-only and fails if signature, timestamp, hash, source identity or human gates are not valid.
7. An authorized owner must separately approve uploading that exact immutable signed package, the SHA-256 and verified release notes. Confirm that users can retrieve the exact bytes, install without a forced account, and reach support and recovery instructions.

The current **unsigned** developer installer always sets `signed=false` and `release_approved=false`. It must fail this verification and **must not** be renamed to pretend it is a production package.

## Rollback and release incident response

Keep the previous independently verified signed version, its exact SHA-256, notes and installation instructions available. On a serious install, unsafe cleanup, data-integrity or security issue, immediately stop new downloads/advertising for the affected release, disable any future update advertisement, and document the exact build identifier and conditions. Do not alter or replace an already published installer in place. Retain the original immutable artifact for forensic diagnosis.

No remote automatic rollback exists in the preview. For a manual downgrade, verify the earlier package's publisher signature and checksum; test upgrade/downgrade implications on a disposable Windows profile before giving users instructions. Never claim settings or recovery history are backward compatible unless actually tested. Preserve local Game Grave settings, Never Touch rules, Undo Center logs and Resurrection Kit ZIP+manifest pairs. Avoid instructing people to uninstall in a way that loses access to Recycle Bin or backups.

If a customer reports unexpected deletion or failed restore, treat as **P0/P1 until triaged**: advise them not to empty the Recycle Bin, stop cleanup attempts on the affected drive, retain an independent backup, and avoid writing additional data unnecessarily. Investigate locally generated activity records and an exact repro on disposable files. No automatic upload of personal logs, account IDs, file paths, licensing keys, modlists or game saves is permitted.

If a paid entitlement or key exposure is suspected, pause activation and purchases while investigating. Only a properly authenticated backend may revoke or reissue entitlements. Never send private signing keys, user payment data or activation keys with support reports.

## Support and privacy checklist

Before publication, record and approve a functioning support contact (none is configured yet), report severity escalation policy, privacy disclosure, data retention/deletion schedule, ownership of updates, incident reporting process, and Windows compatibility limits. Support should ask for **redacted** build/version, broad OS type and reproducible steps with disposable data, not private save files.

Current capabilities that must be stated accurately: offline Free; optional local scans; never permanent-delete by fallback; Windows Recycle Bin and best-effort Undo; local Game DNA associations; conservative Mod Radar; archive/recording heuristics; staged Resurrection Kit restore; no guaranteed launcher/manager compatibility; no live Pro activation or signed update service in the engineering preview.

## Release criteria

M6 is complete only after the *signed* candidate's real tester cohort used the fixed [BETA_TEST_PROTOCOL.md](BETA_TEST_PROTOCOL.md) task order/question wording, independent testers were verified appropriately, owner-approved success thresholds were evaluated, all P0/P1 issues were resolved and retested, and the results were signed off. M7 can then be finalized only by the designated human owner with the exact signed artifact and support commitments.

This runbook does **not** change `release_gate_status.json`, trigger a release or impersonate human approval.
