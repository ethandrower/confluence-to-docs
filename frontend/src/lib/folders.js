// Turning the flat bucket list into a tree, shared by the customer's file
// page and the agent's client view.
//
// It lives here rather than in the files store because the agent side loads a
// different company's buckets through a different endpoint and must not touch
// the customer store — but the two views have to agree on the shape, or the
// "same structure your client sees" promise quietly stops being true.

/**
 * Build the folder tree from a flat bucket list.
 *
 * Each node carries three counts, because they answer different questions:
 *   ownCount   — files sitting directly here
 *   deepCount  — including every subfolder ("is there anything in this branch?")
 *   deepUnseen — of those, how many nobody has opened yet (staff only; the
 *                customer payload has seen === null, so this is always 0)
 */
export function buildFolderTree(buckets) {
  const folders = buckets.filter((b) => b.kind === 'folder')
  const byId = new Map(folders.map((f) => [f.id, { ...f, children: [] }]))

  const roots = []
  for (const node of byId.values()) {
    const parent = node.parent != null ? byId.get(node.parent) : null
    ;(parent ? parent.children : roots).push(node)
  }

  // Depth-first so a node's children are counted before the node itself.
  const tally = (node) => {
    const files = node.files || []
    node.ownCount = files.length
    node.deepCount = files.length
    node.deepUnseen = files.filter((f) => f.seen === false).length
    for (const child of node.children) {
      tally(child)
      node.deepCount += child.deepCount
      node.deepUnseen += child.deepUnseen
    }
    node.children.sort((a, b) => a.title.localeCompare(b.title))
    return node
  }
  roots.forEach(tally)
  roots.sort((a, b) => a.title.localeCompare(b.title))
  return roots
}

/** Ancestors of a bucket, root first, INCLUDING the bucket itself. */
export function folderPath(buckets, id) {
  const byId = new Map(buckets.map((b) => [b.id, b]))
  const path = []
  const seen = new Set()
  let node = byId.get(id)
  while (node && node.kind === 'folder' && !seen.has(node.id)) {
    seen.add(node.id)
    path.unshift(node)
    node = node.parent != null ? byId.get(node.parent) : null
  }
  return path
}

/** Unseen files directly in a bucket — used for the flat buckets (General,
 *  requests) that sit outside the tree but still want a dot. */
export function unseenIn(bucket) {
  return (bucket?.files || []).filter((f) => f.seen === false).length
}

/**
 * Every file across every bucket, annotated with where it lives.
 *
 * Backs the "All files" home. Request files are included deliberately: someone
 * who uploaded three PDFs against "CV" and now wants them filed under a folder
 * can only do that if they can see them next to everything else, and moving
 * one out does not un-satisfy the request — ChecklistItem.linked_file points
 * at the file, not at whichever bucket it currently sits in.
 *
 * Newest first, because the reason to open this view is nearly always "deal
 * with the thing I just uploaded".
 */
export function flattenFiles(buckets) {
  const rows = []
  for (const b of buckets || []) {
    for (const f of b.files || []) {
      rows.push({
        ...f,
        bucketId: b.id,
        bucketKind: b.kind,
        location: b.kind === 'general' ? 'Not in a folder' : b.title,
      })
    }
  }
  return rows.sort(
    (a, z) => String(z.uploaded_at || '').localeCompare(String(a.uploaded_at || '')),
  )
}
