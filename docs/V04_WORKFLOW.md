# SFX Vault V0.4 — Production Workflow

V0.4 extends the existing app with native Windows file dragging, keyboard auditioning, Recently Used, virtual collections, combined filters and persistent production settings. V0.1–V0.3 indexing, classification and explicit import approval remain in place. Source audio is only read; physical filenames, folders and existing REAPER project references stay unchanged.

## Upgrade and launch

Close the previous version and double-click **Launch SFX Vault.bat** from File Explorer. This starts a normal Windows application. The default catalog remains `%LOCALAPPDATA%\SFX Vault\catalog.sqlite3`; no re-import or reapproval is required. If you use a custom data directory, launch with that same `--data-dir` argument.

V0.4 migrates the catalog transactionally to schema 4. A populated V0.3 catalog first receives `catalog.sqlite3.v03-backup.sqlite3` beside it using SQLite's backup API. The backup includes committed WAL data and is not overwritten on later launches. Migration adds only virtual collections/membership and production usage tables. Existing sound paths, IDs, manual metadata, favorites, approval states, monitoring settings, import history and organization decisions are preserved. Older catalogs retain their earlier migration backups too.

Keep earlier versions closed while V0.4 is running. To return to V0.3, use its backup in a separate data folder instead of opening the upgraded catalog with older code. Saved V0.1 watch locations remain disabled unless explicitly enabled.

