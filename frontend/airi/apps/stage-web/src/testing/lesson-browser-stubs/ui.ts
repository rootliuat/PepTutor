import { computed, defineComponent, h, ref } from 'vue'

interface SelectOption {
  label?: string
  value?: string
}

function normalizedValue(value: unknown): string {
  return typeof value === 'string' ? value : String(value ?? '')
}

function createPassThroughComponent(name: string, tag: string = 'div') {
  return defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      return () => h(tag, attrs, slots.default?.())
    },
  })
}

export function useDeferredMount() {
  return {
    isReady: ref(true),
  }
}

export function useTheme() {
  return {
    isDark: ref(false),
  }
}

export const Button = defineComponent({
  name: 'LessonUiButtonStub',
  inheritAttrs: false,
  props: {
    disabled: Boolean,
    loading: Boolean,
  },
  emits: ['click'],
  setup(props, { attrs, emit, slots }) {
    return () => h('button', {
      ...attrs,
      disabled: props.disabled || props.loading,
      type: 'button',
      onClick: (event: MouseEvent) => emit('click', event),
    }, slots.default?.())
  },
})

export const Callout = defineComponent({
  name: 'LessonUiCalloutStub',
  inheritAttrs: false,
  props: {
    label: {
      type: String,
      default: '',
    },
  },
  setup(props, { attrs, slots }) {
    return () => h('div', {
      ...attrs,
      'data-testid': attrs['data-testid'] || 'lesson-ui-callout-stub',
    }, [
      props.label ? h('div', { 'data-testid': 'lesson-ui-callout-label' }, props.label) : null,
      slots.default?.(),
    ])
  },
})

export const FieldSelect = defineComponent({
  name: 'LessonUiFieldSelectStub',
  inheritAttrs: false,
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
    label: {
      type: String,
      default: '',
    },
    description: {
      type: String,
      default: '',
    },
    options: {
      type: Array as () => SelectOption[],
      default: () => [],
    },
    placeholder: {
      type: String,
      default: '',
    },
    disabled: Boolean,
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    const value = computed(() => normalizedValue(props.modelValue))

    return () => h('label', {
      ...attrs,
      'data-testid': attrs['data-testid'] || 'lesson-ui-field-select-stub',
    }, [
      props.label ? h('span', props.label) : null,
      props.description ? h('span', props.description) : null,
      h('select', {
        disabled: props.disabled,
        value: value.value,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value),
        onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value),
      }, [
        props.placeholder
          ? h('option', {
              value: '',
              disabled: true,
            }, props.placeholder)
          : null,
        ...props.options.map(option => h('option', {
          key: normalizedValue(option.value),
          value: normalizedValue(option.value),
        }, option.label || normalizedValue(option.value))),
      ]),
    ])
  },
})

export const Input = defineComponent({
  name: 'LessonUiInputStub',
  inheritAttrs: false,
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    const value = computed(() => normalizedValue(props.modelValue))

    return () => h('input', {
      ...attrs,
      value: value.value,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
    })
  },
})

export const Progress = defineComponent({
  name: 'LessonUiProgressStub',
  inheritAttrs: false,
  props: {
    progress: {
      type: Number,
      default: 0,
    },
  },
  setup(props, { attrs }) {
    return () => h('div', {
      ...attrs,
      'role': 'progressbar',
      'aria-valuemin': 0,
      'aria-valuemax': 100,
      'aria-valuenow': Math.round(props.progress),
      'data-progress': String(props.progress),
    })
  },
})

