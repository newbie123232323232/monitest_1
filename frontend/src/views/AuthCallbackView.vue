<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import AuthCard from "../components/AuthCard.vue"
import { saveTokens } from "../api/auth"

const route = useRoute()
const router = useRouter()
const err = ref<string | null>(null)

onMounted(() => {
  const qErr = route.query.error
  if (typeof qErr === "string") {
    err.value = qErr
    return
  }
  const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : ""
  const params = new URLSearchParams(hash)
  const access = params.get("access_token")
  const refresh = params.get("refresh_token")
  if (access && refresh) {
    saveTokens(access, refresh)
    void router.replace("/dashboard")
    return
  }
  err.value = "Missing tokens in callback URL."
})
</script>

<template>
  <AuthCard>
    <h1>Sign in</h1>
    <p v-if="err" class="err">{{ err }}</p>
    <p v-else class="muted">Finishing sign-in…</p>
  </AuthCard>
</template>

<style scoped>
.err {
  color: var(--color-danger);
  font-size: 0.95rem;
}
.muted {
  color: var(--color-text-muted);
  font-size: 0.95rem;
}
</style>
