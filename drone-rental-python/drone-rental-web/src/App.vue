<template>
  <router-view/>
</template>

<script setup>
import {onMounted, provide} from 'vue'
import {useAuthStore} from '@/stores/auth'
import {useNotificationWS} from '@/composables/useWebSocket'

const authStore = useAuthStore()

// WebSocket 实时通知
const {connected, notifications, unreadCount, lastNotification, markRead} = useNotificationWS()

// 提供给子组件使用
provide('notifications', {connected, notifications, unreadCount, lastNotification, markRead})

// 初始化认证状态
onMounted(async () => {
  await authStore.initAuth()
})
</script>

<style lang="scss">
// 全局样式已在main.js中引入
</style>
