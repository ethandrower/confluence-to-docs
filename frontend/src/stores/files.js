import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const api = (p) => `/api${p}`

export const useFilesStore = defineStore('files', () => {
  const buckets = ref([])
  const loading = ref(false)
  const activeBucketId = ref(null)

  const requests = computed(() => buckets.value.filter((b) => b.kind === 'request'))
  const generalBucket = computed(() => buckets.value.find((b) => b.kind === 'general') || null)
  const activeBucket = computed(() => buckets.value.find((b) => b.id === activeBucketId.value) || null)

  async function load() {
    loading.value = true
    try {
      const r = await fetch(api('/files/buckets/'), { credentials: 'include' })
      buckets.value = r.ok ? (await r.json()).buckets : []
      // Keep selection valid: prefer the current one, else first request, else general.
      if (!buckets.value.some((b) => b.id === activeBucketId.value)) {
        activeBucketId.value = requests.value[0]?.id ?? generalBucket.value?.id ?? null
      }
    } finally {
      loading.value = false
    }
  }

  function select(id) {
    activeBucketId.value = id
  }

  async function upload(file, bucketId, onProgress) {
    const init = await fetch(api('/files/upload-init'), {
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

    const done = await fetch(api('/files/upload-complete'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id }),
    })
    if (!done.ok) throw new Error((await done.json().catch(() => ({}))).error || 'Could not finalize upload')
    await load()
  }

  async function rename(id, name) {
    await fetch(api(`/files/${id}`), {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    await load()
  }

  async function remove(id) {
    await fetch(api(`/files/${id}`), { method: 'DELETE', credentials: 'include' })
    await load()
  }

  const downloadUrl = (id) => api(`/files/${id}/download`)

  return {
    buckets, loading, activeBucketId, requests, generalBucket, activeBucket,
    load, select, upload, rename, remove, downloadUrl,
  }
})
