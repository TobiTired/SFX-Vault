# V0.6 verification — 2026-10-19

## Results

- **66 automated tests passed**, 28.856 seconds, Windows 11 / Python 3.12 /
  PySide6 6.12.0 / Mutagen 1.48.1. No unhandled Qt slot errors.
- **Six workspace tests passed at 150% scale**, including the 1,338-row browser,
  1000×640 minimum window, collapsed panels, restored widths and expanded rows.
- Full populated workspace refresh/render: **0.203 seconds**; combined catalog
  filter: **0.015 seconds**; read-only organization preview: **0.062 seconds**.
  These are local fixture measurements, not guarantees for every machine/share.
- Python compilation passed for app, tests and tools.
- Existing tests cover migrations, recursive scanning, duplicate prevention,
  disconnected paths, protected manual metadata, organization approvals/rejections,
  import approvals/rejections, duplicates, collections, favorites, search,
  playback request ordering, seeking and focus-specific shortcuts.
- New tests cover saved panel visibility/widths, row density, small-screen layout,
  dedicated Pending Review tools, view keys/counts, unchanged source bytes/times,
  full 1,338-row UI rendering/search and all nine transparent ICO frames.
- Captured 1600×950 library/Pending Review and 1100×720 compact/expanded views using
  a separate catalog of 1,338 approved fixture sounds and eight pending imports.
  All **1,346** generated WAVs retained hashes, sizes and modification timestamps.
- Windows executable built successfully using PyInstaller 6.22.3. PE icon resources
  contain 16, 20, 24, 32, 40, 48, 64, 128 and 256px frames. The selected Vault / Wave
  mark is visible in the normal packaged app window/title bar.
- Created and read back the project-folder Windows shortcut: target, working
  directory and `.ico` reference are correct. Desktop creation is available via
  the supplied helper; no existing desktop shortcut was overwritten.

## Packaged startup and native REAPER check

The initial packaging smoke test exposed a DLL startup failure: PyInstaller found
an unrelated Poppler/Conda `icuuc.dll` on the development PATH. It has a different
export set from the Windows ICU API Qt expects. The build spec now excludes that
copy. The corrected executable was launched normally outside the test sandbox with
an isolated sample catalog. Its window opened, the inspector showed the selected
MP3 and its read-only source location, and the player reached 0:02 / 0:02 without a
playback error. This verifies player progress, not a subjective listening assessment.
No Windows library or security setting was changed.

The user physically tested the **corrected packaged V0.6 window** in a clean REAPER
project and confirmed **all three work**:

1. MP3 insertion.
2. WAV insertion.
3. Two selected WAVs inserted together.

After the tests, all four original MP3/WAV fixture files still matched their prior
SHA-256 hashes, byte sizes and original modification timestamps. Native file URLs,
Copy-only drag semantics and the original drag gesture lifetime remain covered by
regression tests. The automation API confines a drag to one window, so the user
performed the physical cross-window insertion checks.

The real 1,338-file user catalog was not opened or modified during development.
Synced `sources/` references were not edited. Older V0.4 evidence is archived in
[docs/V04_VERIFICATION.md](docs/V04_VERIFICATION.md).

## Hands-on checklist

Close earlier app versions before using the real catalog. Launch normally from
File Explorer, with the same Windows permissions as REAPER.

1. Open the packaged executable or normal launcher; confirm the expected library
   count and existing manual names/favorites/collections.
2. Search by display name, original filename and a tag. Combine format/category/
   confidence filters and Reset. Sort table headers.
3. Browse Favorites, Recently Added, Recently Used, Uncategorized, a parent category,
   subcategory and a collection. Scroll the sidebar to reach Collections.
4. Select a sound, edit its name/category/tags/favorite and Save properties. Assign it
   to two virtual collections; restart and rescan to verify metadata persists.
5. Resize both separators, hide/restore each panel, select Comfortable rows and
   restart. On a smaller display, hide Inspector to give the browser more room.
6. Preview WAV/MP3, pause/restart, click the seek bar and adjust volume. Check Space,
   arrows, Ctrl+F, Ctrl+R and Esc with list focus. Type normally inside metadata fields.
7. In Pending Review, inspect confidence and exact-duplicate warnings, preview a
   matching file, save any correction, and explicitly approve/reject selected rows.
   Confirm unreviewed rows remain pending and rejected source files remain in place.
8. Drag one MP3, one WAV and multiple approved rows to a clean REAPER project.
   Confirm actual inserted items; usage records alone do not prove insertion.
9. Confirm the selected icon at window/taskbar/shortcut sizes. Use the provided
   shortcut helper if desired; recreate old pinned shortcuts if Windows caches an
   earlier icon. Keep the packaged folder and `_internal` directory together.

## Known limits

Waveform drawing is omitted; seeking uses the existing reliable slider. Wide review
and history tables use horizontal scrolling, and inspector details scroll vertically.
Some secondary organization/collection/settings actions still use the existing
compact dialogs. The package is an unsigned local Windows build, not an installer;
other machines and display configurations need their own smoke test. No V0.5 or
V1.0 features were added.
