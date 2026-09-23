import {get, put, del} from './request'

// 获取通知列表
export const getNotifications = (params) => {
    return get('/notification/list', params)
}

// 获取未读数量
export const getUnreadCount = () => {
    return get('/notification/unread-count')
}

// 标记单条已读
export const markNotificationRead = (id) => {
    return put(`/notification/${id}/read`)
}

// 全部标记已读
export const markAllNotificationsRead = () => {
    return put('/notification/read-all')
}

// 删除通知
export const deleteNotification = (id) => {
    return del(`/notification/${id}`)
}
