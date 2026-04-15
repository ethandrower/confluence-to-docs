<template>
  <AppShell hide-sidebar>
    <template #content>
      <ContactForm />
    </template>
  </AppShell>
</template>

<script setup>
import AppShell from '@/components/layout/AppShell.vue'
import ContactForm from '@/components/tickets/ContactForm.vue'
</script>
