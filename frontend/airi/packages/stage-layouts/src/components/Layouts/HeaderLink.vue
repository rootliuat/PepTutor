<script setup lang="ts">
import { RouterLink } from 'vue-router'

import Logo from '../../assets/logo.svg'
</script>

<template>
  <RouterLink
    to="/" flex="~"
    w-max items-center gap-2 px-2 text-nowrap text-2xl outline-none
  >
    <img :src="Logo" h-8 w-8 class="theme-colored" alt="AIRI">
    <div translate-y="[2px]" font-quicksand font-semibold>
      <span>AIRI</span>
    </div>
  </RouterLink>
</template>

<style scoped>
.theme-colored {
  filter: hue-rotate(calc(var(--chromatic-hue, 0) * 1deg));
}
</style>
