import { describe, it, expect } from 'vitest'
import {
  isJunk, dirOf, filesFromDrop, filesFromInput, partitionByExtension, pathsIn,
} from './folderDrop.js'

// ── Fakes for the webkit entry API, which jsdom/node do not provide ────────

/** A directory reader that hands back at most `batchSize` entries per call and
 *  signals completion with an empty array — exactly like the real one. */
function fakeReader(entries, batchSize = 100) {
  let i = 0
  return {
    readEntries(onOk) {
      const batch = entries.slice(i, i + batchSize)
      i += batch.length
      onOk(batch)
    },
  }
}

const fakeFile = (name) => ({ name, __file: true })

function fileEntry(name) {
  return {
    name,
    isFile: true,
    isDirectory: false,
    file: (onOk) => onOk(fakeFile(name)),
  }
}

function dirEntry(name, children, batchSize = 100) {
  return {
    name,
    isFile: false,
    isDirectory: true,
    createReader: () => fakeReader(children, batchSize),
  }
}

const dropOf = (entries) => ({
  items: entries.map((e) => ({ kind: 'file', webkitGetAsEntry: () => e })),
  files: [],
})

describe('isJunk', () => {
  it('rejects filesystem bookkeeping and dotfiles', () => {
    expect(isJunk('.DS_Store')).toBe(true)
    expect(isJunk('Thumbs.db')).toBe(true)
    expect(isJunk('desktop.ini')).toBe(true)
    expect(isJunk('.env')).toBe(true) // dotfiles as a class
    expect(isJunk('')).toBe(true)
  })

  it('keeps real documents', () => {
    expect(isJunk('report.pdf')).toBe(false)
    expect(isJunk('Q1 summary.csv')).toBe(false)
  })
})

describe('dirOf', () => {
  it('drops the filename and keeps the directory chain', () => {
    expect(dirOf('tree/2024/q1/report.pdf')).toBe('tree/2024/q1')
    expect(dirOf('report.pdf')).toBe('')
    expect(dirOf('')).toBe('')
  })
})

describe('filesFromDrop', () => {
  it('walks a nested tree into relative paths', async () => {
    const tree = dirEntry('tree', [
      fileEntry('overview.pdf'),
      dirEntry('2024', [dirEntry('q1', [fileEntry('report.pdf')])]),
    ])
    const out = await filesFromDrop(dropOf([tree]))
    expect(out.map((o) => `${o.path}/${o.file.name}`).sort()).toEqual([
      'tree/2024/q1/report.pdf',
      'tree/overview.pdf',
    ])
  })

  it('reads past the 100-entry readEntries batch limit', async () => {
    // The real readEntries returns at most 100 per call. Calling it once —
    // the obvious implementation — silently loses everything after the 100th.
    const many = Array.from({ length: 250 }, (_, i) => fileEntry(`f${i}.pdf`))
    const out = await filesFromDrop(dropOf([dirEntry('big', many)]))
    expect(out).toHaveLength(250)
    expect(out.every((o) => o.path === 'big')).toBe(true)
  })

  it('skips junk anywhere in the tree, including whole junk directories', async () => {
    const tree = dirEntry('tree', [
      fileEntry('keep.pdf'),
      fileEntry('.DS_Store'),
      dirEntry('.git', [fileEntry('config.txt')]),
    ])
    const out = await filesFromDrop(dropOf([tree]))
    expect(out.map((o) => o.file.name)).toEqual(['keep.pdf'])
  })

  it('handles loose files dropped alongside folders', async () => {
    const out = await filesFromDrop(dropOf([
      fileEntry('loose.pdf'),
      dirEntry('docs', [fileEntry('inner.pdf')]),
    ]))
    expect(out.map((o) => [o.path, o.file.name])).toEqual([
      ['', 'loose.pdf'],
      ['docs', 'inner.pdf'],
    ])
  })

  it('falls back to the flat file list when the entries API is absent', async () => {
    const out = await filesFromDrop({ items: [], files: [fakeFile('a.pdf'), fakeFile('.DS_Store')] })
    expect(out).toEqual([{ file: { name: 'a.pdf', __file: true }, path: '' }])
  })
})

describe('filesFromInput', () => {
  it('reads webkitRelativePath from a directory picker', () => {
    const out = filesFromInput([
      { name: 'report.pdf', webkitRelativePath: 'tree/2024/report.pdf' },
      { name: 'loose.pdf', webkitRelativePath: '' },
    ])
    expect(out).toEqual([
      { file: out[0].file, path: 'tree/2024' },
      { file: out[1].file, path: '' },
    ])
  })

  it('filters junk the picker included', () => {
    const out = filesFromInput([
      { name: '.DS_Store', webkitRelativePath: 'tree/.DS_Store' },
      { name: 'ok.pdf', webkitRelativePath: 'tree/ok.pdf' },
    ])
    expect(out.map((o) => o.file.name)).toEqual(['ok.pdf'])
  })
})

describe('partitionByExtension', () => {
  const allowed = new Set(['pdf', 'csv', 'txt'])

  it('separates uploadable from unsupported', () => {
    const items = [
      { file: { name: 'a.pdf' }, path: '' },
      { file: { name: 'b.exe' }, path: '' },
      { file: { name: 'c.CSV' }, path: '' }, // case-insensitive
      { file: { name: 'noext' }, path: '' },
    ]
    const { ok, skipped } = partitionByExtension(items, allowed)
    expect(ok.map((o) => o.file.name)).toEqual(['a.pdf', 'c.CSV'])
    expect(skipped).toEqual(['b.exe', 'noext'])
  })
})

describe('pathsIn', () => {
  it('returns distinct paths shallowest first, so parents precede children', () => {
    const items = [
      { path: 'a/b/c' }, { path: 'a' }, { path: 'a/b' }, { path: 'a' }, { path: '' },
    ].map((x) => ({ ...x, file: { name: 'f.pdf' } }))
    expect(pathsIn(items)).toEqual(['a', 'a/b', 'a/b/c'])
  })

  it('omits the empty path — that is the drop root, not a folder', () => {
    expect(pathsIn([{ path: '', file: { name: 'f.pdf' } }])).toEqual([])
  })
})
