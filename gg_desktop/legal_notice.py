"""Draft in-app legal disclosure for Settings > About.

NOT a substitute for a separately accepted EULA, privacy notice or sales terms.
Product owner must arrange qualified legal review before public distribution.
Keep the plain-language statements accurate as implementation evolves.
"""

LEGAL_NOTICE_VERSION = "Draft for pre-release legal review / November 2026"

LEGAL_NOTICE = """GAME GRAVE | IMPORTANT LEGAL NOTICES & PRODUCT DISCLOSURES
Pre-release draft for legal review, not a substitute for the binding EULA,
Privacy Notice, purchase terms, or applicable consumer-protection law.

PLEASE READ BEFORE SCANNING, RECYCLING, BACKING UP OR RESTORING FILES.

1. WHAT GAME GRAVE DOES
Game Grave is a Windows gaming-library, file-discovery, storage-review,
mod-information, capture-review and optional recovery utility. Features may
identify installed games across supported launchers; display game artwork
and game update information; analyze file paths, directory entries, sizes,
timestamps and relationships; identify likely mod and addon locations;
show screenshots/recordings when specifically requested; and assist users
with backup, restore and Windows Recycle Bin operations. Game Grave is NOT
a replacement for Windows Backup, a professional data-recovery service, or
a guarantee that a game, save or mod will remain compatible or functional.
Some features are experimental or unavailable in preview builds.

2. NO AUTOMATIC AUTHORITY TO DELETE
An item appearing in a list, Graveyard, Mod Radar, Game DNA, or a warning is
NOT proof that the item is safe, unnecessary, unused, or yours to remove.
Age, file extension, directory name, launcher metadata and estimated size
can be misleading. You must review the exact selected items and authorize
each supported destructive operation. Important files may resemble junk.
Built-in exclusion rules, Never Touch settings, and confirmation steps reduce
risk but cannot identify every dependency, file ownership or unusual setup.
Do not remove a file unless you understand its purpose and have a backup.

3. WINDOWS RECYCLE BIN & UNDO LIMITATIONS
When supported, Game Grave asks Windows to move specifically approved items
to the Recycle Bin rather than permanently deleting them. A successful move
does not ensure long-term recoverability, does not immediately free disk
capacity, and may not survive Recycle Bin emptying, Windows cleanup, storage
changes, account/permissions changes or third-party tools. Logs, Undo Center
records and recovery verification are best-effort aids, not independent
copies of your original files. Restoration can fail, be partial or require
user decisions. Never rely on Undo Center as your only backup.

4. GAME SAVES, MODS, CONFIGS & RESURRECTION KITS
Save games, cloud saves, mod-manager profiles, load orders, custom patches,
configuration files, shader files, Workshop data and game installations
can be interdependent. Changing or restoring one part can corrupt data,
break a game, invalidate multiplayer rules or overwrite newer progress.
Game Grave cannot reliably infer all dependencies or guarantee a snapshot
contains everything necessary. Some recovery tools preserve metadata
rather than full file contents. Always confirm what was actually backed up,
verify restore points, and keep independent copies before making changes.
Do not overwrite the sole remaining copy of valuable personal data.

5. STORAGE FIGURES & FILE-CLASSIFICATION ACCURACY
Drive capacity, apparent file size, launcher-reported install size and
physically allocated disk space are different measurements. Sparse files,
compression, hard links, permissions, inaccessible areas, deduplication,
unknown launchers and filesystem changes can make analyses incomplete
or inaccurate. Quick scans may be deliberately bounded; Full Scan attempts
all accessible eligible locations but cannot bypass Windows security,
filesystem errors, excluded protected paths or hardware limitations.
An empty result is not a certification that nothing relevant exists.

6. GAMEPLAY PERFORMANCE & BACKGROUND WORK
Game Grave is designed to give foreground games priority and to pause or
defer supported background operations when it detects gameplay. Detection
cannot identify every game, virtual machine, monitor arrangement or process.
No software can promise literally zero CPU, memory, storage, network, battery
or frame-rate impact on every computer. Stop or cancel a scan if you notice
interference, heat, unusual activity or degraded performance. Do not run
resource-intensive maintenance during competitive or critical sessions.

7. SCREENSHOTS, RECORDINGS & PERSONAL CONTENT
Capture folders may contain personal or sensitive images and recordings.
Game Grave may inspect filenames and metadata in configured locations and
decode individual images for previews. You alone decide whether to keep or
send an eligible screenshot to the Windows Recycle Bin. Fast review shortcuts
and session-level confirmation do not remove the requirement for affirmative
per-item action and backend file-identity and protection checks. Treat every
capture as potentially irreplaceable. Video previews may open the Windows
default media player, subject to its separate settings and privacy rules.

8. OPTIONAL NETWORK FEATURES & THIRD PARTIES
Some optional or on-demand features may contact third-party services,
including Steam's official asset hosts for game artwork, official game
news/update sources, licensing/payment providers, or optional AI components
where supported and enabled. Their availability, terms, outages, content,
security and privacy practices are outside Game Grave's control. A game
identifier or requested resource URL may be shared with an image/news
provider to fulfill that request. Never assume local-only marketing language
applies to explicitly enabled online features. The separately published
Privacy Notice must accurately describe any personal data processed,
service providers, retention, choices and required disclosures.

9. OPTIONAL AI OUTPUT
An optional locally hosted or connected assistant, if enabled, may be
incomplete, wrong, out of date or unable to understand your exact setup.
AI suggestions are informational only and must not authorize deletion,
restore, purchases, license restrictions or administrative actions without
independent product safeguards and required user approval. Do not enter
passwords, account recovery codes, payment card numbers, or information you
are not entitled to disclose. Availability depends on your device, selected
components and applicable third-party licenses.

10. OWNERSHIP OF GAMES, MODS & BRAND ARTWORK
Game Grave is independent software, not sponsored, certified or endorsed by
Valve, Steam, Epic Games, EA, Blizzard, Microsoft, Ubisoft, GOG, game
publishers or third-party mod authors unless explicitly stated otherwise.
Third-party titles, trademarks, artwork, screenshots, game files and mods
remain the property of their respective owners. Displaying your installed
library or official cover art does not transfer a game license or grant
permission to redistribute copyright-protected material. You must comply
with launcher terms, mod licenses, copyright rules and anti-cheat policies.

11. ACCOUNTS, PURCHASES & LICENSES
If Game Grave offers a paid lifetime license, 'lifetime' means the duration
and scope expressly stated in the applicable purchase/license terms; it
does not promise perpetual updates, unchanged functionality, indefinite
server operation or continued compatibility with all future Windows or
launcher versions. Purchase price, taxes, payments, refunds, chargebacks,
device activations, online validation and support are governed by the
separately disclosed transaction and license terms. Nothing here removes
consumer refund, warranty or other legal rights that cannot be waived.

12. USER RESPONSIBILITIES
Use Game Grave only on devices and data you are authorized to access.
Maintain current independent backups before removing or restoring files.
Review paths, categories, selections, confidence labels and confirmation
screens carefully. Check available storage, running applications, disk
health and game/mod-manager instructions. Protect your Windows and gaming
accounts, use legitimate software and install signed builds from trusted
sources where available. You are responsible for ensuring your activities
comply with laws, licenses, employment/device policies and server rules.

13. SOFTWARE PROVIDED 'AS IS' TO THE EXTENT ALLOWED BY LAW
TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, AND SUBJECT TO ANY
MANDATORY CONSUMER RIGHTS, GAME GRAVE IS PROVIDED 'AS IS' AND 'AS
AVAILABLE', WITHOUT EXPRESS OR IMPLIED WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT, UNINTERRUPTED
OPERATION, DATA ACCURACY, CONTINUED COMPATIBILITY OR FREEDOM FROM ERRORS.
NO EXPLANATION, FEATURE LABEL, ESTIMATE OR SUPPORT MESSAGE CREATES A
WARRANTY UNLESS EXPRESSLY AGREED IN A SEPARATE BINDING WRITTEN AGREEMENT.
SOME JURISDICTIONS DO NOT ALLOW CERTAIN WARRANTY DISCLAIMERS, SO THESE
RESTRICTIONS MAY NOT APPLY TO YOU.

14. LIMITATION OF LIABILITY, SUBJECT TO LOCAL LAW
TO THE MAXIMUM EXTENT ALLOWED BY APPLICABLE LAW, THE DEVELOPER AND ITS
LAWFUL LICENSORS ARE NOT LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL,
CONSEQUENTIAL, EXEMPLARY OR PUNITIVE DAMAGES; LOST SAVES, MODS OR FILES;
LOST REVENUE, GOODWILL OR GAMING TIME; SERVICE INTERRUPTIONS; OR
THIRD-PARTY SOFTWARE BEHAVIOR ARISING FROM USE OF GAME GRAVE, EVEN IF
ADVISED OF THE POSSIBILITY. NOTHING EXCLUDES LIABILITY FOR FRAUD,
WILLFUL MISCONDUCT, PERSONAL INJURY, OR ANY OTHER LIABILITY THAT CANNOT
LAWFULLY BE LIMITED. ANY ENFORCEABLE MONETARY CAP OR DISPUTE PROCEDURE
MUST BE SET OUT IN SEPARATELY ACCEPTED, LEGALLY REVIEWED TERMS. THIS
NOTICE ALONE DOES NOT CREATE ONE.

15. SECURITY & PRIVACY LIMITS
The software is designed to minimize collection and avoid unnecessary
access to personal files. Local storage scans are not equivalent to
antivirus or malware detection. No system is immune to vulnerabilities,
malicious mods, compromised networks or third-party defects. Review the
current Privacy Notice before enabling optional online functionality.
Do not treat these disclosures as proof of an external security audit,
regulatory certification, encryption guarantee or breach immunity.

16. UPDATES, CHANGES & SUPPORT
Features, supported sources, safety rules, integrations, limits and
third-party availability may change. Future builds may require separate
permissions, revised terms or new privacy disclosures. Preview builds can
contain defects and are intended for evaluation, not the sole protection of
valuable content. Support, maintenance, response times, compatibility and
update availability are only promised where separately agreed in writing.

17. CONSUMER RIGHTS, CONFLICTS & CONTACT
Nothing in this notice is intended to override applicable consumer-protection,
data-protection, accessibility, product-liability or other non-waivable rights.
If a clause conflicts with binding laws or separately accepted terms, those
laws/terms control to the extent of the conflict. The developer must publish
a verified business/contact address, support channel, governing terms and
Privacy Notice before public launch. Do not infer these from an unsigned
preview. A qualified attorney should review this document for the countries
where Game Grave is offered.

IMPORTANT: This is an informational draft inside an engineering preview.
Simply seeing or opening this notice does not mean you have agreed to a
binding license agreement. Public release requires an explicit EULA and
Privacy Notice presented at the appropriate point of installation or sale.
"""
