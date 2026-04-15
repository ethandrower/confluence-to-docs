<template>
  <div class="contact-page">
    <!-- Hero -->
    <div class="contact-hero">
      <div class="hero-title">
        <div class="hero-icon">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
          </svg>
        </div>
        <h1>Contact Support</h1>
      </div>
      <p>Have a question, found an issue, or need help? Send us a message and our team will get back to you.</p>
    </div>

    <!-- Form card -->
    <div v-if="!submitted" class="form-card">
      <form @submit.prevent="submit" class="contact-form">
        <div class="form-row">
          <div class="form-group">
            <label for="contact-name">Name</label>
            <input
              id="contact-name"
              type="text"
              v-model="form.name"
              placeholder="Your name"
              class="form-input"
              :class="{ 'form-input--error': errors.name }"
            />
            <p v-if="errors.name" class="field-error">{{ errors.name }}</p>
          </div>
          <div class="form-group">
            <label for="contact-email">Email</label>
            <input
              id="contact-email"
              type="email"
              v-model="form.email"
              placeholder="you@company.com"
              class="form-input"
              :class="{ 'form-input--error': errors.email }"
            />
            <p v-if="errors.email" class="field-error">{{ errors.email }}</p>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="contact-category">Category</label>
            <select id="contact-category" v-model="form.category" class="form-input">
              <option value="question">Question</option>
              <option value="bug">Bug Report</option>
              <option value="feature">Feature Request</option>
              <option value="docs">Documentation Issue</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div class="form-group">
            <label for="contact-subject">Subject</label>
            <input
              id="contact-subject"
              type="text"
              v-model="form.subject"
              placeholder="Brief summary"
              class="form-input"
              :class="{ 'form-input--error': errors.subject }"
              maxlength="255"
            />
            <p v-if="errors.subject" class="field-error">{{ errors.subject }}</p>
          </div>
        </div>

        <div class="form-group">
          <label for="contact-message">Message</label>
          <textarea
            id="contact-message"
            v-model="form.message"
            placeholder="Describe your question or issue in detail..."
            rows="5"
            class="form-input form-textarea"
            :class="{ 'form-input--error': errors.message }"
          />
          <p v-if="errors.message" class="field-error">{{ errors.message }}</p>
        </div>

        <div class="form-footer">
          <button type="submit" class="btn-submit" :disabled="submitting">
            <svg v-if="submitting" class="spin" width="16" height="16" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ submitting ? 'Sending...' : 'Send Message' }}
          </button>
          <p class="form-hint">We'll respond to your email within 1-2 business days.</p>
        </div>

        <p v-if="serverError" class="server-error">{{ serverError }}</p>
      </form>
    </div>

    <!-- Success state -->
    <div v-else class="success-card">
      <div class="success-check">
        <svg width="48" height="48" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
      </div>
      <h2>Message Sent</h2>
      <p>Thanks for reaching out! We'll get back to you at <strong>{{ submittedEmail }}</strong>.</p>
      <button @click="reset" class="btn-another">Send another message</button>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import axios from 'axios'

const form = reactive({
  name: '',
  email: '',
  category: 'question',
  subject: '',
  message: '',
})
const errors = reactive({})
const submitting = ref(false)
const serverError = ref('')
const submitted = ref(false)
const submittedEmail = ref('')

function validate() {
  let valid = true
  Object.keys(errors).forEach(k => delete errors[k])

  if (!form.name.trim()) { errors.name = 'Name is required'; valid = false }
  if (!form.email.trim()) { errors.email = 'Email is required'; valid = false }
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) { errors.email = 'Enter a valid email'; valid = false }
  if (!form.subject.trim()) { errors.subject = 'Subject is required'; valid = false }
  if (!form.message.trim()) { errors.message = 'Message is required'; valid = false }

  return valid
}

