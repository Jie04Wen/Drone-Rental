import {defineStore} from 'pinia'
import {reactive, ref} from 'vue'
import {aiApi} from '@/api/ai'
import {parseSseEvents} from '@/utils/sse'

const SESSION_STORAGE_KEY = 'ai_active_session_id'
const DEFAULT_VISION_MESSAGE = '请识别照片中的无人机型号并给出租赁建议'

function truncateTitle(text) {
    if (!text) {
        return '新对话'
    }

    return text.length > 30
        ? `${text.slice(0, 30)}...`
        : text
}

function isAbortError(error) {
    return (
        error?.name === 'AbortError' ||
        error?.message?.includes('aborted') ||
        error?.message?.includes('abort')
    )
}

function resolveAttachment(message) {
    if (message?.attachment) {
        return message.attachment
    }

    if (Array.isArray(message?.attachments)) {
        return message.attachments.find(
            attachment => attachment?.type === 'image'
        )
    }

    return null
}

function attachmentExpired(attachment) {
    if (!attachment) {
        return false
    }

    if (attachment.expired === true) {
        return true
    }

    if (!attachment.expiresAt) {
        return false
    }

    const expiresAt = new Date(attachment.expiresAt).getTime()

    return (
        Number.isFinite(expiresAt) &&
        expiresAt <= Date.now()
    )
}

function attachmentUnavailable(attachment) {
    return attachment?.available === false
}

function normalizeHistoryMessage(message) {
    const attachment = resolveAttachment(message)
    const expired = attachmentExpired(attachment)
    const unavailable = attachmentUnavailable(attachment)

    return {
        ...message,
        streaming: false,
        imageUrl: expired
            ? ''
            : (
                message.imageUrl ||
                attachment?.url ||
                ''
            ),
        imageExpired: (
            Boolean(message.imageExpired) ||
            expired ||
            unavailable
        ),
        imageExpiresAt: (
            message.imageExpiresAt ||
            attachment?.expiresAt ||
            null
        ),
    }
}

function normalizeSendPayload(payload) {
    if (typeof payload === 'string') {
        return {
            text: payload.trim(),
            image: null,
        }
    }

    return {
        text: payload?.text?.trim() || '',
        image: payload?.image || null,
    }
}

