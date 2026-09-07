import { describe, it, expect } from 'vitest'
import { buildFolderTree, originOf, folderPath, flattenFiles } from './folders.js'

const folder = (id, over = {}) => ({
  id, kind: 'folder', title: `F${id}`, parent: null, origin: 'customer',
  files: [], ...over,
})

describe('originOf', () => {
  it('treats a missing origin as the customer’s own', () => {
    // Payloads written before the field existed must not suddenly render as
    // read-only folders the customer can no longer touch.
    expect(originOf({ id: 1 })).toBe('customer')
    expect(originOf(undefined)).toBe('customer')
    expect(originOf({ origin: 'staff' })).toBe('staff')
  })
})

describe('buildFolderTree', () => {
  const buckets = [
    { id: 99, kind: 'general', title: 'General uploads', files: [] },
    { id: 98, kind: 'request', title: 'Send us X', files: [] },
    folder(1, { title: 'Mine' }),
    folder(2, { title: 'Mine sub', parent: 1 }),
    folder(10, { title: 'Ours', origin: 'staff' }),
    folder(11, { title: 'Ours sub', parent: 10, origin: 'staff' }),
  ]

  it('keeps requests and the general bucket out of the tree', () => {
    const ids = buildFolderTree(buckets).map((n) => n.id)
    expect(ids).not.toContain(99)
    expect(ids).not.toContain(98)
  })

  it('splits the two origins into separate trees', () => {
    const mine = buildFolderTree(buckets, 'customer')
    const ours = buildFolderTree(buckets, 'staff')
    expect(mine.map((n) => n.title)).toEqual(['Mine'])
    expect(ours.map((n) => n.title)).toEqual(['Ours'])
    expect(mine[0].children.map((c) => c.title)).toEqual(['Mine sub'])
    expect(ours[0].children.map((c) => c.title)).toEqual(['Ours sub'])
  })

  it('returns both trees when no origin is given', () => {
    expect(buildFolderTree(buckets).map((n) => n.title).sort())
      .toEqual(['Mine', 'Ours'])
  })

  it('surfaces a node whose parent was filtered out as a root', () => {
    // The subtle one. When a tree is filtered by origin, a node whose parent
    // belongs to the OTHER origin has no resolvable parent in this tree. It has
    // to become a root here — dropping it would silently hide a whole branch,
    // and the folder would exist on the server but be unreachable in the UI.
    const orphan = [folder(10, { origin: 'staff' }), folder(11, { parent: 10 })]
    const mine = buildFolderTree(orphan, 'customer')
    expect(mine.map((n) => n.id)).toEqual([11])
  })

  it('counts files in a branch, not just at the node', () => {
    const withFiles = [
      folder(1, { files: [{ id: 1, seen: false }] }),
      folder(2, { parent: 1, files: [{ id: 2, seen: true }, { id: 3, seen: false }] }),
    ]
    const [root] = buildFolderTree(withFiles, 'customer')
    expect(root.ownCount).toBe(1)
    expect(root.deepCount).toBe(3)
    expect(root.deepUnseen).toBe(2)
  })

  it('does not mutate the buckets it was given', () => {
    const input = [folder(1)]
    buildFolderTree(input, 'customer')
    expect(input[0].children).toBeUndefined()
    expect(input[0].deepCount).toBeUndefined()
  })
})

describe('folderPath', () => {
  it('walks to the root, root first, including the folder itself', () => {
    const buckets = [folder(1), folder(2, { parent: 1 }), folder(3, { parent: 2 })]
    expect(folderPath(buckets, 3).map((f) => f.id)).toEqual([1, 2, 3])
  })

  it('terminates on a cycle rather than hanging', () => {
    const buckets = [folder(1, { parent: 2 }), folder(2, { parent: 1 })]
    expect(folderPath(buckets, 1).length).toBeLessThanOrEqual(2)
  })
})

const f = (id, name, at) => ({ id, original_name: name, uploaded_at: at })

describe('flattenFiles', () => {
  it('gathers files from every bucket, whatever kind it is', () => {
    const rows = flattenFiles([
      { id: 1, kind: 'folder', title: 'specs', files: [f(10, 'a.pdf', '2026-01-01')] },
      { id: 2, kind: 'general', title: 'General uploads', files: [f(11, 'b.pdf', '2026-01-02')] },
      { id: 3, kind: 'request', title: 'CV', files: [f(12, 'c.pdf', '2026-01-03')] },
    ])
    expect(rows.map((r) => r.id)).toEqual([12, 11, 10])
  })

  it('includes request files, which is the whole point', () => {
    // Files uploaded against a request are exactly the ones customers want to
    // file away afterwards; excluding them would leave them unreachable from
    // the only screen that can move things in bulk.
    const rows = flattenFiles([
      { id: 3, kind: 'request', title: 'CV', files: [f(12, 'cv.pdf', '2026-01-03')] },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].location).toBe('CV')
  })

  it('labels unfiled files rather than showing the bucket\'s database name', () => {
    const rows = flattenFiles([
      { id: 2, kind: 'general', title: 'General uploads', files: [f(11, 'b.pdf', '2026-01-02')] },
    ])
    expect(rows[0].location).toBe('Not in a folder')
  })

  it('sorts newest first', () => {
    const rows = flattenFiles([
      { id: 1, kind: 'folder', title: 'x', files: [
        f(1, 'old.pdf', '2025-06-01'),
        f(2, 'new.pdf', '2026-08-01'),
        f(3, 'mid.pdf', '2026-01-01'),
      ] },
    ])
    expect(rows.map((r) => r.original_name)).toEqual(['new.pdf', 'mid.pdf', 'old.pdf'])
  })

  it('carries the source bucket so a row can navigate to it', () => {
    const rows = flattenFiles([
      { id: 7, kind: 'folder', title: 'specs', files: [f(1, 'a.pdf', '2026-01-01')] },
    ])
    expect(rows[0].bucketId).toBe(7)
    expect(rows[0].bucketKind).toBe('folder')
  })

  it('keeps the original file fields intact', () => {
    const rows = flattenFiles([
      { id: 1, kind: 'folder', title: 'x', files: [{ id: 5, original_name: 'a.pdf', size_bytes: 42 }] },
    ])
    expect(rows[0].size_bytes).toBe(42)
    expect(rows[0].original_name).toBe('a.pdf')
  })

  it('survives buckets with no files array and an empty input', () => {
    expect(flattenFiles([{ id: 1, kind: 'folder', title: 'x' }])).toEqual([])
    expect(flattenFiles([])).toEqual([])
    expect(flattenFiles(null)).toEqual([])
  })

  it('does not mutate the buckets it was given', () => {
    const buckets = [{ id: 1, kind: 'folder', title: 'x', files: [f(1, 'a.pdf', '2026-01-01')] }]
    flattenFiles(buckets)
    expect(buckets[0].files[0]).not.toHaveProperty('location')
  })
})
