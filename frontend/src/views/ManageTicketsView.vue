<template>
  <AppShell hide-sidebar>
    <template #content>
      <div class="mt">
        <div class="mt-top">
          <RouterLink to="/manage" class="back-link">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" /></svg>
            Manage
          </RouterLink>
          <h1>Support tickets</h1>
          <button class="btn-primary" @click="openNewTicket">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
            New ticket
          </button>
        </div>

        <div class="mt-body" :class="{ 'mt-body--detail': selectedNumber }">
          <section class="mt-list" aria-label="Ticket list">
            <AdminTicketList
              :mode="mode"
              :tickets="list"
              :loading="listLoading"
              :refreshing="refreshing"
              :inbox-total="inboxTotal"
              :truncated="truncated"
              :selected-number="selectedNumber"
              :companies="companies"
              v-model:filter-company="allCompany"
              v-model:filter-status="allStatus"
              @open-inbox="openInbox"
              @open-all="openAll"
              @refresh="refresh"
              @select="selectTicket"
            />
          </section>

          <section class="mt-detail" aria-label="Ticket detail">
            <AdminTicketDetail
              :ticket="selected"
              :loading="detailLoading"
              @back="selectedNumber = null"
              @updated="onDetailUpdated"
              @refreshed="onDetailRefreshed"
            />
          </section>
        </div>
      </div>

      <!-- New ticket modal — Reka Dialog handles focus trap, Escape, focus
           restore and the overlay (replaces the hand-rolled modal). -->
      <Dialog v-model:open="newModal">
        <DialogContent class="mt-dialog">
          <div class="mt-dialog-body">
            <DialogHeader>
              <DialogTitle class="modal-title">New ticket</DialogTitle>
            </DialogHeader>
            <p v-if="newError" class="form-error" role="alert">{{ newError }}</p>
            <label class="field"><span>Client</span>
              <select v-model="newForm.company_id">
                <option value="">Select a client…</option>
                <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </label>
            <label class="field"><span>Customer email</span>
              <input v-model="newForm.customer_email" type="email" placeholder="customer@example.com" />
            </label>
            <label class="field"><span>Subject</span>
              <input v-model="newForm.subject" type="text" placeholder="e.g. Question about report submission" />
            </label>
            <label class="field"><span>Category</span>
              <select v-model="newForm.category">
                <option value="question">Question</option>
                <option value="bug">Bug Report</option>
                <option value="feature">Feature Request</option>
                <option value="docs">Documentation Issue</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label class="field"><span>Message</span>
              <textarea v-model="newForm.body" rows="4" placeholder="Describe the issue or request…"></textarea>
            </label>
            <div class="modal-actions">
              <button class="btn-ghost" @click="newModal = false">Cancel</button>
              <button class="btn-primary" :disabled="newSaving" @click="saveNewTicket">{{ newSaving ? 'Creating…' : 'Create ticket' }}</button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </template>
  </AppShell>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import AdminTicketList from '@/components/support/AdminTicketList.vue'
import AdminTicketDetail from '@/components/support/AdminTicketDetail.vue'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useTicketsStore } from '@/stores/tickets'

const store = useTicketsStore()

const mode = ref('inbox')
const list = ref([])
const listLoading = ref(false)
const inboxTotal = ref(0)
const allCompany = ref('')
const allStatus = ref('')
const refreshing = ref(false)
const truncated = ref(false)

const selectedNumber = ref(null)
const selected = ref(null)
const detailLoading = ref(false)

const companies = ref([])
async function loadCompanies(force = false) {
  if (!force && companies.value.length) return
  const r = await fetch('/api/admin/files/companies/', { credentials: 'include' })
  if (r.ok) companies.value = (await r.json()).companies
}

async function loadInbox() {
  listLoading.value = true
  try {
    const data = await store.adminInbox()
    list.value = data.tickets
    inboxTotal.value = data.awaiting_total
    truncated.value = false
  } finally {
    listLoading.value = false
  }
}
async function loadAll() {
  listLoading.value = true
  try {
    const data = await store.adminList({ company: allCompany.value, status: allStatus.value })
    list.value = data.tickets
    truncated.value = !!data.truncated
  } finally {
    listLoading.value = false
  }
}
function openInbox() {
  mode.value = 'inbox'
  loadInbox()
}
function openAll() {
  mode.value = 'all'
  loadAll()
}

async function selectTicket(number) {
  selectedNumber.value = number
  detailLoading.value = true
  try {
    selected.value = await store.adminTicket(number)
  } finally {
    detailLoading.value = false
  }
}

function onDetailUpdated(patch) {
  if (!selected.value) return
  if (patch.status) selected.value.status = patch.status
  if (patch.jira_links) selected.value.jira_links = patch.jira_links
  if (patch.cc_emails) selected.value.cc_emails = patch.cc_emails
  if (patch.message) selected.value.messages.push(patch.message)
  const row = list.value.find((t) => t.number === selected.value.number)
  if (row && patch.status) row.status = patch.status
  if (mode.value === 'inbox' && patch.status && patch.status !== 'waiting_on_support') {
    // Reply moved the ticket out of the inbox queue — refresh the count quietly.
    loadInbox()
  }
}

