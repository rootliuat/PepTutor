<script setup lang="ts">
import { ProfileSwitcherPopover } from '@proj-airi/stage-ui/components'
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import HeaderAvatar from './HeaderAvatar.vue'
import HeaderLink from './HeaderLink.vue'
import ActionAbout from './InteractiveArea/Actions/About.vue'

const route = useRoute()
const router = useRouter()
const lessonActive = computed(() => route.path.startsWith('/lesson'))

function handleNavigation() {
  router.push('/settings/airi-card')
}
</script>

<template>
  <header mb-1 w-full flex items-center justify-between gap-2>
    <HeaderLink />
    <div flex items-center gap-2>
      <div
        v-if="lessonActive"
        aria-current="page"
        :class="[
          'flex cursor-default items-center gap-2 rounded-full border-2 border-solid px-3 py-2 text-sm font-medium',
          'border-primary-300/60 bg-primary-300/20 text-primary-900 dark:border-primary-500/50 dark:bg-primary-500/20 dark:text-primary-50',
        ]"
      >
        <div class="i-solar:book-bookmark-bold-duotone h-4 w-4" />
        <span>Lesson</span>
      </div>
      <RouterLink
        v-else
        to="/lesson"
        :class="[
          'flex items-center gap-2 rounded-full border-2 border-solid px-3 py-2 text-sm font-medium outline-none transition-all duration-200 ease-in-out',
          'border-neutral-200/60 bg-white/60 text-neutral-600 dark:border-neutral-800/70 dark:bg-neutral-900/70 dark:text-neutral-200',
        ]"
      >
        <div class="i-solar:book-bookmark-bold-duotone h-4 w-4" />
        <span>Lesson</span>
      </RouterLink>
      <ProfileSwitcherPopover v-if="!lessonActive" @create="handleNavigation" @manage="handleNavigation" />
      <ActionAbout />
      <HeaderAvatar />
    </div>
  </header>
</template>
