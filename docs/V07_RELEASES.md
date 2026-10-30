# V0.7 builds, GitHub releases and test updates

Repository: https://github.com/TobiTired/SFX-Vault

## Build

Windows x64, Python 3.12, PySide6/Mutagen, PyInstaller and Inno Setup 6 are needed
only on the build machine. End users install Setup and need no Python installation.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe tools/build_release.py --version 0.7.0 --repository TobiTired/SFX-Vault
```

Or use Build Installer.bat in the prepared development workspace. Set ISCC to an
alternate Inno compiler path if needed. Release output contains Setup, SHA256SUMS,
release notes, draft GitHub metadata and the standalone folder build. Keep the
whole standalone app folder together. Setup packages all its files automatically.

The build injects the same version into About, window title, executable PE version
resources, Setup and uninstall registration. Never reuse a published version for
changed binaries. The stable AppId is fixed for all future installers. Installation
uses LocalAppData/Programs/SFX Vault with no administrator requirement. Start Menu
is standard; desktop shortcut is optional. Setup refuses to update a running app
and never force-closes playback or unsaved edits.

## Publish

1. Update version.py for the next source version and write release-notes/X.Y.Z.md.
2. Commit the source, tests, build configuration and release notes. Never commit
   catalogs, source audio, test-data, local paths/profiles, build output or secrets.
3. Push tag vX.Y.Z, or run Windows installer from GitHub Actions with that version.
   The workflow tests, builds and audits locally on the runner. Artifact upload and release creation are deliberately disabled pending human review.
4. Review Setup on a disposable install, verify SHA256SUMS and notes, obtain publication approval, and create a stable release (neither Draft nor Prerelease). The updater uses
   GitHub's /releases/latest endpoint and ignores unstable/malformed releases.
5. Each stable release must contain SFX-Vault-Setup-X.Y.Z.exe and SHA256SUMS.txt.
   GitHub's asset SHA-256 digest is preferred; the checksum file is a fallback.

Manual alternative: create a GitHub Release tagged vX.Y.Z, paste RELEASE-NOTES.md,
and attach Setup plus SHA256SUMS.txt. No GitHub token is embedded in the app.
Public releases are required for the current updater. Failed/offline/rate-limited
checks are recoverable and do not alter the installed application or catalog.

## Update behavior

Settings → Updates & About provides version, configurable owner/repository,
manual checking, opt-in launch checking, release notes and progress. Launch checks
default off. Download and installation need separate explicit user actions.
Skipping a version suppresses future automatic prompts for that version; manual
checks can find it again. Changing repository resets that decline choice.

Downloads go into a unique temporary folder, with strict expected name/version,
size, HTTPS GitHub address and SHA-256 checks. Interrupted/corrupt downloads are
removed. A verified installer is rechecked immediately before handoff. A committed
SQLite backup, including WAL data, is saved in the catalog's update-backups folder.
Confirmation explicitly warns about playback and unsaved properties. The helper
waits for the app process to exit, rechecks the hash and opens standard interactive
Setup. Setup offers launching the upgraded app afterward. Cancelling Setup retains
the existing application and data. Normal installed-app restart uses the standard
AppData catalog; custom --data-dir users should relaunch with their usual argument.

Checksums protect transfer integrity; they are not publisher signatures. These
local builds are unsigned. Keep the GitHub publishing account protected. Adding
Authenticode or signed release manifests is a future distribution enhancement.

## Included test update: 0.7.0 → 0.7.1

The separate **SFX Vault Update Test** edition has a different AppId, mutex, shortcut
name, install folder and default data folder. Its 0.7.1 installer is deliberately a
version-only test update, not a production feature release. It must not be published
as the latest stable production release. Build both versions with:

```powershell
.\.venv\Scripts\python.exe tools/build_release.py --version 0.7.0 --test
.\.venv\Scripts\python.exe tools/build_release.py --version 0.7.1 --test
```

1. Install release/test/0.7.0/SFX-Vault-Setup-0.7.0.exe normally. Optionally create
   its desktop shortcut. Use generated/disposable sounds, never the real library.
2. Launch that installed test executable with --test-update and the absolute path
   to release/test/0.7.1/test-update.json. A companion Launch Test Update.bat is
   included in release/test for this workspace.
3. In Updates & About, Check for Updates. The explicit LOCAL TEST banner should
   show version 0.7.1 and test notes. Download, then Install & restart. Approve the
   close confirmation, finish Setup, and launch the new version.
4. Confirm About says 0.7.1 and the metadata/favorites/collections/pending records
   and preferences survive. Check preview, search, scanning and REAPER dragging.
5. Reinstall test 0.7.1 and uninstall from Windows Installed apps. Catalog and
   source audio must remain. The test edition keeps data in LocalAppData/SFX Vault
   Update Test; production uses LocalAppData/SFX Vault. Uninstall never removes
   either catalog. Delete test data yourself only when finished.

The local feed is enabled only by an explicit command-line argument, uses a
checksummed installer beside its manifest, and cannot be enabled by GitHub metadata.
Normal production checks use only GitHub HTTPS, never the local test feed.
