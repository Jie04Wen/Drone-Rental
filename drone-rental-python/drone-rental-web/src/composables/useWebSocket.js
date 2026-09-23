import {ref, onUnmounted, watch} from 'vue'
import {useAuthStore} from '@/stores/auth'
import {ElNotification} from 'element-plus'
import {getNotifications, getUnreadCount, markAllNotificationsRead} from '@/api/notification'

/**
 * WebSocket 实时推送 composable。
 *
 * 用法:
 *   const { connected, notifications, unreadCount } = useNotificationWS()
 */
export function useNotificationWS() {
    const authStore = useAuthStore()
    const connected = ref(false)
    const notifications = ref([])
    const unreadCount = ref(0)
    const lastNotification = ref(null)

    let ws = null
    let reconnectTimer = null
    let heartbeatTimer = null
    const RECONNECT_DELAY = 5000
    const HEARTBEAT_INTERVAL = 30000

    function connect() {
        if (!authStore.token || ws) return

        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
        const host = location.host
        const url = `${protocol}//${host}/ws/notifications?token=${authStore.token}`

        ws = new WebSocket(url)

        ws.onopen = () => {
            connected.value = true
            startHeartbeat()
            console.log('[WS] Connected')
        }

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data)

                if (msg.type === 'notification') {
                    handleNotification(msg.data)
                } else if (msg.type === 'broadcast') {
                    handleNotification(msg.data)
                } else if (msg.type === 'pong') {
                    // heartbeat response
                }
            } catch (e) {
                console.warn('[WS] Parse error:', e)
            }
        }

        ws.onclose = () => {
            connected.value = false
            stopHeartbeat()
            ws = null
            console.log('[WS] Disconnected, reconnecting...')
            scheduleReconnect()
        }

        ws.onerror = (err) => {
            console.warn('[WS] Error:', err)
        }
    }

    function disconnect() {
        if (ws) {
            ws.close()
            ws = null
        }
        stopHeartbeat()
        clearTimeout(reconnectTimer)
    }

    function handleNotification(data) {
        lastNotification.value = data
        notifications.value.unshift(data)
        unreadCount.value++

        // 浏览器通知（桌面通知）
        if (Notification.permission === 'granted') {
            new Notification(data.title || '新通知', {
                body: data.content,
                icon: '/favicon.ico',
            })
        }

        // Element Plus 弹窗通知
        ElNotification({
            title: data.title || '新通知',
            message: data.content,
            type: getNotificationType(data.type),
            duration: 5000,
        })
    }

    function getNotificationType(type) {
        const map = {
            payment: 'success',
            order: 'info',
            qualification: 'warning',
            fault: 'error',
            system: 'info',
        }
        return map[type] || 'info'
    }

    function startHeartbeat() {
        heartbeatTimer = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('ping')
            }
        }, HEARTBEAT_INTERVAL)
    }

    function stopHeartbeat() {
        if (heartbeatTimer) {
            clearInterval(heartbeatTimer)
            heartbeatTimer = null
        }
    }

    function scheduleReconnect() {
        clearTimeout(reconnectTimer)
        reconnectTimer = setTimeout(() => {
            if (authStore.token && !connected.value) {
                connect()
            }
        }, RECONNECT_DELAY)
    }

    function markRead() {
        unreadCount.value = 0
        // 同步到后端持久化
        markAllNotificationsRead().catch((e) => {
            console.warn('[WS] markAllRead failed:', e)
        })
    }

    // 从后端加载历史通知与未读数
    async function loadHistory() {
        if (!authStore.token) return
        try {
            const [listRes, countRes] = await Promise.all([
                getNotifications({pageNum: 1, pageSize: 20}),
                getUnreadCount()
            ])
            notifications.value = listRes.data?.records || []
            unreadCount.value = countRes.data || 0
        } catch (e) {
            console.warn('[WS] loadHistory failed:', e)
        }
    }

    // 请求浏览器通知权限
    function requestPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission()
        }
    }

    // 监听 token 变化：登录时连接并加载历史，登出时断开
    watch(
        () => authStore.token,
        (newToken, oldToken) => {
            if (newToken && !oldToken) {
                connect()
                loadHistory()
            } else if (!newToken && oldToken) {
                disconnect()
                notifications.value = []
                unreadCount.value = 0
            }
        }
    )

    // 组件挂载时连接并加载历史（若已登录）
    connect()
    loadHistory()
    requestPermission()

    onUnmounted(() => {
        disconnect()
    })

    return {
        connected,
        notifications,
        unreadCount,
        lastNotification,
        markRead,
        connect,
        disconnect,
    }
}
