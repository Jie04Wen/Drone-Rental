import {beforeEach, describe, expect, it, vi} from 'vitest'
import {setActivePinia, createPinia} from 'pinia'

// Mock ai API — must be before store import
const mockAiApi = {
    createSession: vi.fn().mockResolvedValue({data: {id: 'sess-123', title: '新对话'}}),
    getSessions: vi.fn().mockResolvedValue({data: []}),
    getSessionHistory: vi.fn().mockResolvedValue({data: []}),
    getHistory: vi.fn().mockResolvedValue({data: []}),
    renameSession: vi.fn().mockResolvedValue({code: 200}),
    deleteSession: vi.fn().mockResolvedValue({}),
    chat: vi.fn().mockResolvedValue({data: {content: 'AI 回复'}}),
    streamChat: vi.fn(),
    visionChat: vi.fn()
}

vi.mock('@/api/ai', () => ({
    aiApi: mockAiApi
}))

// Mock scroll
Object.defineProperty(document, 'querySelector', {value: () => null, writable: true})

const {useAiStore} = await import('@/stores/ai')

describe('useAiStore', () => {
    beforeEach(() => {
        sessionStorage.clear()
        vi.clearAllMocks()
        setActivePinia(createPinia())
        mockAiApi.createSession.mockResolvedValue({data: {id: 'sess-123', title: '新对话'}})
        mockAiApi.getSessions.mockResolvedValue({data: []})
        mockAiApi.getSessionHistory.mockResolvedValue({data: []})
        mockAiApi.deleteSession.mockResolvedValue({})
        mockAiApi.renameSession.mockResolvedValue({code: 200})
    })

    describe('initSession', () => {
        it('应调用 createSession 并设置 sessionId', async () => {
            const store = useAiStore()
            await store.initSession()

            expect(store.sessionId).toBe('sess-123')
            expect(sessionStorage.getItem('ai_active_session_id')).toBe('sess-123')
            expect(mockAiApi.createSession).toHaveBeenCalledWith('新对话')
        })

        it('createSession 失败时应 fallback 到本地 UUID', async () => {
            mockAiApi.createSession.mockRejectedValue(new Error('network'))

            const store = useAiStore()
            await store.initSession()

            expect(store.sessionId).toMatch(/^[a-f0-9]{32}$/)
            expect(store.messages).toEqual([])
        })

        it('多次 initSession 应复用同一 sessionId', async () => {
            const store = useAiStore()
            await store.initSession()
            const firstId = store.sessionId

            await store.initSession()

            expect(store.sessionId).toBe(firstId)
            expect(mockAiApi.createSession).toHaveBeenCalledTimes(2)
        })
    })

    describe('sendMessage', () => {
        it('renders content when content and DONE arrive together', async () => {
            const encoder = new TextEncoder()
            const read = vi
                .fn()
                .mockResolvedValueOnce({
                    done: false,
                    value: encoder.encode(
                        'data:### Rental price\ndata:Total: 5897.00 CNY\n\ndata:[DONE]\n\n'
                    )
                })
                .mockResolvedValueOnce({done: true, value: undefined})
            mockAiApi.streamChat.mockReturnValue({
                reader: Promise.resolve({read}),
                cancel: vi.fn()
            })

            const store = useAiStore()
            await store.initSession()
            await store.sendMessage('Rent DJI Mavic 3 for three days')

            expect(store.messages[1].content).toBe(
                '### Rental price\nTotal: 5897.00 CNY'
            )
            expect(mockAiApi.chat).not.toHaveBeenCalled()
        })

        it('应添加用户消息和助手占位消息', async () => {
            mockAiApi.streamChat.mockReturnValue({
                reader: Promise.resolve({
                    read: vi.fn().mockResolvedValue({done: true, value: undefined})
                }),
                cancel: vi.fn()
            })

            const store = useAiStore()
            await store.initSession()
            await store.sendMessage('你好')

            expect(store.messages.length).toBeGreaterThanOrEqual(2)
            expect(store.messages[0].role).toBe('user')
            expect(store.messages[0].content).toBe('你好')
            expect(store.messages[1].role).toBe('assistant')
            expect(store.sessions[0].title).toBe('你好')
        })

        it('SSE 失败时应降级到 POST', async () => {
            mockAiApi.streamChat.mockImplementation(() => {
                throw new Error('SSE not available')
            })

            const store = useAiStore()
            await store.initSession()
            await store.sendMessage('测试')

            expect(mockAiApi.chat).toHaveBeenCalled()
            expect(store.messages.length).toBeGreaterThanOrEqual(2)
        })
    })

    describe('sessions 管理', () => {
        it('loadSessions 应保留有消息的占位标题会话并过滤重复项', async () => {
            mockAiApi.getSessions.mockResolvedValue({
                data: [
                    {id: 's1', title: '对话1'},
                    {id: 's2', title: '新会话'},
                    {id: 's3', title: '对话3'},
                    {id: 's1', title: '重复'}
                ]
            })

            const store = useAiStore()
            await store.loadSessions()

            expect(store.sessions).toHaveLength(3)
            expect(store.sessions[0].id).toBe('s1')
            expect(store.sessions[1].id).toBe('s2')
            expect(store.sessions[2].id).toBe('s3')
        })

        it('restoreOnMount 应恢复保存的活动会话', async () => {
            sessionStorage.setItem('ai_active_session_id', 's2')
            mockAiApi.getSessions.mockResolvedValue({
                data: [
                    {id: 's1', title: '对话1'},
                    {id: 's2', title: '对话2'}
                ]
            })
            mockAiApi.getSessionHistory.mockResolvedValue({
                data: [{role: 'user', content: '历史问题'}]
            })

            const store = useAiStore()
            await store.restoreOnMount()

            expect(store.sessionId).toBe('s2')
            expect(store.messages[0].content).toBe('历史问题')
            expect(mockAiApi.getSessionHistory).toHaveBeenCalledWith('s2')
        })

        it('restoreOnMount 没有保存会话时应打开最近会话', async () => {
            mockAiApi.getSessions.mockResolvedValue({
                data: [
                    {id: 'latest', title: '最近会话'},
                    {id: 'older', title: '较早会话'}
                ]
            })

            const store = useAiStore()
            await store.restoreOnMount()

            expect(store.sessionId).toBe('latest')
            expect(mockAiApi.getSessionHistory).toHaveBeenCalledWith('latest')
        })

        it('deleteSession 应从列表移除并清空当前会话', async () => {
            const store = useAiStore()
            await store.initSession()
            store.sessionId = 's1'

            await store.deleteSession('s1')

            expect(store.sessionId).toBe('')
            expect(store.messages).toEqual([])
        })

        it('deleteSession 非当前会话不应清空消息', async () => {
            const store = useAiStore()
            await store.initSession()
            store.sessionId = 'current'
            store.messages = [{role: 'user', content: 'test'}]

            await store.deleteSession('other')

            expect(store.sessionId).toBe('current')
            expect(store.messages).toHaveLength(1)
        })

        it('renameSession 应更新本地会话标题', async () => {
            const store = useAiStore()
            await store.initSession()
            store.sessions = [{id: 's1', title: '旧标题'}]

            await store.renameSession('s1', '新标题')

            expect(store.sessions[0].title).toBe('新标题')
        })

        it('renameSession API 失败不应影响本地状态', async () => {
            mockAiApi.renameSession.mockRejectedValue(new Error('fail'))

            const store = useAiStore()
            store.sessions = [{id: 's1', title: '旧标题'}]

            await store.renameSession('s1', '新标题')

            expect(store.sessions[0].title).toBe('旧标题')
        })
    })

    describe('switchSession', () => {
        it('应加载会话历史并设置 sessionId', async () => {
            mockAiApi.getSessionHistory.mockResolvedValue({
                data: [
                    {role: 'user', content: '问题1'},
                    {role: 'assistant', content: '回答1'}
                ]
            })

            const store = useAiStore()
            await store.switchSession('s1')

            expect(store.sessionId).toBe('s1')
            expect(store.messages).toHaveLength(2)
            expect(store.messages[0].content).toBe('问题1')
            expect(store.messages[1].streaming).toBe(false)
        })

        it('加载失败时应清空消息', async () => {
            mockAiApi.getSessionHistory.mockRejectedValue(new Error('fail'))

            const store = useAiStore()
            await store.switchSession('s1')

            expect(store.messages).toEqual([])
        })

        it('刷新恢复会话时应恢复未过期的历史图片', async () => {
            mockAiApi.getSessionHistory.mockResolvedValue({
                data: [{
                    role: 'user',
                    content: '这是什么无人机？',
                    attachments: [{
                        id: 1,
                        type: 'image',
                        url: '/uploads/users/1/ai-temp/test.jpg',
                        expiresAt: '2099-01-01T00:00:00',
                        expired: false,
                        available: true
                    }]
                }]
            })

            const store = useAiStore()
            await store.switchSession('s1')

            expect(store.messages[0].imageUrl).toBe(
                '/uploads/users/1/ai-temp/test.jpg'
            )
            expect(store.messages[0].imageExpired).toBe(false)
        })

        it('刷新恢复会话时应把过期图片标记为不可用', async () => {
            mockAiApi.getSessionHistory.mockResolvedValue({
                data: [{
                    role: 'user',
                    content: '识别照片',
                    attachments: [{
                        id: 1,
                        type: 'image',
                        url: null,
                        expiresAt: '2020-01-01T00:00:00',
                        expired: true,
                        available: false
                    }]
                }]
            })

            const store = useAiStore()
            await store.switchSession('s1')

            expect(store.messages[0].imageUrl).toBe('')
            expect(store.messages[0].imageExpired).toBe(true)
        })
    })

    describe('cancelStream', () => {
        it('cancelStream 无活跃流不应报错', async () => {
            const store = useAiStore()
            await store.initSession()

            expect(() => store.cancelStream()).not.toThrow()
        })
    })

    describe('clearChat', () => {
        it('应重置会话并创建新会话', async () => {
            const store = useAiStore()
            await store.initSession()
            store.messages = [{role: 'user', content: 'old'}]

            await store.clearChat()

            expect(store.messages).toEqual([])
            expect(store.sessionId).toBeTruthy()
        })
    })
})
