import {get, post, put, del} from './request'
import {useAuthStore} from '@/stores/auth'

export const aiApi = {
    // 普通非流式文本对话
    chat(message, sessionId) {
        return post('/ai/chat', {message, sessionId})
    },

    // SSE流式文本对话
    streamChat(message, sessionId) {
        const authStore = useAuthStore()
        const ctrl = new AbortController()
        const base = import.meta.env.VITE_API_BASE_URL || '/api'
        const url = `${base}/ai/chat/stream`
        const body = JSON.stringify({message, sessionId})

        const headers = {'Content-Type': 'application/json'}
        if (authStore.token) {
            headers['Authorization'] = `Bearer ${authStore.token}`
        }

        const fetchPromise = fetch(url, {
            method: 'POST',
            headers,
            body,
            signal: ctrl.signal,
        }).then(async (res) => {
            if (!res.ok) {
                const errText = await res.text().catch(() => '')
                throw new Error(`SSE 请求失败 (${res.status}): ${errText}`)
            }
            if (!res.body) throw new Error('SSE 响应体为空')
            return res.body.getReader()
        })

        return {
            reader: fetchPromise,
            cancel: () => ctrl.abort(),
        }
    },

    // 图片视觉识别对话
    visionChat(message, sessionId, image) {
        const authStore = useAuthStore()
        const controller = new AbortController()
        const base = import.meta.env.VITE_API_BASE_URL || '/api'
        const formData = new FormData()
        formData.append(
            'message',
            message || '请识别照片中的无人机型号并给出租赁建议'
        )
        if (sessionId) {
            formData.append('sessionId', sessionId)
        }
        formData.append('image', image)
        const headers = {}
        if (authStore.token) {
            headers.Authorization = `Bearer ${authStore.token}`
        }
        const request = fetch(`${base}/ai/chat/vision`, {
            method: 'POST',
            headers,
            body: formData,
            signal: controller.signal,
        }).then(async response => {
            const payload = await response
                .json()
                .catch(() => null)

            if (
                !response.ok ||
                payload?.code !== 200
            ) {
                throw new Error(
                    payload?.message ||
                    `图片识别失败 (${response.status})`
                )
            }
            return payload
        })
        return {
            request,
            cancel: () => controller.abort(),
        }
    },

    getHistory(sessionId) {
        return get('/ai/history', {sessionId})
    },

    //会话管理

    getSessions() {
        return get('/ai/sessions')
    },

    createSession(title = '新会话') {
        return post('/ai/sessions', {title})
    },

    renameSession(sessionId, title) {
        return put(`/ai/sessions/${sessionId}`, {title})
    },

    deleteSession(sessionId) {
        return del(`/ai/sessions/${sessionId}`)
    },

    getSessionHistory(sessionId) {
        return get(`/ai/sessions/${sessionId}/history`)
    },

    //记忆管理

    getMemories() {
        return get('/ai/memory/list')
    },

    saveMemory(data) {
        return post('/ai/memory/save', data)
    },

    deleteMemory(id) {
        return del(`/ai/memory/${id}`)
    },

    getToolLogs(params) {
        return get('/ai/tool/logs', {
            sessionId: params?.sessionId,
            pageNum: params?.page || params?.pageNum || 1,
            pageSize: params?.pageSize || 10
        })
    }
}
