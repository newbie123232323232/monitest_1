<script setup lang="ts">
import { RouterLink } from "vue-router"
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <p class="brand"><RouterLink to="/login">Moni</RouterLink></p>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 2rem 1rem 3rem;
  box-sizing: border-box;
}

.auth-card {
  width: 100%;
  max-width: 22rem;
  padding: 1.5rem;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-surface) 92%, #fff 8%), var(--color-surface));
  box-shadow: var(--shadow-md);
  text-align: left;
}

.brand {
  margin: 0 0 1.25rem;
  font-weight: 600;
  font-size: 1.25rem;
  letter-spacing: -0.02em;
}
.brand a {
  color: var(--color-text-strong);
  text-decoration: none;
}
.brand a:hover {
  color: var(--color-primary);
}

.auth-card :deep(h1) {
  font-size: 1.35rem;
  margin: 0 0 1rem;
  letter-spacing: normal;
}
</style>
