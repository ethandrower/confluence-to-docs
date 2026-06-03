import { ref } from 'vue'

// Tracks the pages the current user has recently opened (client-side only,
// persisted to localStorage). Used by the home page until we sync real
// Confluence "last modified" dates for a true "recently updated" feed.
const STORAGE_KEY = 'citemed-recent'
const MAX = 8
const recent = ref([])

function load() {
  try {
    recent.value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    recent.value = []
  }
  return recent.value
}

function record(page) {
  if (!page?.slug || !page?.title) return
  const list = load().filter(p => p.slug !== page.slug)
  list.unshift({ slug: page.slug, title: page.title, ts: Date.now() })
  recent.value = list.slice(0, MAX)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(recent.value))
  } catch {
    /* ignore */
  }
}

export function useRecentlyViewed() {
  return { recent, load, record }
}