async function submit() {
  if (!validate()) return
  submitting.value = true
  serverError.value = ''
  try {
    await axios.post('/api/tickets/submit/', {
      name: form.name.trim(),
      email: form.email.trim(),
      category: form.category,
      subject: form.subject.trim(),
      message: form.message.trim(),
    })
    submittedEmail.value = form.email.trim()
    submitted.value = true
  } catch (e) {
    const data = e.response?.data
    if (data?.errors) {
      Object.assign(errors, data.errors)
    } else {
      serverError.value = data?.error || 'Failed to send message. Please try again.'
    }
  } finally {
    submitting.value = false
  }
}

function reset() {
  Object.assign(form, { name: '', email: '', category: 'question', subject: '', message: '' })
  Object.keys(errors).forEach(k => delete errors[k])
  serverError.value = ''
  submitted.value = false
  submittedEmail.value = ''
}
</script>

<style scoped>
.contact-page {
  max-width: 600px;
  margin: 0 auto;
  padding: 48px 24px 64px;
}

/* ── Hero ── */
.contact-hero {
  text-align: center;
  margin-bottom: 32px;
}

.hero-title {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 8px;
}

.hero-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: oklch(0.52 0.20 260 / 0.08);
  color: var(--primary);
  flex-shrink: 0;
}

.contact-hero h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--foreground);
  margin: 0;
  letter-spacing: -0.01em;
}

.contact-hero p {
  font-size: 0.875rem;
  color: var(--muted-foreground);
  margin: 0;
  line-height: 1.6;
  max-width: 440px;
  margin-inline: auto;
}

/* ── Form card ── */
.form-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 28px;
  box-shadow: 0 1px 3px oklch(0 0 0 / 0.04), 0 1px 2px oklch(0 0 0 / 0.02);
}

.contact-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 520px) {
  .form-row { grid-template-columns: 1fr; }
  .form-card { padding: 20px; }
  .contact-page { padding: 32px 16px 48px; }
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 0.8125rem;
  font-weight: 550;
  color: var(--foreground);
}

.form-input {
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.875rem;
  font-family: inherit;
  color: var(--foreground);
  background: var(--background);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.form-input::placeholder {
  color: var(--muted-foreground);
  opacity: 0.6;
}

.form-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px oklch(0.52 0.20 260 / 0.08);
}

.form-input--error {
  border-color: var(--destructive);
}

.form-input--error:focus {
  box-shadow: 0 0 0 3px oklch(0.55 0.22 25 / 0.08);
}

select.form-input {
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 8px center;
  background-repeat: no-repeat;
  background-size: 20px;
  padding-right: 36px;
}

.form-textarea {
  resize: vertical;
  min-height: 120px;
  line-height: 1.5;
}

.field-error {
  font-size: 0.75rem;
  color: var(--destructive);
  margin: 0;
}

/* ── Footer ── */
.form-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-top: 4px;
}

.btn-submit {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 550;
  cursor: pointer;
  transition: opacity 0.15s;
  white-space: nowrap;
}

.btn-submit:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-hint {
  font-size: 0.75rem;
  color: var(--muted-foreground);
  margin: 0;
  opacity: 0.7;
}

.server-error {
  font-size: 0.8125rem;
  color: var(--destructive);
  margin: 0;
}

/* ── Success state ── */
.success-card {
  text-align: center;
  padding: 56px 32px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 1px 3px oklch(0 0 0 / 0.04), 0 1px 2px oklch(0 0 0 / 0.02);
}

.success-check {
  color: var(--primary);
  margin-bottom: 16px;
}

.success-card h2 {
  font-size: 1.25rem;
  font-weight: 650;
  margin: 0 0 8px;
  color: var(--foreground);
}

.success-card p {
  font-size: 0.875rem;
  color: var(--muted-foreground);
  margin: 0 0 24px;
  line-height: 1.5;
}

.btn-another {
  padding: 8px 20px;
  background: transparent;
  color: var(--primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.8125rem;
  font-weight: 550;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-another:hover {
  background: var(--muted);
}

/* ── Spinner ── */
.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
