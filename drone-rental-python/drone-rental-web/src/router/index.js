import {createRouter, createWebHistory} from 'vue-router'
import {useAuthStore} from '@/stores/auth'
import {ElMessage} from 'element-plus'

// 路由配置
const routes = [
    // ============ 用户端路由 ============
    {
        path: '/',
        component: () => import('@/layouts/UserLayout.vue'),
        children: [
            {
                path: '',
                name: 'Home',
                component: () => import('@/views/user/Home.vue'),
                meta: {title: '首页'}
            },
            {
                path: 'drones',
                name: 'DroneList',
                component: () => import('@/views/user/DroneList.vue'),
                meta: {title: '设备浏览'}
            },
            {
                path: 'drones/:id',
                name: 'DroneDetail',
                component: () => import('@/views/user/DroneDetail.vue'),
                meta: {title: '设备详情'}
            },
            {
                path: 'orders',
                name: 'MyOrders',
                component: () => import('@/views/user/MyOrders.vue'),
                meta: {title: '我的订单', requireAuth: true}
            },
            {
                path: 'orders/:id',
                name: 'OrderDetail',
                component: () => import('@/views/user/OrderDetail.vue'),
                meta: {title: '订单详情', requireAuth: true}
            },
            {
                path: 'orders/:id/pay',
                name: 'OrderPay',
                component: () => import('@/views/user/OrderPay.vue'),
                meta: {title: '订单支付', requireAuth: true}
            },
            {
                path: 'profile',
                name: 'Profile',
                component: () => import('@/views/user/Profile.vue'),
                meta: {title: '个人中心', requireAuth: true}
            },
            {
                path: 'fault-report',
                name: 'FaultReport',
                component: () => import('@/views/user/FaultReport.vue'),
                meta: {title: '故障报修', requireAuth: true}
            },
            {
                path: 'ai-assistant',
                name: 'AiAssistant',
                component: () => import('@/views/user/AiAssistant.vue'),
                meta: {title: 'AI智能助手', requireAuth: true}
            },
            {
                path: 'ai-memory',
                name: 'AiMemory',
                component: () => import('@/views/user/AiMemory.vue'),
                meta: {title: 'AI记忆管理', requireAuth: true}
            },
            {
                path: 'rental-guide',
                name: 'RentalGuide',
                component: () => import('@/views/user/RentalGuide.vue'),
                meta: {title: '租赁指南'}
            },
            {
                path: 'faq',
                name: 'Faq',
                component: () => import('@/views/user/Faq.vue'),
                meta: {title: '常见问题'}
            },
            {
                path: 'contact',
                name: 'ContactUs',
                component: () => import('@/views/user/ContactUs.vue'),
                meta: {title: '联系我们'}
            }
        ]
    },

    // ============ 登录注册 ============
    {
        path: '/login',
        name: 'Login',
        component: () => import('@/views/auth/Login.vue'),
        meta: {title: '登录', guest: true}
    },
    {
        path: '/register',
        name: 'Register',
        component: () => import('@/views/auth/Register.vue'),
        meta: {title: '注册', guest: true}
    },
    {
        path: '/admin/login',
        name: 'AdminLogin',
        component: () => import('@/views/auth/AdminLogin.vue'),
        meta: {title: '管理员登录', guest: true}
    },

    // ============ 管理端路由 ============
    {
        path: '/admin',
        component: () => import('@/layouts/AdminLayout.vue'),
        meta: {requireAuth: true, requireAdmin: true},
        children: [
            {
                path: '',
                name: 'AdminDashboard',
                component: () => import('@/views/admin/Dashboard.vue'),
                meta: {title: '控制台'}
            },
            {
                path: 'users',
                name: 'AdminUsers',
                component: () => import('@/views/admin/UserManagement.vue'),
                meta: {title: '用户管理'}
            },
            {
                path: 'audits',
                name: 'AdminAudits',
                component: () => import('@/views/admin/AuditManagement.vue'),
                meta: {title: '资质审核'}
            },
            {
                path: 'drones',
                name: 'AdminDrones',
                component: () => import('@/views/admin/DroneManagement.vue'),
                meta: {title: '无人机管理'}
            },
            {
                path: 'orders',
                name: 'AdminOrders',
                component: () => import('@/views/admin/OrderManagement.vue'),
                meta: {title: '订单管理'}
            },
            {
                path: 'fault-audit',
                name: 'AdminFaultAudit',
                component: () => import('@/views/admin/FaultAudit.vue'),
                meta: {title: '故障报修审核'}
            },
            {
                path: 'maintenance',
                name: 'AdminMaintenance',
                component: () => import('@/views/admin/MaintenanceManagement.vue'),
                meta: {title: '维保管理'}
            },
            {
                path: 'comments',
                name: 'AdminComments',
                component: () => import('@/views/admin/CommentManagement.vue'),
                meta: {title: '评价管理'}
            },
            {
                path: 'ai-logs',
                name: 'AdminAiLogs',
                component: () => import('@/views/admin/AiToolLogs.vue'),
                meta: {title: 'AI工具日志'}
            }
        ]
    },

    // ============ 404页面 ============
    {
        path: '/:pathMatch(.*)*',
        name: 'NotFound',
        component: () => import('@/views/NotFound.vue'),
        meta: {title: '页面未找到'}
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes,
    scrollBehavior(to, from, savedPosition) {
        if (savedPosition) {
            return savedPosition
        } else {
            return {top: 0}
        }
    }
})

let fetchingUser = false

// 路由守卫
router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()

    document.title = to.meta.title
        ? `${to.meta.title} - 无人机租赁系统`
        : '无人机租赁系统'

    // 仅在首次加载或 token 存在但 user 为空时拉取用户信息
    if (authStore.token && !authStore.user && !fetchingUser) {
        fetchingUser = true
        try {
            await authStore.fetchUserInfo()
        } finally {
            fetchingUser = false
        }
    }

    if (to.meta.guest && authStore.isLoggedIn) {
        return next(authStore.isAdmin ? '/admin' : '/')
    }

    if (to.meta.requireAuth && !authStore.isLoggedIn) {
        ElMessage.warning('请先登录')
        return next({
            path: '/login',
            query: {redirect: to.fullPath}
        })
    }

    const needsAdmin = to.matched.some(r => r.meta.requireAdmin)
    if (needsAdmin && !authStore.isAdmin) {
        ElMessage.error({ message: '无权访问管理后台', duration: 1000 })
        return next('/')
    }

    next()
})

export default router
