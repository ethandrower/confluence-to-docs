/**
 * Turning a user's gesture into a list of {file, path} pairs.
 *
 * There are two entirely separate browser APIs for this and neither one covers
 * both cases:
 *
 *  - The file picker with `webkitdirectory` gives File objects carrying
 *    `webkitRelativePath`. Easy.
 *  - Drag-and-drop does NOT. `dataTransfer.files` flattens to nothing useful
 *    for a directory — you must go through `dataTransfer.items` and the
 *    webkitGetAsEntry tree, which is async and has two sharp edges (see below).
 */

// Names that are filesystem bookkeeping, not documents. Uploading these is
// never what someone meant by "upload this folder".
const JUNK = new Set(['.ds_store', 'thumbs.db', 'desktop.ini', '.localized'])

export function isJunk(name) {
  const lower = (name || '').toLowerCase()
  // Dotfiles as a class: .git/, .env, editor droppings.
  return !name || lower.startsWith('.') || JUNK.has(lower)
}

/** Strip the leading directory the browser prepends, so paths are relative to
 *  what was dropped rather than to its container. */
export function dirOf(relativePath) {
  const parts = (relativePath || '').split('/').filter(Boolean)
  parts.pop() // drop the filename
  return parts.join('/')
}

/**
 * Read every entry in a directory.
 *
 * `readEntries` returns AT MOST 100 entries per call and signals "done" with
 * an empty array — a single call silently truncates any folder with more than
 * 100 children, which is the classic way folder upload appears to work and
 * quietly loses files.
 */
function readAllEntries(reader) {
  return new Promise((resolve, reject) => {
    const all = []
    const next = () => {
      reader.readEntries((batch) => {
        if (!batch.length) return resolve(all)
        all.push(...batch)
        next()
      }, reject)
    }
    next()
  })
}

function fileOf(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject))
}

/** Depth-first walk of one dropped entry, accumulating {file, path}. */
async function walk(entry, prefix, out) {
  if (isJunk(entry.name)) return
  if (entry.isFile) {
    const file = await fileOf(entry)
    out.push({ file, path: prefix })
    return
  }
  if (!entry.isDirectory) return
  const dir = prefix ? `${prefix}/${entry.name}` : entry.name
  const entries = await readAllEntries(entry.createReader())
  for (const child of entries) await walk(child, dir, out)
}

/**
 * Extract {file, path} pairs from a drop event.
 *
 * The second sharp edge: a DataTransfer's items are neutered as soon as the
 * event handler yields, so every entry handle must be grabbed synchronously
 * BEFORE the first await. Hence the two loops.
 */
export async function filesFromDrop(dataTransfer) {
  const items = dataTransfer?.items
  if (!items || !items.length) {
    // No items API — fall back to the flat list, which is all we can get.
    return Array.from(dataTransfer?.files || [])
      .filter((f) => !isJunk(f.name))
      .map((file) => ({ file, path: '' }))
  }

  const entries = []
  for (const item of items) {
    if (item.kind !== 'file') continue
    const entry = item.webkitGetAsEntry?.()
    if (entry) entries.push(entry)
  }

  if (!entries.length) {
    return Array.from(dataTransfer.files || [])
      .filter((f) => !isJunk(f.name))
      .map((file) => ({ file, path: '' }))
  }

  const out = []
  for (const entry of entries) await walk(entry, '', out)
  return out
}

/** Extract {file, path} pairs from an <input> change, directory or not. */
export function filesFromInput(fileList) {
  return Array.from(fileList || [])
    .filter((f) => !isJunk(f.name))
    .map((file) => ({ file, path: dirOf(file.webkitRelativePath) }))
}

/**
 * Split a batch into what we can upload and what we cannot, so the UI can say
 * "312 uploaded, 18 skipped" instead of showing 18 red rows the customer can
 * do nothing about.
 */
export function partitionByExtension(items, allowed) {
  const ok = []
  const skipped = []
  for (const item of items) {
    const name = item.file.name
    const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : ''
    if (allowed.has(ext)) ok.push(item)
    else skipped.push(name)
  }
  return { ok, skipped }
}

/** Distinct directory paths in a batch, shallowest first so parents are
 *  created before their children. */
export function pathsIn(items) {
  const set = new Set(items.map((i) => i.path).filter(Boolean))
  return [...set].sort((a, b) => a.split('/').length - b.split('/').length || a.localeCompare(b))
}

/**
 * Dropping folder "specs" while already inside "specs" means "re-upload
 * specs", not "nest specs inside itself".
 *
 * Without this you get specs/specs, and it is easy to hit by accident: a
 * finished folder upload navigates into the folder it just created, so
 * dropping the same tree twice would bury the second copy a level down
 * instead of merging it into the first.
 *
 * Only fires when the whole batch shares ONE top-level folder — dropping two
 * sibling folders at once, one of which happens to share the current folder's
 * name, is not a re-upload of either.
 *
 * Returns the batch unchanged when the rule doesn't apply, so callers can test
 * identity to know whether it fired.
 */
export function mergeIfSameFolder(items, currentFolderTitle) {
  if (!currentFolderTitle) return items
  const tops = [...new Set(pathsIn(items).map((p) => p.split('/')[0]))]
  if (tops.length !== 1) return items
  if (tops[0].toLowerCase() !== String(currentFolderTitle).toLowerCase()) return items
  return items.map((it) => ({ ...it, path: it.path.split('/').slice(1).join('/') }))
}
