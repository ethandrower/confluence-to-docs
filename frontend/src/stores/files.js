import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiFetch } from '../lib/http.js'

const api = (p) => `/api${p}`

export const useFilesStore = defineStore('files', () => {
  const buckets = ref([])
  const loading = ref(false)
  const activeBucketId = ref(null)

  const requests = computed(() => buckets.value.filter((b) => b.kind === 'request'))

  // Only a small share of requests genuinely gate anything. Splitting them
  // keeps the customer's "you must do this" list short enough to be believed:
  // a request stops being urgent once it's complete, so it drops out here too
  // rather than sitting at the top as permanent noise.
  const requiredRequests = computed(() =>
    requests.value.filter((b) => b.required && b.status !== 'complete')
  )
  const otherRequests = computed(() =>
    requests.value.filter((b) => !(b.required && b.status !== 'complete'))
  )
  const generalBucket = computed(() => buckets.value.find((b) => b.kind === 'general') || null)
  const activeBucket = computed(() => buckets.value.find((b) => b.id === activeBucketId.value) || null)
  const folders = computed(() => buckets.value.filter((b) => b.kind === 'folder'))

  // The API returns a flat list with a `parent` id; the tree is derived here so
  // one fetch covers any shape and a re-parent doesn't invalidate a nested
  // payload. Sorted by title because creation order means nothing to a reader.
  const folderTree = computed(() => {
    const byId = new Map(folders.value.map((f) => [f.id, { ...f, children: [] }]))
    const roots = []
    for (const node of byId.values()) {
      const parent = node.parent != null ? byId.get(node.parent) : null
      ;(parent ? parent.children : roots).push(node)
    }
    const sort = (list) => {
      list.sort((a, b) => a.title.localeCompare(b.title))
      list.forEach((n) => sort(n.children))
      return list
    }
    return sort(roots)
  })

  /** Breadcrumb path to a folder, root first. Empty for a non-folder. */
  function pathTo(id) {
    const byId = new Map(buckets.value.map((b) => [b.id, b]))
    const path = []
    let node = byId.get(id)
    const seen = new Set()
    while (node && node.kind === 'folder' && !seen.has(node.id)) {
      seen.add(node.id)
      path.unshift(node)
      node = node.parent != null ? byId.get(node.parent) : null
    }
    return path
  }

  /** Files in a folder, and — when `deep` — everything in its subfolders too.
   *  The count a customer cares about at a collapsed node is the deep one. */
  function fileCount(id, deep = false) {
    const b = buckets.value.find((x) => x.id === id)
    let n = b ? (b.files || []).length : 0
    if (deep) {
      for (const child of buckets.value.filter((x) => x.parent === id)) {
        n += fileCount(child.id, true)
      }
    }
    return n
  }

  async function load() {
    loading.value = true
    try {
      const r = await apiFetch(api('/files/buckets/'), { credentials: 'include' })
      buckets.value = r.ok ? (await r.json()).buckets : []
      // Keep the selection valid, and when there isn't one, land somewhere
      // worth landing: a request that actually blocks them, else their own
      // files. Never an optional request — opening on "Old IFU versions (if
      // handy)" makes a nice-to-have look like the task of the day.
      if (!buckets.value.some((b) => b.id === activeBucketId.value)) {
        activeBucketId.value =
          requiredRequests.value[0]?.id ?? generalBucket.value?.id ?? null
      }
    } finally {
      loading.value = false
    }
  }

  function select(id) {
    activeBucketId.value = id
  }

  async function upload(file, bucketId, onProgress) {
    const init = await apiFetch(api('/files/upload-init'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: file.name, size: file.size, mime: file.type, bucket_id: bucketId || null,
      }),
    })
    if (!init.ok) throw new Error((await init.json().catch(() => ({}))).error || 'Upload failed')
    const { file_id, upload_url } = await init.json()

    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('PUT', upload_url)
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
      xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error('Upload to storage failed')))
      xhr.onerror = () => reject(new Error('Network error during upload'))
      xhr.send(file)
    })

    const done = await apiFetch(api('/files/upload-complete'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id }),
    })
    if (!done.ok) throw new Error((await done.json().catch(() => ({}))).error || 'Could not finalize upload')
    await load()
  }

  async function rename(id, name) {
    await apiFetch(api(`/files/${id}`), {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    await load()
  }

  async function remove(id) {
    await apiFetch(api(`/files/${id}`), { method: 'DELETE', credentials: 'include' })
    await load()
  }

  const downloadUrl = (id) => api(`/files/${id}/download`)

  // ── Folders ───────────────────────────────────────────────────────────
  // Each returns the server's error message rather than throwing: every one
  // of these can fail for a reason the customer needs to read ("a folder with
  // that name is already here", "move the files out first").
  async function json(path, opts) {
    const r = await apiFetch(api(path), { credentials: 'include', ...opts })
    const body = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(body.error || 'Something went wrong.')
    return body
  }

  async function createFolder(title, parentId = null) {
    const body = await json('/files/folders/', {
      method: 'POST',
      body: JSON.stringify({ title, parent_id: parentId }),
    })
    await load()
    return body.folder
  }

  async function renameFolder(id, title) {
    await json(`/files/folders/${id}/`, { method: 'PATCH', body: JSON.stringify({ title }) })
    await load()
  }

  async function moveFolder(id, parentId) {
    await json(`/files/folders/${id}/`, {
      method: 'PATCH', body: JSON.stringify({ parent_id: parentId }),
    })
    await load()
  }

  async function deleteFolder(id) {
    await json(`/files/folders/${id}/`, { method: 'DELETE' })
    if (activeBucketId.value === id) activeBucketId.value = generalBucket.value?.id ?? null
    await load()
  }

  async function moveFiles(fileIds, bucketId) {
    await json('/files/move/', {
      method: 'POST', body: JSON.stringify({ file_ids: fileIds, bucket_id: bucketId }),
    })
    await load()
  }

  return {
    buckets, loading, activeBucketId, requests, generalBucket, activeBucket,
    requiredRequests, otherRequests,
    folders, folderTree, pathTo, fileCount,
    load, select, upload, rename, remove, downloadUrl,
    createFolder, renameFolder, moveFolder, deleteFolder, moveFiles,
  }
})
