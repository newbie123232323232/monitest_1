<script setup lang="ts">
import { ref } from "vue"
import { RouterLink, useRoute, useRouter } from "vue-router"
import AuthCard from "../components/AuthCard.vue"
import { login, saveTokens } from "../api/auth"

const route = useRoute()
const router = useRouter()
const email = ref("")
const password = ref("")
const err = ref<string | null>(null)
const loading = ref(false)

const apiBase = import.meta.env.VITE_API_BASE_URL ?? ""

function safeRedirectTarget(): string {
  const r = route.query.redirect
  if (typeof r !== "string" || !r.startsWith("/") || r.startsWith("//")) {
    return "/dashboard"
  }
  return r
}

async function submit() {
  err.value = null
  loading.value = true
  try {
    const t = await login(email.value.trim(), password.value)
    saveTokens(t.access_token, t.refresh_token)
    await router.replace(safeRedirectTarget())
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Login failed"
  } finally {
    loading.value = false
  }
}

function google() {
  const prefix = apiBase.replace(/\/$/, "")
  window.location.href = `${prefix}/api/v1/auth/google`
}
</script>

<template>
  <AuthCard>
    <h1>Sign in</h1>
    <form class="form" @submit.prevent="submit">
      <label>Email <input v-model="email" type="email" required autocomplete="email" /></label>
      <label
        >Password
        <input v-model="password" type="password" required autocomplete="current-password"
      /></label>
      <button type="submit" class="primary" :disabled="loading">{{ loading ? "…" : "Sign in" }}</button>
    </form>
    <p v-if="err" class="err">{{ err }}</p>
    <p><button type="button" class="google" @click="google">Continue with Google</button></p>
    <p class="muted">No account? <RouterLink to="/register">Create one</RouterLink></p>
  </AuthCard>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.9rem;
}
input {
  padding: 0.5rem;
  font: inherit;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg-soft);
  color: var(--color-text-strong);
}
input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 20%, transparent);
}
.primary {
  padding: 0.5rem 0.75rem;
  font: inherit;
  font-weight: 600;
  border: 1px solid color-mix(in srgb, var(--color-primary) 65%, #fff 35%);
  border-radius: 8px;
  background: linear-gradient(180deg, var(--color-primary), var(--color-primary-hover));
  color: #04130b;
  cursor: pointer;
}
.primary:hover:not(:disabled) {
  filter: brightness(1.05);
}
.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.google {
  width: 100%;
  padding: 0.45rem 0.75rem;
  font: inherit;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-bg-soft) 88%, #000 12%);
  color: var(--color-text-strong);
  cursor: pointer;
}
.google:hover {
  border-color: var(--color-border-strong);
}
.err {
  color: var(--color-danger);
  font-size: 0.9rem;
}
.muted {
  margin: 0.5rem 0 0;
  font-size: 0.9rem;
  color: var(--color-text-muted);
}
.muted a {
  color: var(--color-primary);
  font-weight: 500;
}
</style>