For a new installation, install Python 3.12 or newer, open PowerShell in this folder, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m sfx_vault
```

Dependencies are already installed in this workspace. The app runs offline after installation. No accounts or external services are used.

## Production workflow and REAPER

Select an approved sound in the list, press and hold the left mouse button on the sound, and drag it to REAPER's timeline. Drop onto an existing track or onto empty timeline space. Use Ctrl/Shift to select multiple rows first, then drag from the selected group. Qt supplies local file URLs through Windows native file transfer with Copy semantics; it does not use a plain text path as its drag payload. A drag label shows the file count. Original audio remains in place.

A short background check skips missing/unreadable files before the native drag begins. The UI continues processing events while waiting, with a 750 ms limit so disconnected shares cannot hold the gesture indefinitely. Keep the mouse button held. If the check times out, the drag cancels with a status message; try again once the drive is available. A successful drag start or Qt drop result does not, by itself, prove REAPER inserted the sound. Recently Used records the initiated export action, not verified insertion.

**Windows permissions matter:** launch SFX Vault normally from File Explorer, at the same Windows permission level as REAPER. During V0.4 testing, a low-integrity Codex AppContainer process showed the prohibited-drop cursor over normal REAPER. After relaunching the isolated sample app as a normal, non-elevated Windows process, the user confirmed that MP3, WAV, and multiple-file drops all worked. No Windows security settings were changed. The normal launcher avoids the test sandbox; elevated REAPER may still reject drops from a normal app.

**Fallback:** select a sound and use Copy full path (Ctrl+C with the list focused). In REAPER choose Insert > Media file, paste one original path into the filename field, and insert it. Open file location also reveals the original in Explorer, where it can be dragged using Explorer's native file transfer. These are explicit user actions; SFX Vault never edits a REAPER project directly. REAPER's own import preferences can affect track placement, copying, resampling and peak-cache creation.

## Fast auditioning and shortcuts

Production Workflow settings contains automatic preview (off by default), remembered preview volume, usage tracking preferences and the shortcut reference. Adjusting the bottom volume also persists immediately. Automatic preview waits briefly for navigation to settle and previews only the latest current sound. A single player prevents overlapping previews. Missing/offline source checks run in workers; stale requests cannot replace a newer preview. The playing sound's name and source tooltip remain visible when browsing other results. Filters do not stop an explicit preview; Esc from the list does.

| Shortcut | Action and focus |
|---|---|
| Ctrl+F | Focus search in the main window |
| Space | Play/pause, when the sound list has focus |
| Up / Down | Navigate results; audition automatically if enabled |
| Ctrl+R | Restart selected sound from the beginning, list focus |
| Esc | Stop preview with list focus; dialogs keep their normal dismissal behavior |
| Ctrl+C | Copy selected original paths with list focus; normal copying in text editors |
| Ctrl+D | Toggle favorites for selected list rows |
| Ctrl+Shift+C | Add selected approved sounds to a collection, list focus |
| Enter | Focus the selected sound's editable display name, list focus |

Use the bottom player for previous/next, elapsed/total time, volume and seeking. Click the progress bar to seek directly; keyboard slider controls also work. Unsupported formats or disappearing sources produce a status message. Playback errors leave the library intact.

## Recently Used and virtual collections

Recently Used shows approved sounds for which a native file drag was initiated or the dedicated path-copy action was used. Selecting, previewing, editing metadata, revealing in Explorer and adding to collections do not count as usage. A cancelled drag can count because the explicit drag was started. Last used, action type and use count appear in the list and inspector. Frequently Used orders by usage count; Filters offers Recent use first and Frequent first as well. Disable future tracking in Production Workflow settings if desired; existing usage is retained.

Collections creates, renames or deletes virtual named groups. In the library, select one or more approved sounds and choose Add to collection, or press Ctrl+Shift+C. A sound can belong to several collections. Collections appear in the sidebar and persist across restart. To remove selected membership, open that collection and choose Remove from this collection. Deleting a collection removes only the group and memberships, retaining all catalog sounds and source audio. Pending sounds still require import approval before membership can be added.

The inspector retains the existing metadata editor and now includes duration, format, source location, last-checked availability, memberships, last used and action counts alongside original filename, category/subcategory, tags and favorite status.

## Combined search filters

Open Filters to combine category, subcategory, exact comma-separated tags (all must match), format, minimum/maximum duration in seconds, favorite status, collection, usage and last-checked availability. Search text remains active alongside them. Minimum/maximum durations are inclusive; zero means no limit. Collection sidebar membership and a different collection filter intersect, allowing sounds shared by both groups. Recently Used and Frequently Used views also work with other filters.

Examples: Movement / Footsteps with maximum duration 10; Ambience / Rain with minimum 60; Favorites only plus Combat; WAV format plus the clothing tag. Category/subcategory names come from your catalog and customized rules, including legacy category names.

Reset filters clears text search, format/confidence and advanced filters. It returns managed views to All Sounds; Pending Review and Import History stay on their page. Availability reflects the last folder scan or source check; rescan or preview to refresh it after a drive disconnects/reconnects. No network reads run during SQL filtering.

## V0.4 hands-on checks

Use a disposable REAPER project and an isolated catalog. This workspace includes generated quiet WAV/MP3 samples under `test-data/v04-reaper/samples`; the open test app uses only that catalog. For another test session:

```powershell
.\.venv\Scripts\python.exe -m sfx_vault --data-dir test-data/v04-reaper
```

Run that command from a normal Windows terminal, or use the launcher for your actual catalog. To regenerate sample WAVs, use `python -m tools.prepare_workflow_samples`; optional MP3 generation uses a locally installed Shutter Encoder FFmpeg if available and is not an application dependency.

1. In a clean REAPER project, drop the generated MP3 onto an existing track, a WAV onto empty timeline space, and multiple selected WAVs together. All three passed in the user's Windows/REAPER v7.79 test after matching process permissions. Verify placement and audible playback for your project/audio device and confirm original files remain unchanged.
2. Preview with Space, navigate with arrows, toggle auto-preview on/off and rapidly switch files. Type spaces into search/name/tags and confirm they do not act as playback shortcuts. Use Ctrl+R and Esc with list focus; click to seek. Restart the app and verify remembered volume.
3. Copy paths and initiate a drag, then inspect Recently Used/Frequently Used. Simple previews/selections should not increment usage. The action text must not claim insertion was verified.
4. Create two collections, multi-add sounds, remove membership, rename/delete a collection, then restart. Verify shared membership survives and deleting a collection keeps every sound/audio file.
5. Combine category/subcategory, tags, duration, format, favorites, availability, usage and collections. Reset filters and verify all managed results return. Test a missing/local or disconnected test share without touching the real library.
6. Recheck V0.3 monitoring, pending decisions, exact duplicates and explicit approvals plus V0.2 organization/manual corrections. V0.4 does not change those rules.

Audible playback, long-running real network outages and project/device-specific insertion preferences remain hands-on checks. No V0.5 features are included.

## Organize the existing library

1. Choose **Preview organization (read only)**. All managed sounds receive in-memory proposals from indexed filenames, folder paths and embedded metadata. This operation opens a read-only database connection: it does not persist proposals, decisions or metadata. It does not read source audio or require a connected LAN share.
2. Close that preview and choose **Review organization** to generate or resume a persistent review queue. Current and suggested values appear together. Scroll horizontally for additional current fields and read-only file locations.
3. Filter by suggested category or confidence. Double-click Suggested name, Suggested category or Suggested tags to edit a proposal. Categories can use `Primary / Subcategory`; tags are comma-separated. Edits to proposals are saved independently of the sound's current metadata.
4. Select rows with Ctrl/Shift, or choose **Select all visible**. Approve or reject the selected suggestions and confirm the count. Hidden rows are excluded. Only approved, current, unprotected suggestions change sound metadata. Rejection leaves the sound unchanged; unreviewed rows remain unchanged.
5. Close and reopen the review to resume. Unchanged approved/rejected proposals do not re-enter the queue. Changes to rule inputs create a new review proposal, never an automatic metadata overwrite. A stale proposal is skipped: reopen Review organization to regenerate its current snapshot.

**Manual protection:** V0.1 stores a single manual-edit marker per sound, rather than separate markers for name, category and tags. V0.2 conservatively protects the entire metadata set for those sounds. Protected rows still receive visible suggestions but cannot be batch approved. Editing a proposed value before approval marks the resulting metadata as manual. Favorites are independent and organization approval never changes them.

## Properties, categories and bulk changes

The right-hand properties editor supports display name, primary category, subcategory, comma-separated tags and a favorite checkbox. Click **Save details** to persist. Original filename and full path remain read-only. Restore suggested name fills the name editor; save to commit it. Manual saves are protected from automated organization and rescans.

**Manage categories** creates empty categories or renames a category and its descendants. Rename updates catalog metadata and matching rules, requires confirmation, and protects affected sounds. Categories are virtual; no folders are renamed. Category rules remain customizable in Settings as JSON objects with `category`, `keywords` and optional `tags` lists. Custom category names from older catalogs remain supported.

Select sounds in the library and choose **Bulk edit selected**. Each operation changes only its named fields, with a confirmation:

- Category replaces the full category, including any previous subcategory.
- Subcategory retains the primary category; an empty value clears its subcategory.
- Add tags merges tags without duplicates. Remove tags removes matching comma-separated tags, ignoring case.
- Favorite and Unfavorite change only favorite status.
- Reset automatic metadata restores the original filename as display name, clears tags and classification, and removes that sound's review decision so it can be suggested again. It skips manually edited sounds, and does not clear favorites or touch audio.

Bulk category/tag operations are deliberate user edits and protect the resulting metadata from future automation. No automatic operation clears manual protection.

## Search, scanning and confidence

Search is debounced and covers names, filenames, categories, tags and cached metadata. Browse Favorites, Uncategorized, category/subcategory views, and Recently Added. Use the confidence and format filters; click column headings to sort. Durations are in seconds. Existing play/pause, seeking, volume, previous/next, file path copy, Explorer reveal and file URL drag/drop remain available.

Confidence is a conservative rule-evidence score, not audio analysis or a measured probability. Unknown files have zero confidence. Conflicting equally strong categories stay Uncategorized with low confidence. A single matching keyword is medium confidence; stronger matching evidence raises it. Review low-confidence suggestions before approving.

Managed folders scan in a background worker at startup and when Rescan is selected. Rescanning updates technical metadata without replacing user organization. Missing and disconnected files remain cataloged. Partial traversal/read failures suppress missing-file reconciliation for that root. A later successful scan restores availability. Closing waits for active folder scanning; an unresponsive network share can delay it.

## Import Automation settings

Open **Import Automation** in the top toolbar. Add local or UNC folders, and set Enabled and Subfolders independently for each. You can edit an absolute folder path directly, including a temporarily disconnected share. Removing a configuration never deletes audio or catalog records. Global settings include background monitoring on/off, the polling interval (default 3 seconds), the unchanged period (default 5 seconds), duplicate detection, and checking for missed files at startup. Settings persist across restarts.

Monitoring uses background filesystem polling, which supports local folders and LAN shares without relying on network filesystem events. Nothing runs until a folder is configured and enabled. With startup checking enabled, new files added while the app was closed are detected on launch. With it disabled, the first successful traversal establishes a baseline: unchanged files already there are ignored until they change or you choose **Check imports now**. A manual check scans enabled folder configurations even if global background monitoring is paused. Disabled individual folders stay excluded.

Supported formats remain WAV, MP3, FLAC, OGG, OPUS, M4A, AIF/AIFF, WMA and AAC. Temporary extensions such as `.part`, `.crdownload` and `.tmp` are ignored. A final audio file with a companion temporary-download file is held back. Eligible files must retain the same size and modification time for the configured unchanged period, be readable, have readable audio metadata/duration, and remain unchanged during inspection. Truncated RIFF/WAV containers are held back. Unreadable or incomplete audio is retried; unchanged failures use a 30-second backoff. A valid audio stream whose transfer pauses longer than the unchanged period cannot always be distinguished from a completed download by filesystem checks; increase the period for slow transfers and preview before approval.

The configured import scopes remain reserved during managed-library scans, including while monitoring is paused. Library rescans update already approved sounds but cannot approve newly found files. New files found outside monitored scopes during an explicit library scan also go through stability checks and Pending Review. A manual library scan waits once for stability; a file still changing can be discovered on a later rescan. Startup checking is honored for library discovery, too. Existing approved sounds remain approved, and metadata corrections persist.

## Pending Review and duplicate handling

Open **Pending Review (count)** in the sidebar. The page shows a total and high/medium/low confidence counts plus potential duplicates. Search with the main search field; filter with the import category, confidence and format controls. Low-confidence rows are tinted and marked for closer review. High-confidence rows are preselected when entering the page; they still require explicit confirmation. Use Select all visible or Select high confidence to change the batch.

The table contains suggested name, category/subcategory, tags, confidence, duplicate status, duration, format, detection date, original filename and source folder. Scroll horizontally for the additional columns, or select a row to see its full original filename and path in the inspector. Double-click a row or use the bottom player to preview. Edit the properties and click Save details before approving; unsaved properties are preserved when new files arrive in the background.

**Approve selected** registers each selected sound at its current path. **Reject / skip selected** records rejection and leaves the source file untouched. Both actions require confirmation. Before approval, the worker checks that each source is still readable and matches its queued size/mtime; changed or unavailable files are skipped for another review. Database revisions prevent an old selection from overwriting a newer review. A failed database transaction rolls back decisions and retains the queue.

SHA-256 matching compares against managed sounds and other pending entries, including differently named files. The table marks exact matches; hover for their locations. In the inspector, choose a matching file, use **Preview matching file**, or **Open matching location**. Matching previews reuse the single player. Approval of duplicates asks whether to leave matching files pending or keep them as separate library entries. To skip them permanently, reject the selected matches. Files are never automatically deleted. When duplicate checks are enabled, approval waits for a cached hash. With checks disabled, the table says Not checked; enabling them later fills missing hashes in the background without reviving rejected records.

Unchanged approved, pending and rejected paths are not repeatedly hashed or enqueued. Rejected files remain rejected across restart. Changed content at a rejected path may produce a new pending generation; earlier history is retained. A timestamp-only change with identical SHA-256 content does not revive a rejection. Choose **Reconsider rejected** in Pending Review or settings to explicitly restore rejected entries. From Import History, select rejected rows to reconsider only those sounds. Reconsideration still requires approval and never changes source audio.

## History, notifications and reliability

**Import History** records the source filename/location, detection and decision dates, final category, status and each review generation. It includes pending, approved, rejected and superseded entries. Search the history or filter by category; click Date decided to see recent decisions. Recently Added uses the approval date for imported files. No audio copies are stored in history.

Progress and batch notifications appear in the status bar rather than individual pop-ups. Folder availability appears there on errors and in the summary's folder-status tooltip after checks. Unavailable shares retain their queue/history/catalog records; reconnected folders are checked again. Monitoring and hashing never run on the UI thread. Background work finishes or cancels before closing, though an operating-system call blocked on a disconnected share can delay shutdown.

V0.4 retains explicit import approvals and adds no source-file deletion or renaming, perceptual fingerprinting, cloud services, or AI audio recognition. No V0.5 work is included.

## Hands-on verification with samples

Use an isolated test catalog before organizing the actual library:

```powershell
.\.venv\Scripts\python.exe tools/create_samples.py
.\.venv\Scripts\python.exe -m sfx_vault --data-dir test-data
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

