<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <header class="ui-panel-header">
    <div>
      <h3>{{ title }}</h3>
      <p v-if="subtitle">{{ subtitle }}</p>
    </div>
    <div class="actions">
      <slot />
    </div>
  </header>
</template>

<style scoped>
.ui-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
h3 {
  margin: 0;
  font-size: 1rem;
  color: var(--color-text-strong);
}
p {
  margin: 0.15rem 0 0;
  font-size: 0.82rem;
  color: var(--color-text-muted);
}
.actions {
  display: inline-flex;
  gap: var(--space-2);
  align-items: center;
}
</style>
