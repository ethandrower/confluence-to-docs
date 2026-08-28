import { describe, it, expect } from 'vitest'
import { flattenFiles } from './folders.js'

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
