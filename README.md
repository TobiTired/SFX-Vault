# SFX Vault

Windows desktop sound-library manager. V0.7 adds a per-user Windows installer and
GitHub Releases updater to the approved V0.6 interface. Existing library scanning,
virtual names, metadata, import review, collections, playback and REAPER dragging
remain in place. Source audio is never moved, renamed, overwritten or deleted.

## Install

Download the Windows setup executable from
[GitHub Releases](https://github.com/TobiTired/SFX-Vault/releases).
Run Setup normally; Python and administrator privileges are not required.
Setup creates a Start Menu entry and offers an optional desktop shortcut.
Install over an earlier installed version to upgrade. Close SFX Vault first.

Data stays in `%LOCALAPPDATA%\SFX Vault\catalog.sqlite3`, outside the installation.
Upgrades, reinstallations and uninstall retain the catalog, metadata and settings.
Source audio remains wherever you put it. V0.7 uses the existing schema 4; no new
sound-table migration or reapproval is required. Custom data-directory users retain
support for `--data-dir` and should continue using the same argument.

## Updates

Use Settings → Updates & About. The configured repository is `TobiTired/SFX-Vault`
and can be changed. The dialog shows installed/available versions, plain-text notes,
status and download progress. Launch checks are optional and default off.

Checking never installs anything. Review notes, download, then separately approve
Install & restart. The app warns about preview and unsaved edits, backs up the
committed SQLite catalog, finishes background work and exits. A helper waits for
process exit and verifies the checksum again before opening standard Setup.
Skipped versions do not prompt again automatically; manual checks remain available.
Offline checks or failed/corrupt downloads leave the current app and library intact.

Downloads require a GitHub SHA-256 asset digest or the release's SHA256SUMS.txt,
matching installer name/version/size, and supported HTTPS GitHub addresses.
Builds are currently unsigned: checksums verify integrity, not publisher identity.

## Test update included

The separate **SFX Vault Update Test** edition includes a 0.7.0 installer and a
0.7.1 version-only update, with separate installation identity and data folder.
It does not use your production library. See [the complete test-update procedure](docs/V07_RELEASES.md#included-test-update-070--071).
The workspace's `release/test/Launch Test Update.bat` opens that flow.

## Development and release builds

[Build and publish instructions](docs/V07_RELEASES.md) explain local builds,
checksums, stable installer identity, data retention and the GitHub Actions workflow.
The workflow audits builds without automatically uploading artifacts or creating releases. No GitHub credentials are embedded.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-release.txt -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe tools/build_release.py --version 0.7.0 --repository TobiTired/SFX-Vault
```

Inno Setup 6 is required on the Windows build machine. A standalone folder build
is also produced. For source development, `python -m sfx_vault` or the existing
Launch SFX Vault.bat still works after dependencies are installed.

See [workspace and keyboard guidance](docs/V06_WORKSPACE.md),
[production workflow details](docs/V04_WORKFLOW.md), and
[verification results](VERIFICATION.md).

No V0.5 integration, V0.8 work, V1.0 work, AI categorization, cloud library sync or
UI redesign is included in this release.
