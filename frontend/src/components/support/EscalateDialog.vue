<script setup>
/**
 * Escalate a support ticket into a real Jira issue.
 *
 * The description arrives pre-composed from the ticket and the agent's internal
 * notes, but stays editable — the agent is the one who knows what engineering
 * actually needs, and filing something they haven't read would defeat the point.
 */
import { ref, watch } from 'vue'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useTicketsStore } from '@/stores/tickets'

const props = defineProps({
  ticket: { type: Object, required: true },
})
const emit = defineEmits(['escalated'])

const store = useTicketsStore()
const open = ref(false)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const result = ref(null)

const projects = ref([])
const issueTypes = ref([])
const priorities = ref([])
const form = ref({
  project: '', issue_type_id: '', priority_id: '', summary: '', description: '',
})

async function load(project) {
  loading.value = true
  error.value = ''
  try {
    const d = await store.adminEscalateOptions(props.ticket.number, project)
    projects.value = d.projects || []
    issueTypes.value = d.issue_types || []
    priorities.value = d.priorities || []
    form.value.project = d.project || ''
    // Bugs file as Bug; anything else defaults to Task.
    const wanted = props.ticket.category === 'bug' ? 'bug' : 'task'
    const match = issueTypes.value.find(t => t.name.toLowerCase() === wanted)
    form.value.issue_type_id = (match || issueTypes.value[0] || {}).id || ''
    // Only overwrite the text the first time — switching project shouldn't
    // discard edits the agent has already made.
    if (!form.value.summary) form.value.summary = d.summary || ''
    if (!form.value.description) form.value.description = d.description || ''
  } catch (e) {
    error.value = e.message || 'Could not load escalation options.'
  } finally {
    loading.value = false
  }
}

watch(open, (isOpen) => {
  if (isOpen && !projects.value.length) load()
})

function onProjectChange(project) {
  form.value.project = project
  load(project)
}

async function submit() {
  if (!form.value.summary.trim() || !form.value.description.trim()) {
    error.value = 'Summary and description are required.'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const res = await store.adminEscalate(props.ticket.number, { ...form.value })
    result.value = res
    emit('escalated', res)
  } catch (e) {
    error.value = e.message || 'Escalation failed.'
  } finally {
    submitting.value = false
  }
}

function close() {
  open.value = false
  result.value = null
}
</script>

<template>
  <button type="button" class="btn-outline sm" @click="open = true">Escalate to Jira</button>

  <Dialog v-model:open="open">
    <DialogContent class="esc-dialog">
      <DialogHeader>
        <DialogTitle>Escalate {{ ticket.display_number }} to Jira</DialogTitle>
      </DialogHeader>

      <div v-if="result" class="esc-done">
        <p class="esc-key">
          Created <a :href="`https://citemed.atlassian.net/browse/${result.key}`"
                     target="_blank" rel="noopener noreferrer">{{ result.key }}</a>
        </p>
        <p v-if="result.epic_key" class="esc-meta">
          Filed under epic {{ result.epic_key }}<span v-if="result.sprint_id"> · added to the active sprint</span>.
        </p>
        <ul v-if="result.warnings && result.warnings.length" class="esc-warnings">
          <li v-for="w in result.warnings" :key="w">{{ w }}</li>
        </ul>
        <button class="btn-outline sm" @click="close">Done</button>
      </div>

      <div v-else class="esc-body">
        <p v-if="error" class="esc-error" role="alert">{{ error }}</p>
        <p v-if="loading" class="esc-muted">Loading Jira options…</p>

        <div class="esc-row">
          <label class="esc-field">
            <span>Project</span>
            <select :value="form.project" :disabled="loading || submitting"
                    @change="onProjectChange($event.target.value)">
              <option v-for="p in projects" :key="p" :value="p">{{ p }}</option>
            </select>
          </label>
          <label class="esc-field">
            <span>Issue type</span>
            <select v-model="form.issue_type_id" :disabled="loading || submitting">
              <option v-for="t in issueTypes" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </label>
          <label class="esc-field">
            <span>Priority</span>
            <select v-model="form.priority_id" :disabled="loading || submitting">
              <option value="">Default</option>
              <option v-for="p in priorities" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </label>
        </div>

        <label class="esc-field">
          <span>Summary</span>
          <input v-model="form.summary" type="text" maxlength="255" :disabled="submitting" />
        </label>

        <label class="esc-field">
          <span>Description</span>
          <textarea v-model="form.description" rows="12" :disabled="submitting"></textarea>
        </label>
        <p class="esc-hint">
          Pre-filled from the ticket and your internal notes. Edit before filing —
          this goes to engineering, not the customer.
        </p>

        <div class="esc-actions">
          <button class="btn-outline sm" :disabled="submitting" @click="open = false">Cancel</button>
          <button class="btn-primary sm" :disabled="submitting || loading" @click="submit">
            {{ submitting ? 'Escalating…' : 'Escalate' }}
          </button>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.esc-dialog { max-width: 680px; }
.esc-body, .esc-done { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
.esc-row { display: flex; gap: 10px; flex-wrap: wrap; }
.esc-row .esc-field { flex: 1 1 160px; }
.esc-field { display: flex; flex-direction: column; gap: 4px; font-size: 0.8rem; }
.esc-field > span { font-weight: 600; color: var(--muted-foreground); }
.esc-field select, .esc-field input, .esc-field textarea {
  padding: 6px 8px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--background); color: var(--foreground);
  font-family: inherit; font-size: 0.85rem;
}
.esc-field textarea { font-family: var(--font-mono, ui-monospace, monospace); font-size: 0.78rem; line-height: 1.5; resize: vertical; }
.esc-hint { margin: 0; font-size: 0.75rem; color: var(--muted-foreground); }
.esc-muted { margin: 0; font-size: 0.82rem; color: var(--muted-foreground); }
.esc-error { margin: 0; font-size: 0.82rem; color: var(--destructive); }
.esc-actions { display: flex; justify-content: flex-end; gap: 8px; }
.esc-key { margin: 0; font-size: 0.95rem; font-weight: 600; }
.esc-meta { margin: 0; font-size: 0.82rem; color: var(--muted-foreground); }
.esc-warnings { margin: 0; padding-left: 18px; font-size: 0.8rem; color: var(--destructive); }
</style>
