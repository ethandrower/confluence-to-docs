<template>
  <section class="panel">
    <div class="panel-bar">
      <span class="panel-hint">
        Shown in the portal to signed-in customers. This does <strong>not</strong>
        replace emailing the account contact — EC-SOP-07 §5.2 names email as the
        channel, and the banner is offline whenever the portal is.
      </span>
      <button class="btn-primary" @click="openForm()">+ Raise a notice</button>
    </div>

    <p v-if="error" class="admin-error">{{ error }}</p>

    <p v-if="loading" class="empty">Loading…</p>

    <p v-else-if="!notices.length" class="empty">
      No notices have been raised.
    </p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Level</th><th>Message</th><th>Applies to</th><th>Window</th>
            <th class="ta-c">Status</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="notice in notices" :key="notice.id" :class="notice.retired_at && 'is-retired'">
            <td><span class="lvl" :class="`lvl--${notice.level}`">{{ notice.level }}</span></td>
            <td class="msg">{{ notice.message }}</td>
            <td>{{ scopeLabel(notice) }}</td>
            <td class="when">
              {{ shortDate(notice.starts_at) }}
              <template v-if="notice.ends_at"> → {{ shortDate(notice.ends_at) }}</template>
              <span v-else class="open-ended">→ open-ended</span>
            </td>
            <td class="ta-c">
              <span class="status" :class="statusOf(notice).tone">{{ statusOf(notice).label }}</span>
              <!-- Age of a live notice, flagged once it has stood longer than
                   its level warrants. This is the only prompt an agent gets to
                   retire something: nothing expires a notice automatically. -->
              <span
                v-if="staleness(notice)"
                class="age"
                :class="staleness(notice).isStale && 'age--stale'"
                :title="staleness(notice).isStale
                  ? `Live for ${staleness(notice).label}. Retire it if this is resolved — customers still see it.`
                  : `Live for ${staleness(notice).label}`"
              >{{ staleness(notice).label }}</span>
            </td>
            <td class="ta-r">
              <div class="row-actions">
                <button class="icon-btn" :aria-label="`Edit notice ${notice.id}`" title="Edit" @click="openForm(notice)">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" /></svg>
                </button>
                <!-- Retire, not delete: the customer-visible history depends on
                     the row surviving. -->
                <button
                  v-if="!notice.retired_at"
                  class="icon-btn icon-btn--danger"
                  :aria-label="`Retire notice ${notice.id}`"
                  title="Retire (keeps it in history)"
                  @click="retire(notice)"
                >
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Form -->
    <div v-if="showForm" class="modal-backdrop" @click.self="closeForm">
      <div class="modal" role="dialog" aria-modal="true" :aria-label="editing ? 'Edit notice' : 'Raise a notice'">
        <h2 class="modal-title">{{ editing ? 'Edit notice' : 'Raise a notice' }}</h2>

        <p v-if="formError" class="admin-error">{{ formError }}</p>

        <label class="field">
          <span class="label">Level</span>
          <select v-model="form.level" class="input">
            <option value="info">Info — general information</option>
            <option value="warning">Warning — degraded or delayed</option>
            <option value="critical">Critical — cannot be dismissed</option>
          </select>
        </label>

        <label class="field">
          <span class="label">Message</span>
          <textarea
            v-model="form.message"
            class="input"
            rows="3"
            placeholder="What is happening, what it affects, and what to do instead."
          ></textarea>
        </label>

        <div class="pair">
          <label class="field">
            <span class="label">Link (optional)</span>
            <input v-model="form.link_url" class="input" type="url" placeholder="https://…" />
          </label>
          <label class="field">
            <span class="label">Link text</span>
            <input v-model="form.link_label" class="input" placeholder="More detail" />
          </label>
        </div>

        <div class="pair">
          <label class="field">
            <span class="label">Starts</span>
            <input v-model="form.starts_at" class="input" type="datetime-local" />
          </label>
          <label class="field">
            <span class="label">Ends (blank = open-ended)</span>
            <input v-model="form.ends_at" class="input" type="datetime-local" />
          </label>
        </div>

        <fieldset class="field">
          <legend class="label">Applies to</legend>
          <label class="radio">
            <input v-model="form.scope" type="radio" value="all" />
            Everyone
          </label>
          <label class="radio">
            <input v-model="form.scope" type="radio" value="some" />
            Specific companies
          </label>
          <div v-if="form.scope === 'some'" class="company-list">
            <label v-for="company in admin.companies" :key="company.id" class="check">
              <input v-model="form.company_ids" type="checkbox" :value="company.id" />
              {{ company.name }}
            </label>
          </div>
        </fieldset>

        <div class="modal-actions">
          <button class="btn-ghost" @click="closeForm">Cancel</button>
          <button class="btn-primary" :disabled="saving" @click="save">
            {{ saving ? 'Saving…' : (editing ? 'Save' : 'Raise notice') }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch } from '../../lib/http.js'
