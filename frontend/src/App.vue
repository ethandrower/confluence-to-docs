<template>
  <RouterView />
  <AppLoader />
</template>

<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth.js'
import AppLoader from '@/components/layout/AppLoader.vue'

const auth = useAuthStore()
onMounted(() => auth.fetchMe())
</script>
