<script setup lang="ts">
import { ref } from "vue"
import { RouterLink, useRouter } from "vue-router"
import { logout } from "../api/auth"

const router = useRouter()
const loggingOut = ref(false)
const logoutErr = ref<string | null>(null)

async function handleLogout() {
  logoutErr.value = null
  loggingOut.value = true
  try {
    await logout()
    await router.push({ path: "/login" })
  } catch (e) {
    logoutErr.value = e instanceof Error ? e.message : "Sign out failed"
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <RouterLink class="brand" to="/dashboard">Moni</RouterLink>
      <nav class="app-nav">
        <RouterLink to="/dashboard">Dashboard</RouterLink>
        <RouterLink to="/monitors">Monitors</RouterLink>
      </nav>
      <button type="button" class="signout" @click="handleLogout" :disabled="loggingOut">
        {{ loggingOut ? "…" : "Sign out" }}
      </button>
    </header>
    <p v-if="logoutErr" class="logout-err" role="alert">{{ logoutErr }}</p>
    <main class="app-main">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem 1.5rem;
  padding: 0.75rem 1.25rem;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-surface) 88%, transparent);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0.6rem;
  z-index: 10;
  margin: 0.6rem 0.8rem 0;
  box-shadow: var(--shadow-sm);
}

.brand {
  font-weight: 600;
  font-size: 1.08rem;
  color: var(--color-text-strong);
  text-decoration: none;
  letter-spacing: -0.02em;
}
.brand:hover {
  color: var(--color-primary);
}

.app-nav {
  display: flex;
  gap: 1rem;
  flex: 1;
}

.app-nav a {
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: 0.88rem;
}
.app-nav a.router-link-active {
  color: var(--color-text-strong);
  font-weight: 600;
}
.app-nav a:hover {
  color: var(--color-primary);
}

.signout {
  margin-left: auto;
  padding: 0.35rem 0.75rem;
  font: inherit;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--color-bg-soft);
  color: var(--color-text-strong);
  cursor: pointer;
}
.signout:hover:not(:disabled) {
  border-color: var(--color-border-strong);
}
.signout:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.logout-err {
  margin: 0;
  padding: 0.35rem 1.25rem;
  color: var(--color-danger);
  font-size: 0.9rem;
}

.app-main {
  flex: 1;
  padding: 1.2rem 1.25rem 2rem;
  max-width: 72rem;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.app-main :deep(h1) {
  font-size: 1.7rem;
  letter-spacing: -0.02em;
  margin: 0 0 1.1rem;
}

.app-main :deep(h2) {
  font-size: 1.1rem;
  margin: 0 0 0.5rem;
}
</style>