import { noticeStaleness } from '@/lib/notices.js'
import { useAdminStore } from '@/stores/admin.js'

const admin = useAdminStore()

const staleness = (notice) => noticeStaleness(notice)

const notices = ref([])
const loading = ref(true)
const error = ref('')

const showForm = ref(false)
const editing = ref(null)
const saving = ref(false)
const formError = ref('')
const form = ref(blankForm())

function blankForm() {
  return {
    level: 'info', message: '', link_url: '', link_label: '',
    starts_at: '', ends_at: '', scope: 'all', company_ids: [],
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await apiFetch('/api/admin/notices/')
    if (!response.ok) throw new Error('load failed')
    notices.value = (await response.json()).notices || []
  } catch {
    error.value = 'Could not load notices.'
  } finally {
    loading.value = false
  }
}

function openForm(notice = null) {
  editing.value = notice
  formError.value = ''
  form.value = notice
    ? {
        level: notice.level,
        message: notice.message,
        link_url: notice.link_url || '',
        link_label: notice.link_label || '',
        starts_at: toLocalInput(notice.starts_at),
        ends_at: toLocalInput(notice.ends_at),
        scope: notice.company_ids?.length ? 'some' : 'all',
        company_ids: [...(notice.company_ids || [])],
      }
    : blankForm()
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  editing.value = null
}

async function save() {
  if (!form.value.message.trim()) {
    formError.value = 'A message is required.'
    return
  }
  saving.value = true
  formError.value = ''

  const payload = {
    level: form.value.level,
    message: form.value.message,
    link_url: form.value.link_url,
    link_label: form.value.link_label,
    // Empty list means "everyone" server-side, which is what 'all' should send.
    company_ids: form.value.scope === 'some' ? form.value.company_ids : [],
  }
  // Only send window keys the agent actually filled in — the API leaves absent
  // keys alone, so a blank field must not clear an existing window by accident.
  if (form.value.starts_at) payload.starts_at = new Date(form.value.starts_at).toISOString()
  payload.ends_at = form.value.ends_at ? new Date(form.value.ends_at).toISOString() : null

  try {
    const response = await apiFetch(
      editing.value ? `/api/admin/notices/${editing.value.id}/` : '/api/admin/notices/',
      {
        method: editing.value ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      },
    )
    if (!response.ok) {
      formError.value = (await response.json().catch(() => ({}))).error || 'Could not save.'
      return
    }
    closeForm()
    await load()
  } catch {
    formError.value = 'Could not save.'
  } finally {
    saving.value = false
  }
}

async function retire(notice) {
  if (!confirm('Retire this notice? It stops showing, but stays in the customer-visible history.')) return
  const response = await apiFetch(`/api/admin/notices/${notice.id}/`, { method: 'DELETE' })
  if (response.ok) await load()
  else error.value = 'Could not retire that notice.'
}

function statusOf(notice) {
  if (notice.retired_at) return { label: 'Retired', tone: 'status--muted' }
  const now = new Date()
  if (new Date(notice.starts_at) > now) return { label: 'Scheduled', tone: 'status--pending' }
  if (notice.ends_at && new Date(notice.ends_at) <= now) return { label: 'Expired', tone: 'status--muted' }
  return { label: 'Live', tone: 'status--live' }
}

function scopeLabel(notice) {
  const ids = notice.company_ids || []
  if (!ids.length) return 'Everyone'
  const names = ids
    .map((id) => admin.companies.find((c) => c.id === id)?.name)
    .filter(Boolean)
  // Fall back to the count if the company list hasn't loaded — better than
  // rendering "undefined" next to an incident notice.
  return names.length ? names.join(', ') : `${ids.length} companies`
}