1. Launch with `--data-dir test-data`, then create a separate test-downloads folder and enable it under Import Automation. Keep the real library unconfigured for this first test.
2. Copy a generated sample WAV into the monitored folder. Wait roughly 6–9 seconds with default settings. Confirm it appears only in Pending Review and the sidebar badge increases. Check its fields and preview it.
3. Copy the same WAV using a different filename. Confirm both pending entries show duplicate matches. Preview each matching file from the inspector. Explicitly keep a selected duplicate as a separate entry to approve it; leave another pending or reject it. Verify that original paths and bytes remain unchanged.
4. Edit a pending name/category/tags and save. Approve only that row, then check that it appears in All Sounds. Reject another and restart; the rejected item should stay out of Pending Review while the undecided items remain. Use Reconsider rejected to restore it explicitly.
5. While the app is closed, add another sample to the watched folder. Restart with missed-file checking enabled and confirm it is detected. Test recursive monitoring, a disabled folder, and global pause. Try a `.wav.part` file; it should be ignored until completed and renamed to `.wav` **by you**.
6. Review Import History and its detection/decision dates. Test confidence and category filters, high-confidence preselection and batch approval/rejection. The generated samples are quiet tones; names classify them, not their audio content.
7. Add `sample-library` as a managed root. In V0.3, previously unknown sounds also require Pending Review approval; existing approved records are retained. Rescan twice and confirm there are no duplicate path records. Test an overlapping monitored directory and ensure files cannot bypass review.
8. Recheck V0.2 organization preview, saved manual corrections, favorites, bulk editing, search and playback. Existing managed sounds should stay approved across migration, restart and rescan. On a test network folder, disconnect/reconnect it and confirm records survive.

When satisfied, launch with your existing data directory and configure your actual download folders. You do not need to rescan or reapprove the existing 1,338 managed sounds.

See VERIFICATION.md for automated test coverage and remaining real-device checks. Audio codec support depends on Windows/Qt. The app is distributed as source with a launcher, not as a signed installer. Diagnostic logging stays in the selected application data folder.
