<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRoute, RouterLink } from "vue-router"
import AuthCard from "../components/AuthCard.vue"
import { verifyEmailToken } from "../api/auth"

const route = useRoute()
const err = ref<string | null>(null)
const ok = ref<string | null>(null)
const busy = ref(false)

onMounted(async () => {
  const v = route.query.verified
  if (v === "1") {
    ok.value = "Email verified. You can sign in."
    return
  }
  if (v === "0") {
    err.value = "Verification failed or link expired."
    return
  }
  const token = route.query.token
  if (typeof token !== "string" || !token) return
  busy.value = true
  try {
    const r = await verifyEmailToken(token)
    ok.value = r.message
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Verification failed"
  } finally {
    busy.value = false
  }
})
</script>

<template>
  <AuthCard>
    <h1>Email verification</h1>
    <p v-if="busy">Verifying…</p>
    <p v-else-if="err" class="err">{{ err }}</p>
    <p v-else-if="ok" class="ok">{{ ok }}</p>
    <p v-else class="hint">Open the link from your email (it includes a verification token).</p>
    <p class="muted"><RouterLink to="/login">Sign in</RouterLink></p>
  </AuthCard>
</template>

<style scoped>
.err {
  color: var(--color-danger);
  font-size: 0.95rem;
}
.ok {
  color: var(--color-success);
  font-size: 0.95rem;
}
.hint {
  color: var(--color-text);
  font-size: 0.95rem;
}
.muted {
  margin-top: 1rem;
  font-size: 0.9rem;
}
.muted a {
  color: var(--color-primary);
  font-weight: 500;
}
</style>
