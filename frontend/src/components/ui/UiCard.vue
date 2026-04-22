<script setup lang="ts">
defineProps<{ compact?: boolean }>()
</script>

<template>
  <section class="ui-card" :class="{ compact }">
    <slot />
  </section>
</template>

<style scoped>
.ui-card {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-surface) 92%, #fff 8%), var(--color-surface));
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  box-shadow: var(--shadow-sm);
}
.ui-card.compact { padding: var(--space-3); }
</style>
