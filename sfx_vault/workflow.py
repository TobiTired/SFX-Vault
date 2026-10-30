"""Virtual collections and explicit production actions. No source-file writes."""
import time

DEFAULT_WORKFLOW = dict(auto_preview=False, volume=70, track_usage=True)

def preferences(catalog):
    return DEFAULT_WORKFLOW | catalog.setting('production_workflow', {})

def record_usage(catalog, ids, action):
    if action not in ('drag_started', 'copy_path'): raise ValueError('Unsupported production action')
    if not preferences(catalog)['track_usage']: return
    with catalog.db:
        for ident in set(ids):
            row = catalog.db.execute("SELECT id FROM sounds WHERE id=? AND status='managed'", (ident,)).fetchone()
            if row:
                catalog.db.execute('''INSERT INTO sound_usage(sound_id,last_used,use_count,last_action) VALUES (?,?,1,?)
                    ON CONFLICT(sound_id) DO UPDATE SET last_used=excluded.last_used,
                    use_count=sound_usage.use_count+1,last_action=excluded.last_action''', (ident, time.time(), action))

def collections(catalog):
    return catalog.db.execute('SELECT * FROM collections ORDER BY name COLLATE NOCASE').fetchall()

def create_collection(catalog, name):
    name = name.strip()
    if not name: raise ValueError('Enter a collection name')
    with catalog.db: return catalog.db.execute('INSERT INTO collections(name) VALUES (?)', (name,)).lastrowid

def rename_collection(catalog, ident, name):
    name = name.strip()
    if not name: raise ValueError('Enter a collection name')
    with catalog.db: catalog.db.execute('UPDATE collections SET name=? WHERE id=?', (name, ident))

def delete_collection(catalog, ident):
    with catalog.db:
        catalog.db.execute('DELETE FROM collection_members WHERE collection_id=?', (ident,))
        catalog.db.execute('DELETE FROM collections WHERE id=?', (ident,))

def change_members(catalog, collection_id, ids, add=True):
    with catalog.db:
        if not catalog.db.execute('SELECT 1 FROM collections WHERE id=?', (collection_id,)).fetchone(): raise ValueError('Collection no longer exists')
        for ident in set(ids):
            if add:
                catalog.db.execute('''INSERT OR IGNORE INTO collection_members(collection_id,sound_id)
                    SELECT ?,id FROM sounds WHERE id=? AND status='managed' ''', (collection_id, ident))
            else: catalog.db.execute('DELETE FROM collection_members WHERE collection_id=? AND sound_id=?', (collection_id, ident))

def memberships(catalog, ident):
    return catalog.db.execute('''SELECT c.* FROM collections c JOIN collection_members m ON m.collection_id=c.id
        WHERE m.sound_id=? ORDER BY c.name COLLATE NOCASE''', (ident,)).fetchall()

def usage(catalog, ident):
    row = catalog.db.execute('SELECT * FROM sound_usage WHERE sound_id=?', (ident,)).fetchone()
    return dict(row) if row else None
