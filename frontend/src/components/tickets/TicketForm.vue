<template>
  <AuthGate>
    <div class="ticket-form-page">
      <h1>Submit a Ticket</h1>
      <div v-if="auth.canSubmitTickets">
        <form @submit.prevent="submit" class="ticket-form">
          <div class="form-group">
            <label>Request Type</label>
            <select v-model="form.requestTypeId" required class="form-select">
              <option value="" disabled>Select a request type...</option>
              <option v-for="rt in store.requestTypes" :key="rt.id" :value="rt.id">
                {{ rt.name }}
              </option>
            </select>
            <p v-if="errors.requestTypeId" class="field-error">{{ errors.requestTypeId }}</p>
          </div>
          <div class="form-group">
            <label>Summary</label>
            <input
              type="text"
              v-model="form.summary"
              placeholder="Brief description of your issue"
              class="form-input"
              :class="{ error: errors.summary }"
              maxlength="255"
            />
            <p v-if="errors.summary" class="field-error">{{ errors.summary }}</p>
          </div>
          <div class="form-group">
            <label>Description</label>
            <textarea
              v-model="form.description"
              placeholder="Describe your issue in detail..."
              rows="6"
              class="form-textarea"
              :class="{ error: errors.description }"
            />
            <p v-if="errors.description" class="field-error">{{ errors.description }}</p>
          </div>
          <button type="submit" class="btn-primary" :disabled="submitting">
            {{ submitting ? 'Submitting...' : 'Submit ticket' }}
          </button>
          <p v-if="serverError" class="server-error">{{ serverError }}</p>
        </form>
      </div>
      <div v-else class="not-authorized">
        <p>Ticket submission is available to CiteMed customers only.</p>
        <p>If you're a customer and can't submit tickets, contact us at <a href="mailto:support@citemed.com">support@citemed.com</a></p>
      </div>
    </div>
  </AuthGate>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth.js'
import { useTicketsStore } from '@/stores/tickets.js'
import AuthGate from '@/components/auth/AuthGate.vue'

const auth = useAuthStore()
const store = useTicketsStore()
const router = useRouter()

const form = reactive({ requestTypeId: '', summary: '', description: '' })
const errors = reactive({ requestTypeId: '', summary: '', description: '' })
const submitting = ref(false)
const serverError = ref('')

onMounted(() => store.fetchRequestTypes())

function validate() {
  let valid = true
  errors.requestTypeId = form.requestTypeId ? '' : 'Please select a request type'
  errors.summary = form.summary.trim() ? '' : 'Summary is required'
  errors.description = form.description.trim() ? '' : 'Description is required'
  if (errors.requestTypeId || errors.summary || errors.description) valid = false
  return valid
}

async function submit() {
  if (!validate()) return
  submitting.value = true
  serverError.value = ''
  try {
    await store.submitTicket({
      requestTypeId: form.requestTypeId,
      summary: form.summary,
      description: form.description,
    })
    router.push({ name: 'ticket-list' })
  } catch (e) {
    serverError.value = e.response?.data?.error || 'Failed to submit ticket. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.ticket-form-page { max-width: 600px; }
h1 { font-size: 1.75rem; font-weight: 700; margin-bottom: 1.5rem; }
.ticket-form { display: flex; flex-direction: column; gap: 1.25rem; }
.form-group { display: flex; flex-direction: column; gap: 0.4rem; }
.form-group label { font-size: 0.875rem; font-weight: 500; }
.form-input, .form-select, .form-textarea {
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.9rem;
  font-family: inherit;
  outline: none;
  width: 100%;
  box-sizing: border-box;
}
.form-input:focus, .form-select:focus, .form-textarea:focus { border-color: var(--accent); }
.form-input.error, .form-textarea.error { border-color: #ef4444; }
.form-textarea { resize: vertical; }
.field-error { font-size: 0.8rem; color: #ef4444; margin: 0; }
.btn-primary {
  padding: 10px 20px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  align-self: flex-start;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-primary:hover:not(:disabled) { background: var(--accent-dark); }
.server-error { font-size: 0.875rem; color: #ef4444; }
.not-authorized { padding: 1.5rem; background: var(--surface-1); border-radius: 8px; border: 1px solid var(--border); }
.not-authorized p { color: var(--text-secondary); margin-bottom: 0.5rem; }
.not-authorized a { color: var(--accent); }
</style>
