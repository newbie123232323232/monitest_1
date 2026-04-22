<script setup lang="ts">
const props = withDefaults(
  defineProps<{ tone?: "neutral" | "success" | "warning" | "danger" | "info" }>(),
  { tone: "neutral" },
)
</script>

<template>
  <span class="ui-badge" :class="`t-${props.tone}`">
    <slot />
  </span>
</template>

<style scoped>
.ui-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  border-radius: 999px;
  border: 1px solid transparent;
  padding: 0.2rem 0.56rem;
  font-size: 0.75rem;
  font-weight: 600;
}
.ui-badge.t-neutral { background: var(--color-bg-soft); color: var(--color-text); border-color: var(--color-border); }
.ui-badge.t-success { background: color-mix(in srgb, var(--color-success) 15%, transparent); color: var(--color-success); }
.ui-badge.t-warning { background: color-mix(in srgb, var(--color-warning) 18%, transparent); color: var(--color-warning); }
.ui-badge.t-danger { background: color-mix(in srgb, var(--color-danger) 15%, transparent); color: var(--color-danger); }
.ui-badge.t-info { background: color-mix(in srgb, var(--color-info) 15%, transparent); color: var(--color-info); }
</style>