function shortDate(value) {
  if (!value) return ''
  return new Date(value).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

/** ISO → the `YYYY-MM-DDTHH:mm` local form datetime-local expects. */
function toLocalInput(value) {
  if (!value) return ''
  const date = new Date(value)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(() => {
  load()
  // The scope picker needs company names. fetchAll is the store's only loader
  // (it fetches users and companies together) — the parent view calls it on
  // mount, so this only fires if that hasn't happened yet.
  if (!admin.companies.length) admin.fetchAll()
})
</script>

<style scoped>
/* AdminView's styles are `scoped`, so the shared admin classes don't reach a
   child component. FilesAdmin.vue restates them for the same reason — matching
   that rather than lifting a shared stylesheet, which would touch every admin
   surface and isn't this change's job. */
.panel-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.panel-hint { font-size: 12.5px; color: var(--muted-foreground); max-width: 62ch; }
.admin-error { color: var(--destructive); font-size: 0.9rem; margin: 8px 0; }
.table-wrap { border: 1px solid var(--border); border-radius: var(--radius-lg); overflow-x: auto; background: var(--card); }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
th {
  text-align: left;
  font-family: var(--font-ui);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--muted-foreground);
  padding: 9px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--muted);
  white-space: nowrap;
}
td { padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
tbody tr:last-child td { border-bottom: 0; }
.ta-c { text-align: center; }
.ta-r { text-align: right; }
.row-actions { display: inline-flex; gap: 6px; }
.icon-btn {
  display: inline-flex;
  padding: 5px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--muted-foreground);
  background: var(--card);
}
.icon-btn:hover { color: var(--primary); border-color: var(--primary); background: var(--accent); }
.icon-btn--danger:hover { color: var(--destructive); border-color: var(--destructive); background: color-mix(in srgb, var(--destructive) 12%, transparent); }
.icon-btn svg { width: 15px; height: 15px; }
.icon-btn:focus-visible, .btn-primary:focus-visible, .btn-ghost:focus-visible {
  outline: 2px solid var(--ring, var(--primary));
  outline-offset: 2px;
}
.btn-primary {
  background: var(--primary);
  color: var(--primary-foreground);
  font-family: var(--font-ui);
  font-size: 13.5px;
  font-weight: 550;
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--primary);
  white-space: nowrap;
}
.btn-primary:hover { filter: brightness(0.94); }
.btn-primary:disabled { opacity: 0.6; }
.btn-ghost {
  font-family: var(--font-ui);
  font-size: 13.5px;
  font-weight: 550;
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  color: var(--foreground);
  background: var(--card);
}
.btn-ghost:hover { background: var(--muted); }

.empty {
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--card);
  font-size: 14px;
  color: var(--muted-foreground);
}

.msg {
  max-width: 380px;
  overflow-wrap: anywhere;
}

.when {
  font-size: 12.5px;
  color: var(--muted-foreground);
  white-space: nowrap;
}

.open-ended {
  font-style: italic;
}

.is-retired {
  opacity: 0.62;
}

.lvl {
  font-size: 11px;
  font-weight: 650;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.lvl--info { color: var(--info); background: color-mix(in srgb, var(--info) 12%, var(--card)); }
.lvl--warning { color: var(--warning); background: color-mix(in srgb, var(--warning) 14%, var(--card)); }
.lvl--critical { color: var(--destructive); background: color-mix(in srgb, var(--destructive) 12%, var(--card)); }

.status {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--muted);
  color: var(--muted-foreground);
}

.status--live { color: var(--success); background: color-mix(in srgb, var(--success) 14%, var(--card)); }

.age {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--muted-foreground);
}

.age--stale {
  font-weight: 650;
  color: var(--destructive);
}
.status--pending { color: var(--warning); background: color-mix(in srgb, var(--warning) 14%, var(--card)); }

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: color-mix(in srgb, var(--foreground) 34%, transparent);
}

.modal {
  width: 100%;
  max-width: 520px;
  max-height: 88vh;
  overflow-y: auto;
  padding: 22px;
  border-radius: var(--radius-xl, 12px);
  background: var(--card);
  border: 1px solid var(--border);
}

.modal-title {
  font-size: 17px;
  font-weight: 650;
  margin-bottom: 16px;
}

.field {
  display: block;
  margin-bottom: 14px;
}

.label {
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  margin-bottom: 5px;
  color: var(--muted-foreground);
}

.input {
  width: 100%;
  padding: 8px 10px;
  font-size: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--background);
  color: var(--foreground);
}

.input:focus-visible {
  outline: 2px solid var(--ring, var(--primary));
  outline-offset: 1px;
}

.pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.radio,
.check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  padding: 3px 0;
}

.company-list {
  margin-top: 6px;
  padding: 8px 10px;
  max-height: 160px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}

@media (max-width: 520px) {
  .pair {
    grid-template-columns: 1fr;
  }
}
</style>
