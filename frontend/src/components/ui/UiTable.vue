<template>
  <div class="ui-table-wrap">
    <table class="ui-table">
      <slot />
    </table>
  </div>
</template>

<style scoped>
.ui-table-wrap {
  width: 100%;
  overflow: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-surface) 94%, #fff 6%);
}
.ui-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
.ui-table :deep(th),
.ui-table :deep(td) {
  text-align: left;
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}
.ui-table :deep(th) {
  color: var(--color-text-strong);
  background: color-mix(in srgb, var(--color-bg-soft) 86%, #000 14%);
  font-weight: 600;
}
</style>
