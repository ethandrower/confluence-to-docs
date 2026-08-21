// Turning the flat bucket list into a tree, shared by the customer's file
// page and the agent's client view.
//
// It lives here rather than in the files store because the agent side loads a
// different company's buckets through a different endpoint and must not touch
// the customer store — but the two views have to agree on the shape, or the
// "same structure your client sees" promise quietly stops being true.

/** A bucket's origin, tolerating payloads written before the field existed. */
export function originOf(bucket) {
  return bucket?.origin || 'customer'
}

/**
 * Build the folder tree from a flat bucket list.
 *
 * `origin` picks which tree: 'customer' for the folders they made, 'staff' for
 * the ones we pushed to them, null for both. The two are built separately and
 * rendered as separate sections rather than merged — they answer different
 * questions ("where did I file that" vs "what has CiteMed sent me") and only
 * one of them is editable.
 *
 * Each node carries three counts, because they answer different questions:
 *   ownCount   — files sitting directly here
 *   deepCount  — including every subfolder ("is there anything in this branch?")
 *   deepUnseen — of those, how many nobody has opened yet (staff only; the
 *                customer payload has seen === null, so this is always 0)
 */
export function buildFolderTree(buckets, origin = null) {
  const folders = buckets.filter(
    (b) => b.kind === 'folder' && (origin === null || originOf(b) === origin)
  )
  const byId = new Map(folders.map((f) => [f.id, { ...f, children: [] }]))

  const roots = []
  for (const node of byId.values()) {
    // byId only holds the requested origin, so a node whose parent belongs to
    // the other tree resolves to undefined here and becomes a root of this
    // one. That is what keeps a filtered tree complete rather than silently
    // dropping every branch whose parent was filtered out.
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
