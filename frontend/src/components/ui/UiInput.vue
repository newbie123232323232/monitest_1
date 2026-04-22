<script setup lang="ts">
const model = defineModel<string | number | null>()
withDefaults(
  defineProps<{
    label?: string
    type?: string
    placeholder?: string
    disabled?: boolean
  }>(),
  {
    type: "text",
    placeholder: "",
    disabled: false,
  },
)
</script>

<template>
  <label class="ui-input-wrap">
    <span v-if="label" class="ui-label">{{ label }}</span>
    <input
      v-model="model"
      class="ui-input"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
    />
  </label>
</template>

<style scoped>
.ui-input-wrap { display: flex; flex-direction: column; gap: 0.25rem; }
.ui-label { font-size: 0.8rem; color: var(--color-text-muted); }
.ui-input {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-bg-soft) 90%, #000 10%);
  color: var(--color-text-strong);
  padding: 0.5rem 0.65rem;
}
.ui-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 22%, transparent);
}
</style>
