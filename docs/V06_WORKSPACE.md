# SFX Vault V0.6 — Library workspace

V0.6 redesigns the existing PySide6 application with charcoal surfaces, cyan accents,
consistent geometric icons, a dense sound browser, and a quieter command layout.
The existing schema-4 database and V0.1–V0.4 workflows are retained. No V0.5 or V1.0
features are included. Audio files are never renamed, moved, overwritten or deleted.

## Launch and upgrade

Close earlier versions, then open `dist/SFX Vault/SFX Vault.exe`, or use
`Launch SFX Vault.bat` for the source version. Keep the entire packaged `SFX Vault`
folder, including `_internal`, together. Python is not required for the packaged app.
The default catalog is still `%LOCALAPPDATA%/SFX Vault/catalog.sqlite3`.
Use the same `--data-dir` argument if you previously used a custom catalog.

V0.6 does not change schema 4. It stores only layout preferences in the existing
settings table. Older catalogs still use the existing transactional migrations and
versioned SQLite backups. Your sound IDs, paths, manual metadata, import decisions,
favorites, collections and production preferences remain compatible.

## Workspace

- **Library / Inspector:** the buttons beside the page title hide or restore each
  panel. Drag the separators to resize them. Visibility, panel widths and row density
  are saved when the window closes.
- **Compact rows / Comfortable rows:** compact fits more sounds; comfortable adds
  tags (or the original filename) beneath each display name.
- **Navigation:** library views and category/subcategory groups have counts and
  geometric icons. Collections appear below categories; scroll the sidebar to reach
  them. `+ Collection` opens the compact create/rename/membership controls.
- **Search:** Ctrl+F searches display names, original filenames, tags and existing
  searchable metadata. Format and confidence controls remain alongside Filters.
  Reset clears the search and combined filters.
- **Organize:** read-only preview, organization review, bulk metadata editing,
  category customization and collection management live in this menu.
- **Inspector:** edit display name, primary category, subcategory, tags and favorite,
  then Save properties. Original filename and source location remain read only.
  Copy path, Show file and collection assignment are nearby; More contains name
  restoration, favorite toggle and preview. Technical/source/collection details
  remain selectable and scrollable.
- **Pending Review:** a dedicated browser workspace retains confidence filters,
  duplicate warnings, high-confidence selection, explicit individual/batch approval
  and rejection. Saving properties alone does not approve an import. Rejected and
  unreviewed sources remain untouched. Matching-file previews are in the inspector.
- **Player:** Previous, Play/Pause, Next, click-to-seek, time, remembered volume and
  now-previewing name. The same single-player and stale-request protection remain.

Settings now groups Library settings, Import automation and Production workflow &
shortcuts. Existing dialogs use the same visual theme. See
[V0.4 workflow details](docs/V04_WORKFLOW.md) for import, migration, collection,
filter and keyboard semantics inherited by this release.

## REAPER

Select approved rows and drag their original files to REAPER; Ctrl/Shift selects a
batch. Launch both apps normally at matching Windows permissions. Do not launch
SFX Vault inside a restricted test sandbox for native cross-application dragging.
The Copy-only file URL payload and original drag gesture code are unchanged.
Pending files still require approval before production dragging.

Space previews, Ctrl+R restarts, Esc stops, Ctrl+C copies selected original paths,
Ctrl+D toggles favorites and Ctrl+Shift+C assigns a collection when the list has
focus. Text fields retain normal editing shortcuts. Enter focuses the name field.

## Selected icon and Windows assets

The user selected **Vault / Wave** from four vector concepts. Files in
`sfx_vault/assets/` include the concept sheet and editable SVG/PNG alternatives,
the selected SVG/512px PNG, and `sfx-vault.ico` with 16, 20, 24, 32, 40, 48, 64,
128 and 256px transparent frames. Window/application icons and Windows AppUserModelID
are set by the app. All nine sizes were verified in the executable's icon resources.

`SFX Vault V0.6.lnk` is a ready shortcut in this project folder. You can copy it to
your desktop. Alternatively run `Create Desktop Shortcut.bat`; it creates a desktop
shortcut without replacing an existing one. Keep this workspace in place because
that shortcut references its executable and icon.

To rebuild, use `Build Windows App.bat`. PyInstaller is a build-only dependency;
runtime requirements remain PySide6 and Mutagen. The spec excludes a conflicting
Poppler/Conda ICU DLL that the development PATH otherwise contributes; Qt uses the
Windows system ICU library. The corrected package was opened and MP3 playback was
verified on this Windows 11 computer. No system libraries or security settings were
changed. The executable is an unsigned local build, not an installer.

## Verification and screenshots

See [verification results and checklist](VERIFICATION.md).

- [Desktop library](test-data/v06-preview/library-desktop.png)
- [Pending Review](test-data/v06-preview/pending-review.png)
- [Small workspace](test-data/v06-preview/library-small.png)
- [Expanded rows](test-data/v06-preview/expanded-rows.png)
- [Icon concepts](sfx_vault/assets/icon-concepts.png)

Screenshots use an isolated fixture catalog with 1,338 approved sounds and eight
pending imports. Fixture names/categories are curated presentation data, not claims
about automatic classification accuracy. The real library was not opened.

Known limits: waveform rendering is intentionally omitted; preview uses the reliable
seek bar. Very wide Pending Review/history tables scroll horizontally. The inspector
scrolls vertically; hiding it provides more room on smaller displays. Native REAPER
insertion needs a physical cross-window check; automated tests verify drag payload,
Copy semantics and gesture lifetime but cannot prove insertion. Windows icon cache
may retain an old pinned shortcut until it is recreated. Testing on other computers
and display-scale combinations remains a hands-on release check.
