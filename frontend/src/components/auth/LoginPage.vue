<template>
  <form @submit.prevent="submit" class="login-form">
    <div class="form-group">
      <label for="email" class="form-label">Email address</label>
      <input
        id="email"
        type="email"
        v-model="email"
        placeholder="you@company.com"
        class="form-input"
        :class="{ 'form-input--error': emailError }"
        required
        autocomplete="email"
        autofocus
      />
      <p v-if="emailError" class="field-error">{{ emailError }}</p>
    </div>

    <button type="submit" class="btn-primary" :disabled="loading">
      <svg v-if="loading" class="spin" width="16" height="16" fill="none" viewBox="0 0 24 24" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      {{ loading ? 'Sending...' : 'Send login link' }}
    </button>

    <p class="form-hint">
      We'll email you a secure link to sign in — no password needed.
    </p>

    <p v-if="serverError" class="server-error">{{ serverError }}</p>
  </form>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth.js'

const emit = defineEmits(['sent'])
const auth = useAuthStore()
const email = ref('')
const loading = ref(false)
const emailError = ref('')
const serverError = ref('')

function validateEmail(e) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)
}

async function submit() {
  emailError.value = ''
  serverError.value = ''
  if (!validateEmail(email.value)) {
    emailError.value = 'Please enter a valid email address'
    return
  }
  loading.value = true
  try {
    await auth.requestMagicLink(email.value)
    emit('sent')
  } catch (e) {
    if (e.response?.status === 429) {
      serverError.value = 'Too many requests. Please try again in a few minutes.'
    } else {
      serverError.value = 'Something went wrong. Please try again.'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 0.8125rem;
  font-weight: 550;
  color: var(--foreground);
}

.form-input {
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 0.9375rem;
  font-family: inherit;
  color: var(--foreground);
  background: var(--background);
  outline: none;
  width: 100%;
  box-sizing: border-box;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.form-input::placeholder {
  color: var(--muted-foreground);
  opacity: 0.55;
}

.form-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px oklch(0.52 0.20 260 / 0.12);
}

.form-input--error {
  border-color: var(--destructive);
}

.form-input--error:focus {
  box-shadow: 0 0 0 3px oklch(0.55 0.22 25 / 0.12);
}

.field-error {
  font-size: 0.75rem;
  color: var(--destructive);
  margin: 0;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 16px;
  background: var(--primary);
  color: var(--primary-foreground);
  border: none;
  border-radius: 8px;
  font-size: 0.9375rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  letter-spacing: -0.005em;
  transition: background 0.15s, transform 0.04s;
}

.btn-primary:hover:not(:disabled) {
  background: oklch(0.46 0.20 260);
}

.btn-primary:active:not(:disabled) {
  transform: translateY(0.5px);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-hint {
  font-size: 0.75rem;
  color: var(--muted-foreground);
  margin: 0;
  text-align: center;
  line-height: 1.5;
}

.server-error {
  font-size: 0.8125rem;
  color: var(--destructive);
  text-align: center;
  margin: 0;
  padding: 10px 12px;
  background: oklch(0.95 0.03 25 / 0.6);
  border: 1px solid oklch(0.85 0.06 25);
  border-radius: 8px;
}

.spin {
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
