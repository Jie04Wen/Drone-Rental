import {defineStore} from 'pinia'
import {ref, computed} from 'vue'
import {login, register, adminLogin, getCurrentUser, getAdminInfo, logout as logoutApi} from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
    // 状态
    const token = ref(localStorage.getItem('token') || '')
    const user = ref(null)
    const isAdmin = ref(localStorage.getItem('isAdmin') === 'true')

    // 计算属性
    const isLoggedIn = computed(() => !!token.value)

    // 用户是否已实名认证
    const isVerified = computed(() => user.value?.status === 1)

    // 用户可以租赁的条件：已登录 + 已实名认证
    const canRent = computed(() => isLoggedIn.value && isVerified.value)

    // 设置token
    const setToken = (newToken, admin = false) => {
        token.value = newToken
        isAdmin.value = admin
        localStorage.setItem('token', newToken)
        localStorage.setItem('isAdmin', String(admin))
    }

    // 设置用户信息
    const setUser = (userInfo) => {
        user.value = userInfo
    }

    // 用户登录
    const userLogin = async (credentials) => {
        const res = await login(credentials)
        const {token: newToken, ...userInfo} = res.data
        setToken(newToken, false)
        setUser(userInfo)
        // 登录成功后获取完整用户信息（包含头像等）
        await fetchUserInfo()
        return res
    }

    // 用户注册
    const userRegister = async (data) => {
        return register(data)
    }

    // 管理员登录
    const adminUserLogin = async (credentials) => {
        const res = await adminLogin(credentials)
        const {token: newToken, ...userInfo} = res.data
        setToken(newToken, true)
        setUser(userInfo)
        // 获取完整用户信息（包含头像等）
        await fetchUserInfo()
        return res
    }

    // 获取当前用户信息
    const fetchUserInfo = async () => {
        if (!token.value) return null

        try {
            const res = await getCurrentUser()
            const info = res.data
            setUser(info)
            const adminFlag = info?.role === 1
            isAdmin.value = adminFlag
            localStorage.setItem('isAdmin', String(adminFlag))
            return user.value
        } catch (error) {
            // 普通接口失败时，若本地标记为管理员则尝试管理端接口
            if (isAdmin.value) {
                try {
                    const adminRes = await getAdminInfo()
                    setUser(adminRes.data)
                    return user.value
                } catch (e) {
                    clearAuth()
                    return null
                }
            }
            clearAuth()
            return null
        }
    }

    // 更新用户信息（本地）
    const updateUserInfo = (newInfo) => {
        if (user.value) {
            user.value = {...user.value, ...newInfo}
        }
    }
    // 清除前端登录状态，不请求后端。
    const clearAuth = () => {
        token.value = ''
        user.value = null
        isAdmin.value = false
        localStorage.removeItem('token')
        localStorage.removeItem('isAdmin')
    }

    // 用户主动退出：先通知后端撤销 JWT，再清除本地状态。
    const logout = async () => {
        try {
            if (token.value) {
                await logoutApi()
            }
        } catch (error) {
            console.warn('服务端退出失败，已执行本地退出:', error)
        } finally {
            clearAuth()
        }
    }

    // 初始化时检查登录状态
    const initAuth = async () => {
        if (token.value) {
            await fetchUserInfo()
        }
    }

    return {
        //状态
        token,
        user,
        isAdmin,

        // 计算属性
        isLoggedIn,
        isVerified,
        canRent,

        // 方法
        setToken,
        setUser,
        userLogin,
        userRegister,
        adminUserLogin,
        fetchUserInfo,
        updateUserInfo,
        clearAuth,
        logout,
        initAuth
    }
}, {
    // 持久化配置（可选，如果需要更复杂的持久化）
    persist: false
})
