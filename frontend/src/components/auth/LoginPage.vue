<template>
  <form @submit.prevent="submit" class="login-form">
    <label for="email" class="form-label">Email address</label>
    <input
      id="email"
      type="email"
      v-model="email"
      placeholder="you@example.com"
      class="form-input"
      :class="{ error: emailError }"
      required
      autocomplete="email"
    />
    <p v-if="emailError" class="field-error">{{ emailError }}</p>
    <button type="submit" class="btn-primary" :disabled="loading">
      {{ loading ? 'Sending...' : 'Send login link' }}
    </button>
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
    serverError.value = 'Something went wrong. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-form { display: flex; flex-direction: column; gap: 0.75rem; }
.form-label { font-size: 0.875rem; font-weight: 500; color: var(--text-primary); }
.form-input {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.9rem;
  outline: none;
  width: 100%;
  box-sizing: border-box;
}
.form-input:focus { border-color: var(--accent); }
.form-input.error { border-color: #ef4444; }
.field-error { font-size: 0.8rem; color: #ef4444; margin: -0.25rem 0 0; }
.btn-primary {
  padding: 10px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  margin-top: 0.25rem;
}
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-primary:hover:not(:disabled) { background: var(--accent-dark); }
.server-error { font-size: 0.8rem; color: #ef4444; text-align: center; }
</style>
