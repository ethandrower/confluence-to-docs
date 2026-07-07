<template>
  <div>
    <div class="chips" :class="{ 'chips--focus': focused }" @click="focusInput">
      <span v-for="(email, i) in modelValue" :key="email" class="chip">
        <span class="chip-text">{{ email }}</span>
        <button
          type="button"
          class="chip-x"
          :aria-label="`Remove ${email}`"
          @click.stop="removeAt(i)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
        </button>
      </span>
      <input
        ref="inputEl"
        v-model="draft"
        type="text"
        class="chips-input"
        :placeholder="modelValue.length ? '' : placeholder"
        :aria-label="ariaLabel"
        autocomplete="off"
        @keydown="onKeydown"
        @paste="onPaste"
        @focus="focused = true"
        @blur="onBlur"
      />
    </div>
    <p v-if="error" class="chips-error" role="alert">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'name@company.com' },
  ariaLabel: { type: String, default: 'Email addresses' },
})
const emit = defineEmits(['update:modelValue'])

const draft = ref('')
const focused = ref(false)
const error = ref('')
const inputEl = ref(null)

// Deliberately loose — the backend (_clean_ccs) is the authority and re-validates.
// This is just enough to reject obvious non-emails before they become a chip.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function addEmails(raw) {
  const parts = raw.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean)
  const next = [...props.modelValue]
  let bad = ''
  for (const p of parts) {
    if (!EMAIL_RE.test(p)) { bad = p; continue }
    if (!next.some((e) => e.toLowerCase() === p.toLowerCase())) next.push(p)
  }
  if (next.length !== props.modelValue.length) emit('update:modelValue', next)
  return bad
}

function commit() {
  const raw = draft.value
  if (!raw.trim()) { draft.value = ''; error.value = ''; return }
  const bad = addEmails(raw)
  draft.value = bad // keep the unparseable remainder in the field for editing
  error.value = bad ? `"${bad}" doesn't look like an email` : ''
}

function onKeydown(e) {
  if (e.key === ',' || e.key === ';' || e.key === 'Enter') {
    e.preventDefault()
    commit()
  } else if (e.key === 'Backspace' && !draft.value && props.modelValue.length) {
    removeAt(props.modelValue.length - 1)
  }
}

function onPaste(e) {
  e.preventDefault()
  const text = (e.clipboardData || window.clipboardData).getData('text')
  const bad = addEmails(text)
  draft.value = bad
  error.value = bad ? `"${bad}" doesn't look like an email` : ''
}

function onBlur() {
  focused.value = false
  commit()
}

function removeAt(i) {
  emit('update:modelValue', props.modelValue.filter((_, idx) => idx !== i))
  error.value = ''
}

function focusInput() {
  inputEl.value?.focus()
}
</script>

<style scoped>
.chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 38px;
  padding: 5px 8px;
  border: 1px solid var(--input, var(--border));
  border-radius: var(--radius-md);
  background: var(--background);
  cursor: text;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.chips--focus {
  border-color: var(--brand-accent, var(--primary));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-accent, var(--primary)) 15%, transparent);
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 3px 4px 3px 9px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--brand-accent, var(--primary)) 12%, var(--secondary));
  color: var(--foreground);
  font-size: 0.8rem;
  font-weight: 500;
  line-height: 1.4;
}
.chip-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-x {
  flex-shrink: 0;
  display: inline-grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border: none;
  border-radius: 50%;
  background: none;
  color: var(--muted-foreground);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.chip-x svg { width: 11px; height: 11px; }
.chip-x:hover { background: color-mix(in srgb, var(--foreground) 12%, transparent); color: var(--foreground); }
.chips-input {
  flex: 1 1 90px;
  min-width: 90px;
  border: none;
  outline: none;
  background: none;
  color: var(--foreground);
  font: inherit;
  font-size: 0.875rem;
  padding: 3px 2px;
}
.chips-input::placeholder { color: var(--muted-foreground); opacity: 0.7; }
.chips-error { font-size: 0.75rem; color: var(--destructive); margin: 0.3rem 0 0; }
</style>