export const SelectTab = defineComponent({
  name: 'LessonUiSelectTabStub',
  inheritAttrs: false,
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
    options: {
      type: Array as () => SelectOption[],
      default: () => [],
    },
    disabled: Boolean,
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    const value = computed(() => normalizedValue(props.modelValue))

    return () => h('div', {
      ...attrs,
      'role': 'radiogroup',
      'data-testid': attrs['data-testid'] || 'lesson-ui-select-tab-stub',
    }, props.options.map((option) => {
      const optionValue = normalizedValue(option.value)
      return h('button', {
        'key': optionValue,
        'type': 'button',
        'role': 'radio',
        'aria-label': option.label || optionValue,
        'aria-checked': String(value.value === optionValue),
        'disabled': props.disabled,
        'onClick': () => emit('update:modelValue', optionValue),
      }, option.label || optionValue)
    }))
  },
})

export const BasicTextarea = defineComponent({
  name: 'LessonUiBasicTextareaStub',
  inheritAttrs: false,
  props: {
    modelValue: {
      type: [String, Number],
      default: '',
    },
  },
  emits: ['update:modelValue', 'submit', 'compositionstart', 'compositionend'],
  setup(props, { attrs, emit }) {
    const value = computed(() => normalizedValue(props.modelValue))

    return () => h('textarea', {
      ...attrs,
      value: value.value,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
      onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLTextAreaElement).value),
      onCompositionstart: (event: CompositionEvent) => emit('compositionstart', event),
      onCompositionend: (event: CompositionEvent) => emit('compositionend', event),
      onKeydown: (event: KeyboardEvent) => {
        if (event.key === 'Enter' && !event.shiftKey) {
          emit('submit')
        }
      },
    })
  },
})

export const Collapsible = createPassThroughComponent('LessonUiCollapsibleStub')
export const TransitionVertical = createPassThroughComponent('LessonUiTransitionVerticalStub')
export const Screen = createPassThroughComponent('LessonUiScreenStub')
export const Skeleton = createPassThroughComponent('LessonUiSkeletonStub')
export const Select = createPassThroughComponent('LessonUiSelectStub')
export const InputFile = createPassThroughComponent('LessonUiInputFileStub', 'input')
export const BasicInputFile = InputFile
export const InputKeyValue = createPassThroughComponent('LessonUiInputKeyValueStub')
export const DoubleCheckButton = Button
export const Textarea = BasicTextarea
export const FieldInput = Input
export const FieldKeyValues = createPassThroughComponent('LessonUiFieldKeyValuesStub')

export const Checkbox = defineComponent({
  name: 'LessonUiCheckboxStub',
  inheritAttrs: false,
  props: {
    modelValue: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    return () => h('input', {
      ...attrs,
      type: 'checkbox',
      checked: props.modelValue,
      onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).checked),
      onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).checked),
    })
  },
})

export const FieldCheckbox = Checkbox

export const Radio = defineComponent({
  name: 'LessonUiRadioStub',
  inheritAttrs: false,
  props: {
    modelValue: {
      type: [String, Number, Boolean],
      default: '',
    },
    value: {
      type: [String, Number, Boolean],
      default: '',
    },
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    return () => h('input', {
      ...attrs,
      type: 'radio',
      checked: props.modelValue === props.value,
      onInput: () => emit('update:modelValue', props.value),
      onChange: () => emit('update:modelValue', props.value),
    })
  },
})

const RangeBase = defineComponent({
  name: 'LessonUiRangeBaseStub',
  inheritAttrs: false,
  props: {
    modelValue: {
      type: [String, Number],
      default: 0,
    },
    min: {
      type: Number,
      default: 0,
    },
    max: {
      type: Number,
      default: 100,
    },
    step: {
      type: Number,
      default: 1,
    },
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    return () => h('input', {
      ...attrs,
      type: 'range',
      min: props.min,
      max: props.max,
      step: props.step,
      value: props.modelValue,
      onInput: (event: Event) => emit('update:modelValue', Number((event.target as HTMLInputElement).value)),
      onChange: (event: Event) => emit('update:modelValue', Number((event.target as HTMLInputElement).value)),
    })
  },
})

export const Range = RangeBase
export const FieldRange = RangeBase
export const RoundRange = RangeBase
export const ColorHueRange = RangeBase
