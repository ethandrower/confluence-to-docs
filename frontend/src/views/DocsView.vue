<template>
  <div class="app-shell">
    <AppShell>
      <template #sidebar>
        <DocSidebar />
      </template>
      <template #content>
        <RouterView v-slot="{ Component }">
          <Transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </template>
    </AppShell>
  </div>
</template>

<script setup>
import AppShell from '@/components/layout/AppShell.vue'
import DocSidebar from '@/components/layout/DocSidebar.vue'
import { useDocsStore } from '@/stores/docs.js'
import { onMounted } from 'vue'

const store = useDocsStore()
onMounted(() => store.fetchTree())
</script>
