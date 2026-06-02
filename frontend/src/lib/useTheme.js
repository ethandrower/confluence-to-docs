import { ref } from 'vue'

// Light is the default. Dark is opt-in and only persists when the user
// explicitly chooses it — we intentionally do NOT follow the OS preference,
// so a first-time auditor always lands on the light, print-friendly theme.
const STORAGE_KEY = 'citemed-theme'
const theme = ref('light')

function applyClass(value) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', value === 'dark')
}

function initTheme() {
  let stored = null
  try {
    stored = localStorage.getItem(STORAGE_KEY)
  } catch {
    /* storage unavailable — fall back to light */
  }
  theme.value = stored === 'dark' ? 'dark' : 'light'
  applyClass(theme.value)
}

function setTheme(value) {
  theme.value = value === 'dark' ? 'dark' : 'light'
  try {
    localStorage.setItem(STORAGE_KEY, theme.value)
  } catch {
    /* ignore */
  }
  applyClass(theme.value)
}

function toggleTheme() {
  setTheme(theme.value === 'dark' ? 'light' : 'dark')
}

export function useTheme() {
  return { theme, initTheme, setTheme, toggleTheme }
}
