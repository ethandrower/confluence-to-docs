import { describe, it, expect } from 'vitest'
import { buildFolderTree, originOf, folderPath } from './folders.js'

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
