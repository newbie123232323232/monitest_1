<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "ghost" | "danger"
    size?: "sm" | "md"
    disabled?: boolean
    fullWidth?: boolean
    type?: "button" | "submit" | "reset"
  }>(),
  {
    variant: "secondary",
    size: "md",
    disabled: false,
    fullWidth: false,
    type: "button",
  },
)
</script>

<template>
  <button
    :type="props.type"
    :disabled="props.disabled"
    class="ui-btn"
    :class="[`v-${props.variant}`, `s-${props.size}`, { full: props.fullWidth }]"
  >
    <slot />
  </button>
</template>

<style scoped>
.ui-btn {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-surface) 90%, #fff 10%);
  color: var(--color-text-strong);
  cursor: pointer;
  transition: all 140ms ease;
  font-weight: 600;
}
.ui-btn.full { width: 100%; }
.ui-btn.s-sm { padding: 0.3rem 0.6rem; font-size: 0.82rem; }
.ui-btn.s-md { padding: 0.45rem 0.8rem; font-size: 0.9rem; }
.ui-btn.v-primary {
  background: linear-gradient(180deg, var(--color-primary), var(--color-primary-hover));
  border-color: color-mix(in srgb, var(--color-primary) 65%, #fff 35%);
  color: #04130b;
}
.ui-btn.v-primary:hover:not(:disabled) { filter: brightness(1.06); }
.ui-btn.v-danger { background: var(--color-danger); border-color: var(--color-danger); color: #fff; }
.ui-btn.v-danger:hover:not(:disabled) { filter: brightness(0.95); }
.ui-btn.v-ghost { background: transparent; color: var(--color-text); }
.ui-btn:hover:not(:disabled) { border-color: var(--color-border-strong); }
.ui-btn:disabled { opacity: 0.55; cursor: not-allowed; }
</style>
