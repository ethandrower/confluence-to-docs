import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiFetch } from '../lib/http.js'
import { buildFolderTree, folderPath, flattenFiles } from '../lib/folders.js'
import { RateLimited, runPool, withSlot, withRetry, UPLOAD_CONCURRENCY } from '../lib/uploadQueue.js'

const api = (p) => `/api${p}`

/**
 * Sentinel for the "All files" home, which is a view rather than a bucket.
 *
 * A string can never collide with a Bucket id (always a number), so every
 * `b.id === activeBucketId` test in the tree simply misses it and no folder
 * lights up while it is selected — which is what we want, since it is not one.
 */
export const ALL_FILES_ID = '__all__'

export const useFilesStore = defineStore('files', () => {
  const buckets = ref([])
  const loading = ref(false)
  // Server-authoritative; the uploader uses it only to report skips early.
  const allowedExt = ref(new Set())
  const activeBucketId = ref(ALL_FILES_ID)

  const requests = computed(() => buckets.value.filter((b) => b.kind === 'request'))

  // Only a small share of requests genuinely gate anything. Splitting them
  // keeps the customer's "you must do this" list short enough to be believed:
  // a request stops being urgent once it's complete, so it drops out here too
  // rather than sitting at the top as permanent noise.
  const requiredRequests = computed(() =>
    requests.value.filter((b) => b.required && b.status !== 'complete')
  )

  // Split on `required` alone, NOT on "everything that isn't currently
  // blocking". A mandatory document that has been satisfied is still a
  // mandatory document, and sweeping it in with the optional ones would file
  // "Signed Declaration of Conformity" under a heading that says the customer
  // never had to send it.
  const optionalRequests = computed(() => requests.value.filter((b) => !b.required))
  const doneRequests = computed(() =>
    requests.value.filter((b) => b.required && b.status === 'complete')
  )
  const generalBucket = computed(() => buckets.value.find((b) => b.kind === 'general') || null)
  const activeBucket = computed(() => buckets.value.find((b) => b.id === activeBucketId.value) || null)
  const folders = computed(() => buckets.value.filter((b) => b.kind === 'folder'))

  // Derived from the flat list via the shared helper, so the customer's tree
  // and the agent's client view are literally the same construction.
  const folderTree = computed(() => buildFolderTree(buckets.value))

  /** Breadcrumb path to a folder, root first. Empty for a non-folder. */
  const pathTo = (id) => folderPath(buckets.value, id)

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

  /** Backing list for the "All files" home. See flattenFiles for what it
   *  includes and why. */
  const allFiles = computed(() => flattenFiles(buckets.value))

  const totalFileCount = computed(() => allFiles.value.length)

  async function load() {
    loading.value = true
    try {
      const r = await apiFetch(api('/files/buckets/'), { credentials: 'include' })
      if (r.ok) {
        const body = await r.json()
        buckets.value = body.buckets
        if (body.allowed_ext) allowedExt.value = new Set(body.allowed_ext)
      } else {
        buckets.value = []
      }
      // Land on "All files", never on a request.
      //
      // This used to open on requiredRequests[0], which meant the portal
      // greeted people by selecting the first thing that blocked them and
      // scoping the drop zone to it — so an ordinary upload silently became
      // "answer this request", and the answer to a different question than the
      // one they came to do. Uploading is the common case; requests stay
      // listed in the sidebar and are chosen deliberately.
      //
      // "All files" is a view rather than a bucket, so it is never in this
      // list — test for it explicitly or every refresh knocks the customer off
      // whatever they were looking at.
      const onAllFiles = activeBucketId.value === ALL_FILES_ID
      if (!onAllFiles && !buckets.value.some((b) => b.id === activeBucketId.value)) {
        activeBucketId.value = ALL_FILES_ID
      }
    } finally {
      loading.value = false
    }
  }

  function select(id) {
    activeBucketId.value = id
  }

  /**
   * PUT a blob straight to storage, reporting progress.
   *
   * Resolves with the ETag response header, which is meaningless for a whole
   * file but is what multipart completion is assembled from — so the plumbing
   * is here once rather than duplicated later.
   */
  function putToStorage(url, body, contentType, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('PUT', url)
      if (contentType) xhr.setRequestHeader('Content-Type', contentType)
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded, e.total)
      xhr.onload = () =>
        xhr.status >= 200 && xhr.status < 300
          ? resolve(xhr.getResponseHeader('ETag'))
          : reject(new Error(`Upload to storage failed (${xhr.status})`))
      xhr.onerror = () => reject(new Error('Network error during upload'))
      xhr.ontimeout = () => reject(new Error('Upload timed out'))
      xhr.send(body)
    })
  }

  async function uploadInit(file, bucketId) {
    const r = await apiFetch(api('/files/upload-init'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: file.name, size: file.size, mime: file.type, bucket_id: bucketId || null,
      }),
    })
    // 429 is backpressure, not failure: the caller pauses the whole queue and
    // comes back, rather than burning this file as an error.
    if (r.status === 429) {
      const body = await r.json().catch(() => ({}))
      throw new RateLimited((body.retry_after || 60) * 1000)
    }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'Upload failed')
    return r.json()
  }

  /**
   * Turn relative folder paths into bucket ids, creating what's missing.
   *
   * One call for the whole batch: doing it per file would race, since two
   * files in the same new subfolder would each try to create it.
   */
  async function ensurePaths(paths, rootId) {
    if (!paths.length) return { '': rootId || null }
    const r = await apiFetch(api('/files/folders/ensure-path'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root_id: rootId || null, paths }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'Could not create folders')
    return (await r.json()).folders
  }

  async function fetchPartUrls(fileId, numbers) {
    const r = await apiFetch(api('/files/upload-parts'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId, part_numbers: numbers }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'Could not presign parts')
    return (await r.json()).urls
  }

  async function abortUpload(fileId) {
    // Best-effort: the nightly purge is the real backstop. Worth attempting
    // because until an aborted multipart's parts are discarded they keep
    // being billed and never appear in a listing.
    try {
      await apiFetch(api('/files/upload-abort'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: fileId }),
      })
    } catch { /* nothing useful to do */ }
  }

  // Presign in batches rather than all at once: a 5 GB file is hundreds of
  // parts whose URLs would otherwise all expire together.
  const PART_URL_BATCH = 25

  async function uploadInParts(file, init, onProgress) {
    const { file_id, part_size, part_count } = init
    const loaded = new Array(part_count).fill(0)
    const report = () =>
      onProgress?.(loaded.reduce((a, b) => a + b, 0) / (file.size || 1))

    const done = []
    for (let first = 1; first <= part_count; first += PART_URL_BATCH) {
      const numbers = []
      for (let n = first; n < first + PART_URL_BATCH && n <= part_count; n++) numbers.push(n)
      const urls = await fetchPartUrls(file_id, numbers)

      const results = await runPool(numbers, (n) => withRetry(async () => {
        const blob = file.slice((n - 1) * part_size, n * part_size)
        const etag = await withSlot(() => putToStorage(urls[String(n)], blob, null, (l) => {
          loaded[n - 1] = l
          report()
        }))
        if (!etag) {
          // The PUT succeeded but the ETag header was not readable. Almost
          // always a bucket CORS problem: multipart completion is assembled
          // from ETags, so the store must expose that header to scripts.
          throw new Error('Storage did not return an ETag (check CORS ExposeHeaders)')
        }
        // A retried part replaces the previous one, so recording it here is safe.
        return { PartNumber: n, ETag: etag }
      }), UPLOAD_CONCURRENCY)

      const failed = results.find((r) => !r.ok)
      if (failed) throw failed.error
      done.push(...results.map((r) => r.value))
    }

    const complete = await apiFetch(api('/files/upload-complete'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id, parts: done }),
    })
    if (!complete.ok) {
      throw new Error((await complete.json().catch(() => ({}))).error || 'Could not finalize upload')
    }
    return file_id
  }

  /**
   * Upload one file. Deliberately does NOT refresh the folder list — a caller
   * uploading 200 files would otherwise refetch the entire tree 200 times.
   * Callers reload once when their batch drains.
   *
   * Large files go up in parts. That is not really about the 5 GB single-PUT
   * ceiling: it is that a whole-object PUT has nothing to resume from, so one
   * dropped connection at 90% costs the entire transfer.
   */
  async function upload(file, bucketId, onProgress) {
    const init = await uploadInit(file, bucketId)

    if (init.multipart) {
      try {
        return await uploadInParts(file, init, onProgress)
      } catch (e) {
        await abortUpload(init.file_id)
        throw e
      }
    }

    await withRetry(() => withSlot(() => putToStorage(
      init.upload_url, file, file.type || 'application/octet-stream',
      (loaded, total) => onProgress?.(loaded / total),
    )))

    const done = await apiFetch(api('/files/upload-complete'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: init.file_id }),
    })
    if (!done.ok) throw new Error((await done.json().catch(() => ({}))).error || 'Could not finalize upload')
    return init.file_id
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
    requiredRequests, optionalRequests, doneRequests,
    folders, folderTree, pathTo, fileCount, allFiles, totalFileCount,
    load, select, upload, rename, remove, downloadUrl,
    allowedExt, ensurePaths,
    createFolder, renameFolder, moveFolder, deleteFolder, moveFiles,
  }
})
