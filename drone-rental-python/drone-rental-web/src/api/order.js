import {get, post, put} from './request'

// ============ 用户端 ============

// 创建订单（携带幂等键防重复提交）
export const createOrder = (data) => {
    const {_idempotencyKey, ...payload} = data
    const idempotencyKey = _idempotencyKey || crypto.randomUUID()

    return post('/order/create', payload, {
        headers: {'X-Idempotency-Key': idempotencyKey}
    })
}

// 获取我的订单列表（通过 UserController）
export const getMyOrders = (params) => {
    return get('/user/orders', params)
}

// 获取订单详情
export const getOrderDetail = (id) => {
    return get(`/order/${id}`)
}

// 支付订单（模拟）
export const payOrder = (id, paymentMethod, deliveryAddress) => {
    return post(`/order/${id}/pay`, {paymentMethod, deliveryAddress})
}

// 取消订单
export const cancelOrder = (id, reason) => {
    return post(`/order/${id}/cancel`, {reason})
}

// 确认收货
export const confirmReceive = (id) => {
    return post(`/order/${id}/receive`)
}

// 申请退租
export const applyReturn = (id) => {
    return post(`/order/${id}/return`)
}

// 填写寄回物流
export const submitReturnShipment = (id, data) => {
    return post(`/order/${id}/return-shipment`, data)
}

// 评价订单
export const commentOrder = (id, data) => {
    return post(`/comment/add`, {orderId: id, ...data})
}

// ============ 管理端 ============

// 获取订单列表（管理端）
export const getAdminOrders = (params) => {
    return get('/admin/order/list', params)
}

// 获取订单详情（管理端）
export const getAdminOrderDetail = (id) => {
    return get(`/admin/order/${id}`)
}

export const getReturnLogs = (id) => {
    return get(`/admin/order/${id}/return-logs`)
}

// 发货
export const shipOrder = (id, data) => {
    return post(`/admin/order/${id}/ship?expressCompany=${encodeURIComponent(data.expressCompany)}&expressNo=${encodeURIComponent(data.expressNo)}`)
}

// 确认退租
export const confirmReturn = (id, data) => {
    return post(`/admin/order/${id}/return`, data)
}

// 退款
export const refundOrder = (id, data) => {
    return post(`/admin/order/${id}/refund`, data)
}
