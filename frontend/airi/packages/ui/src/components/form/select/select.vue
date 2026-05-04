<script setup lang="ts">
import { provide, ref } from 'vue'

import { Combobox } from '../combobox'

const props = defineProps<{
  options?: { label: string, value: string | number }[]
  inputId?: string
  inputName?: string
  placeholder?: string
  disabled?: boolean
  title?: string
  layout?: 'horizontal' | 'vertical'
}>()

const show = ref(false)
const modelValue = defineModel<string | number>({ required: false })

function selectOption(value: string | number) {
  modelValue.value = value
}

function handleHide() {
  show.value = false
}

provide('selectOption', selectOption)
provide('hide', handleHide)
</script>

<template>
  <Combobox
    v-model="modelValue"
    :default-value="modelValue"
    :input-id="props.inputId"
    :input-name="props.inputName"
    :options="[{ groupLabel: '', children: props.options }]"
    :placeholder="props.placeholder"
  />
</template>
