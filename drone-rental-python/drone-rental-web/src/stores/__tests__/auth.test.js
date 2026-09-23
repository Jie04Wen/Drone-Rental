import {beforeEach, describe, expect, it, vi} from 'vitest'
import {setActivePinia, createPinia} from 'pinia'
import {useAuthStore} from '@/stores/auth'
import {register, logout as logoutApi} from '@/api/auth'

// 屏蔽真实 API 调用
vi.mock('@/api/auth', () => ({
    login: vi.fn(),
    register: vi.fn(),
    adminLogin: vi.fn(),
    getCurrentUser: vi.fn(),
    getAdminInfo: vi.fn(),
    logout: vi.fn()
}))

describe('useAuthStore', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        setActivePinia(createPinia())
    })

    it('注册成功后不应依赖登录凭证，并保持未登录状态', async () => {
        const response = {code: 200, data: null}
        register.mockResolvedValue(response)
        const store = useAuthStore()
        const payload = {nickname: '测试用户', username: 'tester', password: '123456'}

        await expect(store.userRegister(payload)).resolves.toBe(response)

        expect(register).toHaveBeenCalledWith(payload)
        expect(store.isLoggedIn).toBe(false)
        expect(localStorage.getItem('token')).toBeNull()
    })

    it('setToken 应写入 token 与 isAdmin 并持久化', () => {
        const store = useAuthStore()
        store.setToken('abc123', true)

        expect(store.token).toBe('abc123')
        expect(store.isAdmin).toBe(true)
        expect(localStorage.getItem('token')).toBe('abc123')
        expect(localStorage.getItem('isAdmin')).toBe('true')
        expect(store.isLoggedIn).toBe(true)
    })

    it('logout 应调用后端并清空登录状态', async () => {
        logoutApi.mockResolvedValue({
            code: 200,
            data: null
        })

        const store = useAuthStore()
        store.setToken('abc123', false)

        await store.logout()

        expect(logoutApi).toHaveBeenCalledTimes(1)
        expect(store.token).toBe('')
        expect(store.isAdmin).toBe(false)
        expect(store.user).toBeNull()
        expect(localStorage.getItem('token')).toBeNull()
        expect(localStorage.getItem('isAdmin')).toBeNull()
        expect(store.isLoggedIn).toBe(false)
    })

    it('后端退出失败时仍应清空本地登录状态', async () => {
        logoutApi.mockRejectedValue(new Error('Redis unavailable'))

        const store = useAuthStore()
        store.setToken('abc123', true)

        await store.logout()

        expect(logoutApi).toHaveBeenCalledTimes(1)
        expect(store.token).toBe('')
        expect(store.user).toBeNull()
        expect(store.isAdmin).toBe(false)
        expect(localStorage.getItem('token')).toBeNull()
    })

    it('初始化应从 localStorage 恢复 token/isAdmin', () => {
        localStorage.setItem('token', 'restored')
        localStorage.setItem('isAdmin', 'true')
        const store = useAuthStore()

        expect(store.token).toBe('restored')
        expect(store.isAdmin).toBe(true)
    })
})
