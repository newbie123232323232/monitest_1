import { createRouter, createWebHistory } from "vue-router"
import { getAccessToken } from "../api/auth"
import LoginView from "../views/LoginView.vue"
import RegisterView from "../views/RegisterView.vue"
import VerifyEmailView from "../views/VerifyEmailView.vue"
import AuthCallbackView from "../views/AuthCallbackView.vue"
import DashboardView from "../views/DashboardView.vue"
import MonitorsView from "../views/MonitorsView.vue"
import MonitorDetailView from "../views/MonitorDetailView.vue"

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", redirect: "/dashboard" },
    { path: "/login", name: "login", component: LoginView, meta: { guestOnly: true } },
    { path: "/register", name: "register", component: RegisterView, meta: { guestOnly: true } },
    { path: "/verify-email", name: "verify-email", component: VerifyEmailView },
    { path: "/auth/callback", name: "auth-callback", component: AuthCallbackView },
    { path: "/dashboard", name: "dashboard", component: DashboardView, meta: { requiresAuth: true } },
    { path: "/monitors", name: "monitors", component: MonitorsView, meta: { requiresAuth: true } },
    { path: "/monitors/:id", name: "monitor-detail", component: MonitorDetailView, meta: { requiresAuth: true } },
  ],
})

router.beforeEach((to) => {
  const token = getAccessToken()
  if (to.meta.requiresAuth && !token) {
    return { path: "/login", query: { redirect: to.fullPath } }
  }
  if (to.meta.guestOnly && token) {
    return { path: "/dashboard" }
  }
  return true
})

export default router
