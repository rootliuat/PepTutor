<script setup lang="ts">
import { LoginDrawer } from '@proj-airi/stage-ui/components/auth/index'
import { useAuthStore } from '@proj-airi/stage-ui/stores/auth'
import { isLessonRouteLike } from '@proj-airi/stage-ui/utils'
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

const route = useRoute()
const isLessonRoute = computed(() => isLessonRouteLike(route))
let authStore: ReturnType<typeof useAuthStore> | null = null

function ensureAuthStore() {
  authStore ??= useAuthStore()
  return authStore
}

const isLoginDrawerOpen = computed({
  get: () => isLessonRoute.value ? false : ensureAuthStore().isLoginDrawerOpen,
  set: (open: boolean) => {
    if (isLessonRoute.value) {
      return
    }
    ensureAuthStore().isLoginDrawerOpen = open
  },
})
</script>

<template>
  <main h-full font-cute>
    <RouterView />
    <LoginDrawer v-if="!isLessonRoute" v-model:open="isLoginDrawerOpen" />
  </main>
</template>
