<script setup lang="ts">
import { RouterView } from "vue-router"
</script>

<template>
  <div class="app-root">
    <RouterView />
  </div>
</template>

<style scoped>
.app-root {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  width: 100%;
  max-width: 100%;
}
</style>
