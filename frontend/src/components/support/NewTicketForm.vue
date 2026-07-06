<template>
  <form class="ntf" @submit.prevent="submit">
    <div class="ntf-row">
      <div class="ntf-group ntf-group--subject">
        <label for="nt-subject">Subject</label>
        <input
          id="nt-subject"
          v-model="subject"
          type="text"
          class="ntf-input"
          :class="{ 'ntf-input--error': errors.subject }"
          placeholder="Brief summary"
          maxlength="512"
        />
        <p v-if="errors.subject" class="ntf-error">{{ errors.subject }}</p>
      </div>
      <div class="ntf-group">
        <label for="nt-category">Category</label>
        <select id="nt-category" v-model="category" class="ntf-input">
          <option value="question">Question</option>
          <option value="bug">Bug Report</option>
          <option value="feature">Feature Request</option>
          <option value="docs">Documentation Issue</option>
          <option value="other">Other</option>
        </select>
      </div>
    </div>

    <div class="ntf-group">
      <label for="nt-message">Message</label>
      <textarea
        id="nt-message"
        v-model="body"
        class="ntf-input ntf-textarea"
        :class="{ 'ntf-input--error': errors.body }"
        rows="5"
        placeholder="Describe your question or issue in detail…"
      />
      <p v-if="errors.body" class="ntf-error">{{ errors.body }}</p>
    </div>

    <div class="ntf-group">
      <label for="nt-cc">CC emails <span class="ntf-optional">(optional)</span></label>
      <input
        id="nt-cc"
        v-model="ccRaw"
        type="text"
        class="ntf-input"
        placeholder="teammate@company.com, other@company.com"
      />
      <p class="ntf-hint">Separate multiple addresses with commas. They'll be copied on replies.</p>
    </div>

    <p v-if="serverError" class="ntf-server-error" role="alert">{{ serverError }}</p>

    <div class="ntf-actions">
      <button type="button" class="btn-ghost" @click="$emit('cancel')">Cancel</button>
      <button type="submit" class="btn-primary" :disabled="submitting">
        {{ submitting ? 'Sending…' : 'Send ticket' }}
      </button>
    </div>
  </form>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useTicketsStore } from '@/stores/tickets'

const emit = defineEmits(['created', 'cancel'])
const store = useTicketsStore()

const subject = ref('')
const category = ref('question')
const body = ref('')
const ccRaw = ref('')
const errors = reactive({})
const serverError = ref('')
const submitting = ref(false)

function validate() {
  Object.keys(errors).forEach((k) => delete errors[k])
  let valid = true
  if (!subject.value.trim()) { errors.subject = 'Subject is required'; valid = false }
  if (!body.value.trim()) { errors.body = 'Message is required'; valid = false }
  return valid
}

function parseCcs() {
  return ccRaw.value.split(',').map((e) => e.trim()).filter(Boolean)
}

async function submit() {
  if (!validate()) return
  submitting.value = true
  serverError.value = ''
  try {
    const ticket = await store.createTicket({
      subject: subject.value.trim(),
      body: body.value.trim(),
      category: category.value,
      cc_emails: parseCcs(),
    })
    emit('created', ticket)
  } catch (e) {
    serverError.value = e.message || 'Failed to create ticket. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.ntf {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--card);
  padding: 1.25rem;
  margin-bottom: 1.25rem;
}
.ntf-row { display: grid; grid-template-columns: 1fr 200px; gap: 1rem; }
@media (max-width: 560px) { .ntf-row { grid-template-columns: 1fr; } }

.ntf-group { display: flex; flex-direction: column; gap: 0.35rem; }
.ntf-group--subject { min-width: 0; }
.ntf-group label { font-size: 0.8125rem; font-weight: 550; color: var(--foreground); }
.ntf-optional { font-weight: 400; color: var(--muted-foreground); }

.ntf-input {
  padding: 0.55rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
  font-family: inherit;
  color: var(--foreground);
  background: var(--background);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ntf-input::placeholder { color: var(--muted-foreground); opacity: 0.7; }
.ntf-input:focus-visible { border-color: var(--brand-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand-accent) 15%, transparent); }
.ntf-input--error { border-color: var(--destructive); }
.ntf-textarea { resize: vertical; min-height: 110px; line-height: 1.5; }

select.ntf-input {
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%23626a7a' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 10px center;
  background-repeat: no-repeat;
  background-size: 18px;
  padding-right: 34px;
}

.ntf-error { font-size: 0.75rem; color: var(--destructive); margin: 0; }
.ntf-hint { font-size: 0.76rem; color: var(--muted-foreground); margin: 0; }
.ntf-server-error { font-size: 0.85rem; color: var(--destructive); margin: 0; }

.ntf-actions { display: flex; justify-content: flex-end; gap: 0.6rem; }
.btn-ghost { background: none; border: 1px solid var(--border); color: var(--foreground); border-radius: var(--radius-sm); padding: 0.5rem 1rem; cursor: pointer; font: inherit; font-size: 0.85rem; font-weight: 550; }
.btn-ghost:hover { background: var(--muted); }
.btn-primary { background: var(--primary); color: var(--primary-foreground); border: none; border-radius: var(--radius-sm); padding: 0.5rem 1.1rem; cursor: pointer; font: inherit; font-size: 0.85rem; font-weight: 600; transition: opacity 0.15s; }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
