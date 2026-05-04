<script setup lang="ts">
import { useTheme } from '@proj-airi/ui'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import LogoDark from '../../assets/logo-dark.svg'
import Logo from '../../assets/logo.svg'

import { BackgroundKind, useBackgroundStore } from '../../stores/background'

const { selectedOption } = storeToRefs(useBackgroundStore())
const { isDark: dark } = useTheme()
const route = useRoute()
const brandLabel = computed(() => route.path.startsWith('/lesson') ? '米粒老师' : 'AIRI')
</script>

<template>
  <RouterLink
    to="/" flex="~" items-center
    gap-2 px-2 text-nowrap text-2xl outline-none
  >
    <template v-if="selectedOption?.kind === BackgroundKind.Wave">
      <template v-if="dark">
        <img :src="LogoDark" h-8 w-8 class="theme-colored" :alt="brandLabel">
      </template>
      <template v-else>
        <img :src="Logo" h-8 w-8 class="theme-colored" :alt="brandLabel">
      </template>
    </template>
  </RouterLink>
</template>

<style scoped>
.theme-colored {
  filter: hue-rotate(calc(var(--chromatic-hue, 0) * 1deg));
}
</style>