export const useAiStore = defineStore('ai', () => {
    const sessionId = ref('')
    const messages = ref([])
    const loading = ref(false)
    const streaming = ref(false)
    const sessions = ref([])

    let currentStreamCancel = null
    let currentVisionCancel = null

    function persistSessionId(sid) {
        if (sid) {
            sessionStorage.setItem(
                SESSION_STORAGE_KEY,
                sid
            )
        } else {
            sessionStorage.removeItem(
                SESSION_STORAGE_KEY
            )
        }
    }

    function releaseLocalPreview(message) {
        const imageUrl = message?.imageUrl

        if (
            typeof imageUrl === 'string' &&
            imageUrl.startsWith('blob:')
        ) {
            URL.revokeObjectURL(imageUrl)
        }
    }

    function releaseAllLocalPreviews() {
        messages.value.forEach(releaseLocalPreview)
    }

    function replaceMessages(nextMessages) {
        releaseAllLocalPreviews()
        messages.value = nextMessages
    }

    async function initSession() {
        cancelStream()
        releaseAllLocalPreviews()

        try {
            const response = await aiApi.createSession(
                '新对话'
            )
            const data = response?.data

            if (data?.id) {
                sessionId.value = data.id
                messages.value = []
                persistSessionId(sessionId.value)

                const exists = sessions.value.some(
                    session => session.id === data.id
                )

                if (!exists) {
                    sessions.value = [
                        {
                            id: data.id,
                            title: data.title || '新对话',
                            createdTime: data.createdTime,
                            messageCount: 0,
                        },
                        ...sessions.value,
                    ].slice(0, 20)
                }

                return
            }
        } catch (error) {
            console.warn(
                'createSession failed, fallback to local UUID:',
                error
            )
        }

        sessionId.value = crypto
            .randomUUID()
            .replace(/-/g, '')
        messages.value = []
        persistSessionId(sessionId.value)
    }

    function addMessage(message) {
        messages.value.push(reactive(message))
        return messages.value.length - 1
    }

    function triggerMessagesUpdate() {
        messages.value = [...messages.value]
    }

    function updateMessage(index, changes) {
        if (!messages.value[index]) {
            return
        }

        Object.assign(messages.value[index], changes)
        triggerMessagesUpdate()
    }

    /**
     * 根据消息是否包含图片选择调用路径：
     * - 纯文本：SSE 文本对话
     * - 带图片：视觉识别接口
     */
    async function sendMessage(payload) {
        if (loading.value) {
            return
        }

        const {text, image} = normalizeSendPayload(payload)

        if (!text && !image) {
            return
        }

        if (!sessionId.value) {
            await initSession()
        }

        if (image) {
            await sendVisionMessage(text, image)
            return
        }

        await sendTextMessage(text)
    }

    async function sendTextMessage(content) {
        addMessage({
            role: 'user',
            content,
            createdTime: new Date().toISOString(),
        })

        const assistantIndex = addMessage({
            role: 'assistant',
            content: '',
            streaming: true,
            createdTime: new Date().toISOString(),
        })

        loading.value = true
        streaming.value = false

        try {
            await streamWithFallback(
                content,
                assistantIndex
            )
        } finally {
            updateMessage(assistantIndex, {
                streaming: false,
            })

            loading.value = false
            streaming.value = false
            currentStreamCancel = null

            upsertCurrentSession(content)
            scrollToBottom()
        }
    }

    async function sendVisionMessage(text, image) {
        const prompt = text || DEFAULT_VISION_MESSAGE
        const localImageUrl = URL.createObjectURL(image)

        const userIndex = addMessage({
            role: 'user',
            content: text,
            imageUrl: localImageUrl,
            imageExpired: false,
            createdTime: new Date().toISOString(),
        })

        const assistantIndex = addMessage({
            role: 'assistant',
            content: '',
            streaming: false,
            createdTime: new Date().toISOString(),
        })

        loading.value = true
        streaming.value = false
        scrollToBottom()

        try {
            /*
             * 推荐的 visionChat 返回结构：
             *
             * {
             *   request: Promise,
             *   cancel: Function
             * }
             *
             * 同时兼容当前直接返回 Promise 的实现。
             */
            const operation = aiApi.visionChat(
                prompt,
                sessionId.value,
                image
            )

            let response

            if (
                operation &&
                typeof operation === 'object' &&
                'request' in operation
            ) {
                currentVisionCancel = operation.cancel
                response = await operation.request
            } else {
                response = await operation
            }

            const data = response?.data || response
            const attachment = data?.attachment || null

            if (data?.sessionId) {
                sessionId.value = data.sessionId
                persistSessionId(data.sessionId)
            }

            if (attachment?.url) {
                releaseLocalPreview(
                    messages.value[userIndex]
                )

                updateMessage(userIndex, {
                    imageUrl: attachment.url,
                    imageExpiresAt:
                        attachment.expiresAt || null,
                    imageExpired: false,
                    attachment,
                })
            }

            updateMessage(assistantIndex, {
                content: (
                    data?.content ||
                    '图片识别完成，但服务没有返回文字结果。'
                ),
                model: data?.model || '',
                recognition: data?.recognition || null,
                createdTime: (
                    data?.createdTime ||
                    new Date().toISOString()
                ),
            })
        } catch (error) {
            if (isAbortError(error)) {
                updateMessage(assistantIndex, {
                    content: '已停止本次图片识别。',
                })
            } else {
                console.error(
                    'Vision chat failed:',
                    error
                )

                updateMessage(assistantIndex, {
                    content: (
                        error?.message ||
                        '图片识别失败，请稍后重试。'
                    ),
                })
            }
        } finally {
            currentVisionCancel = null
            loading.value = false
            streaming.value = false

            upsertCurrentSession(prompt)
            scrollToBottom()
        }
    }

    /**
     * SSE 文本请求失败时降级到普通 POST。
     * 用户主动取消的请求不会降级。
     */
    async function streamWithFallback(
        content,
        assistantIndex
    ) {
        try {
            const {reader, cancel} = aiApi.streamChat(
                content,
                sessionId.value
            )

            currentStreamCancel = cancel

            const stream = await reader
            const decoder = new TextDecoder()

            let buffer = ''
            let fullContent = ''

            streaming.value = true

            while (true) {
                const {done, value} = await stream.read()

                if (done) {
                    break
                }

                buffer += decoder.decode(
                    value,
                    {stream: true}
                )

                const parsed = parseSseEvents(buffer)
                buffer = parsed.remaining

                for (const chunk of parsed.chunks) {
                    fullContent += chunk

                    updateMessage(assistantIndex, {
                        content: fullContent,
                    })

                    scrollToBottom()
                }

                if (parsed.done) {
                    break
                }
            }

            /*
             * 处理 TextDecoder 中尚未输出的尾部字符。
             */
            buffer += decoder.decode()

            if (buffer) {
                const parsed = parseSseEvents(buffer)

                for (const chunk of parsed.chunks) {
                    fullContent += chunk

                    updateMessage(assistantIndex, {
                        content: fullContent,
                    })
                }
            }
        } catch (error) {
            streaming.value = false
            currentStreamCancel = null

            if (isAbortError(error)) {
                updateMessage(assistantIndex, {
                    content: '已停止生成。',
                })
                return
            }

            console.warn(
                'SSE failed, falling back to POST:',
                error?.message
            )

            try {
                const response = await aiApi.chat(
                    content,
                    sessionId.value
                )

                updateMessage(assistantIndex, {
                    content: (
                        response?.data?.content ||
                        '服务没有返回内容。'
                    ),
                    model: response?.data?.model || '',
                })
            } catch (postError) {
                console.error(
                    'POST chat failed:',
                    postError
                )

                updateMessage(assistantIndex, {
                    content: (
                        postError?.message ||
                        '抱歉，请求失败，请稍后重试。'
                    ),
                })
            }
        } finally {
            currentStreamCancel = null
            streaming.value = false
        }
    }

    function upsertCurrentSession(userMessage) {
        const sid = sessionId.value

        if (!sid) {
            return
        }

        const messageCount = messages.value.filter(
            message => message.role === 'user'
        ).length

        const index = sessions.value.findIndex(
            session => session.id === sid
        )

        const isNew = index < 0
        const currentTitle = isNew
            ? ''
            : sessions.value[index].title

        const shouldGenerateTitle = (
            isNew ||
            (
                messageCount === 1 &&
                (
                    currentTitle === '新会话' ||
                    currentTitle === '新对话'
                )
            )
        )

        const entry = {
            id: sid,
            title: shouldGenerateTitle
                ? truncateTitle(userMessage)
                : currentTitle,
            createdTime: isNew
                ? new Date().toISOString()
                : sessions.value[index].createdTime,
            messageCount,
        }

        if (isNew) {
            sessions.value = [
                entry,
                ...sessions.value,
            ].slice(0, 20)

            return
        }

        const nextSessions = [...sessions.value]
        nextSessions.splice(index, 1)

        sessions.value = [
            {
                ...sessions.value[index],
                ...entry,
            },
            ...nextSessions,
        ]
    }

    function scrollToBottom() {
        if (typeof document === 'undefined') {
            return
        }

        const element = document.querySelector(
            '.chat-window__messages'
        )

        if (!element) {
            return
        }

        requestAnimationFrame(() => {
            element.scrollTop = element.scrollHeight
        })
    }

    function cancelStream() {
        if (currentStreamCancel) {
            try {
                currentStreamCancel()
            } catch {
                // 请求可能已经结束。
            }

            currentStreamCancel = null
        }

        if (currentVisionCancel) {
            try {
                currentVisionCancel()
            } catch {
                // 请求可能已经结束。
            }

            currentVisionCancel = null
        }

        loading.value = false
        streaming.value = false
    }

    async function loadSessions() {
        try {
            const response = await aiApi.getSessions()
            const seen = new Set()

            sessions.value = (response.data || [])
                .filter(session => {
                    if (!session.id) {
                        return false
                    }

                    if (seen.has(session.id)) {
                        return false
                    }

                    seen.add(session.id)
                    return true
                })
                .map(session => ({
                    ...session,
                    title: (
                        session.title?.trim() ||
                        '新对话'
                    ),
                }))
        } catch (error) {
            console.error(
                'Load sessions failed:',
                error
            )
        }
    }

    async function restoreOnMount() {
        await loadSessions()

        const savedSessionId = sessionStorage.getItem(
            SESSION_STORAGE_KEY
        )

        const targetSessionId = (
            savedSessionId &&
            sessions.value.some(
                session => session.id === savedSessionId
            )
        )
            ? savedSessionId
            : sessions.value[0]?.id

        if (targetSessionId) {
            await switchSession(targetSessionId)
        }
    }

    async function switchSession(sid) {
        if (!sid) {
            return
        }

        cancelStream()
        sessionId.value = sid
        persistSessionId(sid)

        try {
            const response =
                await aiApi.getSessionHistory(sid)

            replaceMessages(
                (response.data || []).map(
                    normalizeHistoryMessage
                )
            )

            scrollToBottom()
        } catch (error) {
            console.error(
                'Load session history failed:',
                error
            )

            replaceMessages([])
        }
    }

    async function renameSession(sid, title) {
        try {
            const response = await aiApi.renameSession(
                sid,
                title
            )

            if (response?.code !== 200) {
                return
            }

            const index = sessions.value.findIndex(
                session => session.id === sid
            )

            if (index < 0) {
                return
            }

            const updated = [...sessions.value]

            updated[index] = {
                ...updated[index],
                title,
            }

            sessions.value = updated
        } catch (error) {
            console.error(
                'Rename session failed:',
                error
            )
        }
    }

    async function deleteSession(sid) {
        try {
            await aiApi.deleteSession(sid)

            sessions.value = sessions.value.filter(
                session => session.id !== sid
            )

            if (sessionId.value === sid) {
                cancelStream()
                releaseAllLocalPreviews()

                sessionId.value = ''
                messages.value = []
                persistSessionId('')
            }
        } catch (error) {
            console.error(
                'Delete session failed:',
                error
            )
        }
    }

    async function loadHistory(sid) {
        if (!sid) {
            return
        }

        cancelStream()
        sessionId.value = sid
        persistSessionId(sid)

        try {
            const response = await aiApi.getHistory(sid)

            replaceMessages(
                (response.data || []).map(
                    normalizeHistoryMessage
                )
            )

            scrollToBottom()
        } catch (error) {
            console.error(
                'Load history failed:',
                error
            )

            replaceMessages([])
        }
    }

    async function clearChat() {
        cancelStream()
        await initSession()
    }

    return {
        sessionId,
        messages,
        loading,
        streaming,
        sessions,

        initSession,
        sendMessage,
        loadHistory,
        clearChat,
        cancelStream,
        loadSessions,
        restoreOnMount,
        switchSession,
        renameSession,
        deleteSession,
    }
})