function onDetailRefreshed(fresh) {
  // Only apply if it's still the open ticket (a poll can resolve after switching).
  if (!fresh || selectedNumber.value !== fresh.number) return
  selected.value = fresh
  const row = list.value.find((t) => t.number === fresh.number)
  if (row && row.status !== fresh.status) row.status = fresh.status
}

// New ticket modal
const newModal = ref(false)
const newSaving = ref(false)
const newError = ref('')
const newForm = ref({ company_id: '', customer_email: '', subject: '', category: 'question', body: '' })
function openNewTicket() {
  newError.value = ''
  newForm.value = { company_id: '', customer_email: '', subject: '', category: 'question', body: '' }
  newModal.value = true
  loadCompanies()
}
async function saveNewTicket() {
  if (!newForm.value.company_id || !newForm.value.subject.trim() || !newForm.value.body.trim()) {
    newError.value = 'Client, subject and message are required.'
    return
  }
  newSaving.value = true
  newError.value = ''
  try {
    await store.adminCreate({
      company_id: newForm.value.company_id,
      subject: newForm.value.subject.trim(),
      category: newForm.value.category,
      body: newForm.value.body.trim(),
      customer_email: newForm.value.customer_email.trim(),
      cc_emails: [],
    })
    newModal.value = false
    mode.value = 'all'
    await loadAll()
  } catch (e) {
    newError.value = e.message || 'Could not create ticket'
  } finally {
    newSaving.value = false
  }
}

async function refresh() {
  refreshing.value = true
  try {
    if (mode.value === 'inbox') await loadInbox()
    else await loadAll()
    if (selectedNumber.value) await selectTicket(selectedNumber.value)
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  loadCompanies()
  loadInbox()
})
</script>

<style scoped>
.mt { display: flex; flex-direction: column; height: 100%; min-height: 0; }

.mt-top { display: flex; align-items: center; gap: 16px; padding: 18px clamp(1rem, 2vw, 1.5rem) 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.back-link { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; color: var(--muted-foreground); padding: 6px 10px 6px 6px; border-radius: var(--radius-md); transition: color 0.15s, background 0.15s; flex-shrink: 0; }
.back-link:hover { color: var(--foreground); background: var(--muted); }
.mt-top h1 { flex: 1 1 auto; font-family: var(--font-ui); font-size: 1.3rem; font-weight: 650; letter-spacing: -0.01em; color: var(--foreground); margin: 0; }

.mt-body { flex: 1 1 auto; min-height: 0; display: flex; }
.mt-list { flex: 0 0 360px; min-width: 0; border-right: 1px solid var(--border); background: var(--card); overflow: hidden; display: flex; }
.mt-list > :deep(*) { flex: 1 1 auto; min-width: 0; }
.mt-detail { flex: 1 1 auto; min-width: 0; overflow: hidden; display: flex; }
.mt-detail > :deep(*) { flex: 1 1 auto; min-width: 0; }

.btn-primary { display: inline-flex; align-items: center; gap: 6px; background: var(--primary); color: var(--primary-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 600; padding: 9px 16px; border-radius: var(--radius-md); cursor: pointer; border: 1px solid var(--primary); transition: filter 0.15s; flex-shrink: 0; }
.btn-primary:hover { filter: brightness(0.94); }
.btn-primary:disabled { opacity: 0.6; }
.btn-primary svg { width: 15px; height: 15px; }
.btn-ghost { color: var(--muted-foreground); font-family: var(--font-ui); font-size: 13.5px; font-weight: 500; padding: 8px 14px; border-radius: var(--radius-md); cursor: pointer; }
.btn-ghost:hover { background: var(--muted); color: var(--foreground); }

/* New-ticket dialog (Reka Dialog provides the overlay/panel; this lays out
   the form body inside DialogContent). */
.mt-dialog-body { display: block; }
.modal-title { font-family: var(--font-ui); font-size: 1.15rem; font-weight: 600; color: var(--foreground); margin: 0 0 14px; }
.form-error { color: var(--destructive); font-size: 0.85rem; margin: 0 0 10px; }
.field { display: block; margin-bottom: 13px; }
.field > span { display: block; font-family: var(--font-ui); font-size: 12px; font-weight: 600; color: var(--muted-foreground); margin-bottom: 5px; }
.field input, .field select { width: 100%; height: 38px; padding: 0 11px; border-radius: var(--radius-md); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font-size: 14px; }
.field input:focus-visible, .field select:focus-visible { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
.field textarea { width: 100%; padding: 8px 11px; border-radius: var(--radius-md); border: 1px solid var(--input); background: var(--background); color: var(--foreground); font: inherit; font-size: 14px; resize: vertical; }
.field textarea:focus-visible { outline: 2px solid var(--ring); outline-offset: -1px; border-color: var(--ring); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }

@media (max-width: 860px) {
  .mt-body { position: relative; }
  .mt-list { flex: 1 1 auto; border-right: none; }
  .mt-detail { position: absolute; inset: 0; background: var(--background); transform: translateX(100%); transition: transform 0.22s ease; }
  .mt-body--detail .mt-list { display: none; }
  .mt-body--detail .mt-detail { transform: translateX(0); }
  @media (prefers-reduced-motion: reduce) { .mt-detail { transition: none; } }
}
</style>
