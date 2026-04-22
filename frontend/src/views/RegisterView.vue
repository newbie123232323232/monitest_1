<script setup lang="ts">
import { ref } from "vue"
import { RouterLink } from "vue-router"
import AuthCard from "../components/AuthCard.vue"
import { register } from "../api/auth"

const email = ref("")
const password = ref("")
const err = ref<string | null>(null)
const ok = ref<string | null>(null)
const loading = ref(false)

async function submit() {
  err.value = null
  ok.value = null
  loading.value = true
  try {
    const r = await register(email.value.trim(), password.value)
    ok.value = r.message
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Register failed"
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthCard>
    <h1>Create account</h1>
    <form class="form" @submit.prevent="submit">
      <label>Email <input v-model="email" type="email" required autocomplete="email" /></label>
      <label
        >Password (min 8)
        <input v-model="password" type="password" required minlength="8" autocomplete="new-password"
      /></label>
      <button type="submit" class="primary" :disabled="loading">{{ loading ? "…" : "Create account" }}</button>
    </form>
    <p v-if="err" class="err">{{ err }}</p>
    <p v-if="ok" class="ok">{{ ok }}</p>
    <p class="muted"><RouterLink to="/login">Back to sign in</RouterLink></p>
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
.err {
  color: var(--color-danger);
  font-size: 0.9rem;
}
.ok {
  color: var(--color-success);
  font-size: 0.9rem;
}
.muted {
  margin: 0.75rem 0 0;
  font-size: 0.9rem;
}
.muted a {
  color: var(--color-primary);
  font-weight: 500;
}
</style>
