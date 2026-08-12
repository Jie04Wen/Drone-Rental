-- mysql CLI 的默认连接字符集可能不是 UTF-8；source 前先固定客户端、连接和结果字符集。
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建数据库
CREATE DATABASE IF NOT EXISTS drone_rental DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE drone_rental;

-- =====================================================
-- 1. 用户表 (user)
-- =====================================================
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    `username` VARCHAR(50) NOT NULL COMMENT '用户名',
    `password` VARCHAR(100) NOT NULL COMMENT '密码(加密存储)',
    `nickname` VARCHAR(50) DEFAULT NULL COMMENT '昵称',
    `phone` VARCHAR(20) DEFAULT NULL COMMENT '手机号',
    `email` VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
    `avatar` VARCHAR(255) DEFAULT NULL COMMENT '头像URL',
    `address` VARCHAR(255) DEFAULT NULL COMMENT '住址',
    `role` TINYINT NOT NULL DEFAULT 0 COMMENT '角色: 0-普通用户, 1-管理员',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-禁用, 1-正常',
    `credit_status` TINYINT NOT NULL DEFAULT 1 COMMENT '诚信状态: 0-不良, 1-正常',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除: 0-未删除, 1-已删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_phone` (`phone`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- =====================================================
-- 2. 用户飞行资质表 (user_qualification)
-- =====================================================
DROP TABLE IF EXISTS `user_qualification`;
CREATE TABLE `user_qualification` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '资质ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `certificate_no` VARCHAR(50) NOT NULL COMMENT '证件号码',
    `certificate_type` VARCHAR(50) DEFAULT NULL COMMENT '证件类型',
    `certificate_image` VARCHAR(255) DEFAULT NULL COMMENT '证件图片URL',
    `valid_start_date` DATE DEFAULT NULL COMMENT '有效期开始日期',
    `valid_end_date` DATE DEFAULT NULL COMMENT '有效期结束日期',
    `audit_status` TINYINT NOT NULL DEFAULT 0 COMMENT '审核状态: 0-待审核, 1-审核通过, 2-审核拒绝',
    `audit_remark` VARCHAR(255) DEFAULT NULL COMMENT '审核备注',
    `audit_time` DATETIME DEFAULT NULL COMMENT '审核时间',
    `auditor_id` BIGINT DEFAULT NULL COMMENT '审核人ID',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_audit_status` (`audit_status`),
    KEY `idx_certificate_no` (`certificate_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户飞行资质表';

-- =====================================================
-- 3. 无人机表 (drone)
-- =====================================================
DROP TABLE IF EXISTS `drone`;
CREATE TABLE `drone` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '无人机ID',
    `model` VARCHAR(100) NOT NULL COMMENT '型号名称',
    `brand` VARCHAR(50) DEFAULT NULL COMMENT '品牌',
    `type` VARCHAR(20) DEFAULT NULL COMMENT '类型: 航拍/测绘/农业/巡检',
    `description` TEXT DEFAULT NULL COMMENT '描述信息',
    `image` VARCHAR(255) DEFAULT NULL COMMENT '图片URL',
    `price_per_day` DECIMAL(10,2) NOT NULL COMMENT '每日租赁价格(元)',
    `deposit` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '押金(元)',
    `stock` INT NOT NULL DEFAULT 0 COMMENT '库存数量',
    `flight_time` INT DEFAULT NULL COMMENT '续航时间(分钟)',
    `max_payload` DECIMAL(10,2) DEFAULT NULL COMMENT '最大载重(kg)',
    `max_speed` DECIMAL(10,2) DEFAULT NULL COMMENT '最大速度(km/h)',
    `max_range` DECIMAL(10,2) DEFAULT NULL COMMENT '最大航程(km)',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-缺货, 1-在售, 2-维护中',
    `on_shelf` TINYINT NOT NULL DEFAULT 1 COMMENT '上架状态: 0-下架, 1-上架',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    KEY `idx_model` (`model`),
    KEY `idx_status` (`status`),
    KEY `idx_on_shelf` (`on_shelf`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='无人机表';

-- =====================================================
-- 4. 无人机库存日志表 (drone_stock_log)
-- =====================================================
DROP TABLE IF EXISTS `drone_stock_log`;
CREATE TABLE `drone_stock_log` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `drone_id` BIGINT NOT NULL COMMENT '无人机ID',
    `change_type` TINYINT NOT NULL COMMENT '变更类型: 1-入库, 2-出租, 3-归还, 4-维修占用, 5-维修归还',
    `change_amount` INT NOT NULL COMMENT '变更数量(正数增加,负数减少)',
    `before_stock` INT NOT NULL COMMENT '变更前库存',
    `after_stock` INT NOT NULL COMMENT '变更后库存',
    `related_order_id` BIGINT DEFAULT NULL COMMENT '关联订单ID',
    `remark` VARCHAR(255) DEFAULT NULL COMMENT '备注',
    `operator_id` BIGINT DEFAULT NULL COMMENT '操作人ID',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_drone_id` (`drone_id`),
    KEY `idx_change_type` (`change_type`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='无人机库存日志表';

-- =====================================================
-- 5. 空域备案表 (airspace_record)
-- =====================================================
DROP TABLE IF EXISTS `airspace_record`;
CREATE TABLE `airspace_record` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '备案ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `region_name` VARCHAR(100) NOT NULL COMMENT '飞行区域名称',
    `region_address` VARCHAR(255) DEFAULT NULL COMMENT '飞行区域详细地址',
    `longitude` DECIMAL(10,6) DEFAULT NULL COMMENT '经度',
    `latitude` DECIMAL(10,6) DEFAULT NULL COMMENT '纬度',
    `radius` INT DEFAULT NULL COMMENT '飞行半径(米)',
    `max_altitude` INT DEFAULT NULL COMMENT '最大飞行高度(米)',
    `planned_start_time` DATETIME DEFAULT NULL COMMENT '计划开始时间',
    `planned_end_time` DATETIME DEFAULT NULL COMMENT '计划结束时间',
    `purpose` VARCHAR(255) DEFAULT NULL COMMENT '飞行用途',
    `audit_status` TINYINT NOT NULL DEFAULT 0 COMMENT '审核状态: 0-待审核, 1-审核通过, 2-审核拒绝',
    `audit_remark` VARCHAR(255) DEFAULT NULL COMMENT '审核备注',
    `audit_time` DATETIME DEFAULT NULL COMMENT '审核时间',
    `auditor_id` BIGINT DEFAULT NULL COMMENT '审核人ID',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_audit_status` (`audit_status`),
    KEY `idx_region_name` (`region_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='空域备案表';

-- =====================================================
-- 6. 租赁订单表 (rental_order)
-- =====================================================
DROP TABLE IF EXISTS `rental_order`;
CREATE TABLE `rental_order` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '订单ID',
    `order_no` VARCHAR(32) NOT NULL COMMENT '订单编号',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `drone_id` BIGINT NOT NULL COMMENT '无人机ID',
    `airspace_record_id` BIGINT NULL COMMENT '空域备案ID',
    `rental_start_time` DATETIME NOT NULL COMMENT '租赁开始时间',
    `rental_end_time` DATETIME NOT NULL COMMENT '租赁结束时间',
    `rental_days` INT NOT NULL COMMENT '租赁天数',
    `unit_price` DECIMAL(10,2) NOT NULL COMMENT '单价(元/天)',
    `total_amount` DECIMAL(10,2) NOT NULL COMMENT '订单总金额',
    `deposit_amount` DECIMAL(10,2) DEFAULT 0.00 COMMENT '押金金额',
    `deposit_status` TINYINT NOT NULL DEFAULT 0 COMMENT '押金状态: 0-待结算, 1-已全额退还, 2-已部分扣除, 3-已全部扣除',
    `deposit_deduction_amount` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '押金扣除金额',
    `deposit_refund_amount` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '押金退还金额',
    `deposit_deduction_reason` VARCHAR(255) DEFAULT NULL COMMENT '押金扣除原因',
    `deposit_settled_time` DATETIME DEFAULT NULL COMMENT '押金结算时间',
    `deposit_settled_by` BIGINT DEFAULT NULL COMMENT '押金结算管理员ID',
    `delivery_address` VARCHAR(500) DEFAULT NULL COMMENT '收货地址',
    `return_applied_time` DATETIME DEFAULT NULL COMMENT '申请退租时间',
    `return_apply_reason` VARCHAR(255) DEFAULT NULL COMMENT '退租申请原因',
    `return_express_company` VARCHAR(100) DEFAULT NULL COMMENT '寄回快递公司',
    `return_express_no` VARCHAR(100) DEFAULT NULL COMMENT '寄回快递单号',
    `return_shipped_time` DATETIME DEFAULT NULL COMMENT '寄回发货时间',
    `ship_time` DATETIME DEFAULT NULL COMMENT '商家发货时间',
    `receive_time` DATETIME DEFAULT NULL COMMENT '用户确认收货时间',
    `order_status` TINYINT NOT NULL DEFAULT 0 COMMENT '订单状态: 0-待支付, 1-待发货, 2-待收货, 3-租赁中, 4-已归还, 5-已取消, 6-已退款, 7-待归还/待寄回, 8-待商家收货',
    `remark` VARCHAR(255) DEFAULT NULL COMMENT '订单备注',
    `cancel_reason` VARCHAR(255) DEFAULT NULL COMMENT '取消原因',
    `cancel_time` DATETIME DEFAULT NULL COMMENT '取消时间',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_order_no` (`order_no`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_drone_id` (`drone_id`),
    KEY `idx_order_status` (`order_status`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租赁订单表';
-- =====================================================
-- 6.1 退租流程审计日志表 (order_return_log)
-- =====================================================
DROP TABLE IF EXISTS `order_return_log`;
CREATE TABLE `order_return_log` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `order_id` BIGINT NOT NULL COMMENT '订单ID',
    `order_no` VARCHAR(32) NOT NULL COMMENT '订单编号',
    `action` VARCHAR(30) NOT NULL COMMENT '动作: apply_return/submit_return_shipment/inspect_and_settle',
    `from_status` TINYINT NOT NULL COMMENT '变更前订单状态',
    `to_status` TINYINT NOT NULL COMMENT '变更后订单状态',
    `operator_id` BIGINT NOT NULL COMMENT '操作人ID',
    `operator_role` TINYINT NOT NULL COMMENT '操作人角色: 0-用户, 1-管理员',
    `express_company` VARCHAR(100) DEFAULT NULL COMMENT '寄回快递公司快照',
    `express_no` VARCHAR(100) DEFAULT NULL COMMENT '寄回快递单号快照',
    `remark` VARCHAR(255) DEFAULT NULL COMMENT '操作备注',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (`id`),
    KEY `idx_order_id` (`order_id`),
    KEY `idx_order_no` (`order_no`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='退租流程审计日志表';
-- =====================================================
-- 7. 支付记录表 (payment)
-- =====================================================
DROP TABLE IF EXISTS `payment`;
CREATE TABLE `payment` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '支付ID',
    `payment_no` VARCHAR(32) NOT NULL COMMENT '支付单号',
    `order_id` BIGINT NOT NULL COMMENT '订单ID',
    `order_no` VARCHAR(32) NOT NULL COMMENT '订单编号',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `amount` DECIMAL(10,2) NOT NULL COMMENT '支付金额',
    `payment_type` TINYINT NOT NULL DEFAULT 1 COMMENT '支付类型: 1-订单支付, 2-押金支付, 3-维修费支付',
    `payment_method` VARCHAR(20) DEFAULT 'SIMULATED' COMMENT '支付方式: SIMULATED-模拟支付, ALIPAY-支付宝, WECHAT-微信',
    `payment_status` TINYINT NOT NULL DEFAULT 0 COMMENT '支付状态: 0-未支付, 1-已支付, 2-已全额退款, 3-已部分退款',
    `payment_time` DATETIME DEFAULT NULL COMMENT '支付时间',
    `refund_time` DATETIME DEFAULT NULL COMMENT '退款时间',
    `refund_amount` DECIMAL(10,2) DEFAULT NULL COMMENT '退款金额',
    `refund_reason` VARCHAR(255) DEFAULT NULL COMMENT '退款原因',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_payment_no` (`payment_no`),
    KEY `idx_order_id` (`order_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_payment_status` (`payment_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='支付记录表';

-- =====================================================
-- 8. 评论表 (comment)
-- =====================================================
DROP TABLE IF EXISTS `comment`;
CREATE TABLE `comment` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '评论ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `drone_id` BIGINT NOT NULL COMMENT '无人机ID',
    `order_id` BIGINT DEFAULT NULL COMMENT '订单ID',
    `content` TEXT NOT NULL COMMENT '评论内容',
    `rating` TINYINT DEFAULT 5 COMMENT '评分: 1-5星',
    `images` VARCHAR(1000) DEFAULT NULL COMMENT '评论图片(JSON数组)',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-已屏蔽, 1-正常',
    `reply_content` TEXT DEFAULT NULL COMMENT '管理员回复内容',
    `reply_time` DATETIME DEFAULT NULL COMMENT '回复时间',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_drone_id` (`drone_id`),
    KEY `idx_order_id` (`order_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='评论表';

-- =====================================================
-- 9. 故障上报表 (fault_report)
-- =====================================================
DROP TABLE IF EXISTS `fault_report`;
CREATE TABLE `fault_report` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '故障ID',
    `report_no` VARCHAR(32) NOT NULL COMMENT '故障单号',
    `user_id` BIGINT NOT NULL COMMENT '上报用户ID',
    `drone_id` BIGINT NOT NULL COMMENT '无人机ID',
    `order_id` BIGINT DEFAULT NULL COMMENT '关联订单ID',
    `fault_type` VARCHAR(50) DEFAULT NULL COMMENT '故障类型',
    `fault_description` TEXT NOT NULL COMMENT '故障描述',
    `fault_images` VARCHAR(1000) DEFAULT NULL COMMENT '故障图片(JSON数组)',
    `fault_time` DATETIME DEFAULT NULL COMMENT '故障发生时间',
    `audit_status` TINYINT NOT NULL DEFAULT 0 COMMENT '审核状态: 0-待审核, 1-确认故障, 2-非故障',
    `audit_remark` VARCHAR(255) DEFAULT NULL COMMENT '审核备注',
    `audit_time` DATETIME DEFAULT NULL COMMENT '审核时间',
    `auditor_id` BIGINT DEFAULT NULL COMMENT '审核人ID',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_report_no` (`report_no`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_drone_id` (`drone_id`),
    KEY `idx_order_id` (`order_id`),
    KEY `idx_audit_status` (`audit_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='故障上报表';

-- =====================================================
-- 10. 维修工单表 (maintenance_ticket)
-- =====================================================
DROP TABLE IF EXISTS `maintenance_ticket`;
CREATE TABLE `maintenance_ticket` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '工单ID',
    `ticket_no` VARCHAR(32) NOT NULL COMMENT '工单编号',
    `fault_report_id` BIGINT NOT NULL COMMENT '故障上报ID',
    `drone_id` BIGINT NOT NULL COMMENT '无人机ID',
    `user_id` BIGINT DEFAULT NULL COMMENT '关联用户ID',
    `maintenance_type` VARCHAR(50) DEFAULT NULL COMMENT '维修类型',
    `maintenance_description` TEXT DEFAULT NULL COMMENT '维修描述',
    `status` TINYINT NOT NULL DEFAULT 0 COMMENT '状态: 0-待维修, 1-维修中, 2-已完成, 3-已取消',
    `estimated_cost` DECIMAL(10,2) DEFAULT NULL COMMENT '预估费用',
    `actual_cost` DECIMAL(10,2) DEFAULT NULL COMMENT '实际费用',
    `estimated_days` INT DEFAULT NULL COMMENT '预估维修天数',
    `actual_days` INT DEFAULT NULL COMMENT '实际维修天数',
    `start_time` DATETIME DEFAULT NULL COMMENT '维修开始时间',
    `complete_time` DATETIME DEFAULT NULL COMMENT '维修完成时间',
    `progress_notes` TEXT DEFAULT NULL COMMENT '进度备注(JSON数组)',
    `assignee_name` VARCHAR(50) DEFAULT NULL COMMENT '维修负责人',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '逻辑删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ticket_no` (`ticket_no`),
    KEY `idx_fault_report_id` (`fault_report_id`),
    KEY `idx_drone_id` (`drone_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='维修工单表';

-- =====================================================
-- 11. 诚信记录表 (credit_record)
-- =====================================================
DROP TABLE IF EXISTS `credit_record`;
CREATE TABLE `credit_record` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '记录ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `change_type` TINYINT NOT NULL COMMENT '变更类型: 1-标记不良, 2-恢复正常, 3-系统扣分, 4-系统加分',
    `before_status` TINYINT NOT NULL COMMENT '变更前状态: 0-不良, 1-正常',
    `after_status` TINYINT NOT NULL COMMENT '变更后状态: 0-不良, 1-正常',
    `reason` VARCHAR(255) DEFAULT NULL COMMENT '变更原因',
    `operator_id` BIGINT DEFAULT NULL COMMENT '操作人ID',
    `operator_name` VARCHAR(50) DEFAULT NULL COMMENT '操作人名称',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_change_type` (`change_type`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='诚信记录表';

-- =====================================================
-- 初始数据
-- =====================================================

-- 注意：密码使用 MD5 加密存储
-- 首次登录时系统会自动将 MD5 密码升级为 BCrypt 加密
-- 默认密码：123456

-- 插入默认管理员账号 (密码: 123456, MD5 加密)
INSERT INTO `user` (`username`, `password`, `nickname`, `phone`, `role`, `status`, `credit_status`) VALUES
('admin', 'e10adc3949ba59abbe56e057f20f883e', '系统管理员', '13800000000', 1, 1, 1);

-- 插入测试用户 (密码: 123456, MD5 加密)
INSERT INTO `user` (`username`, `password`, `nickname`, `phone`, `email`, `address`, `role`, `status`, `credit_status`) VALUES
('testuser', 'e10adc3949ba59abbe56e057f20f883e', '测试用户', '13900000001', 'test@example.com', '北京市朝阳区', 0, 1, 1);

-- 插入示例无人机数据
INSERT INTO `drone` (`model`, `brand`, `type`, `description`, `image`, `price_per_day`, `deposit`, `stock`, `flight_time`, `max_payload`, `max_speed`, `max_range`, `status`, `on_shelf`) VALUES
('DJI Mavic 3', 'DJI大疆', '航拍', '专业航拍无人机，4/3 CMOS哈苏相机，46分钟续航', '/uploads/mavic3_drone.png', 299.00, 5000.00, 10, 46, 0.9, 75.0, 30.0, 1, 1),
('DJI Mini 3 Pro', 'DJI大疆', '航拍', '轻便型航拍无人机，249g起飞重量，适合新手', '/uploads/mini3pro_drone.png', 149.00, 2000.00, 15, 34, 0.25, 58.0, 18.0, 1, 1),
('DJI Air 2S', 'DJI大疆', '航拍', '一英寸传感器，5.4K视频，智能跟随', '/uploads/air2s_drone.png', 199.00, 3500.00, 8, 31, 0.6, 68.0, 18.5, 1, 1),
('DJI Inspire 2', 'DJI大疆', '航拍', '专业影视航拍平台，可换镜头，双操控', '/uploads/inspire2_drone.png', 599.00, 10000.00, 5, 27, 1.4, 94.0, 15.0, 1, 1),
('DJI Phantom 4 Pro V2.0', 'DJI大疆', '测绘', '经典航拍无人机，一英寸传感器', '/uploads/phantom4pro_drone.png', 249.00, 4000.00, 6, 30, 0.5, 72.0, 15.0, 1, 1),
('DJI Agras T40', 'DJI大疆', '农业', '农业植保无人机，40kg喷洒载荷', '/uploads/agrast40_drone.png', 899.00, 15000.00, 3, 25, 50.0, 45.0, 10.0, 1, 1);

-- 插入示例空域备案数据
INSERT INTO `airspace_record` (`user_id`, `region_name`, `region_address`, `longitude`, `latitude`, `radius`, `max_altitude`, `purpose`, `audit_status`) VALUES
(2, '北京奥林匹克公园', '北京市朝阳区奥林匹克公园', 116.391244, 39.992552, 500, 120, '航拍摄影', 1),
(2, '上海外滩', '上海市黄浦区外滩', 121.490317, 31.240018, 300, 100, '城市风光拍摄', 0);

-- =====================================================
-- 12. 站内消息通知表 (notification)
-- =====================================================
DROP TABLE IF EXISTS `notification`;
CREATE TABLE `notification` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '通知ID',
    `user_id` BIGINT NOT NULL COMMENT '接收用户ID',
    `title` VARCHAR(200) NOT NULL COMMENT '通知标题',
    `content` TEXT NOT NULL COMMENT '通知内容',
    `type` VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '类型: system/order/qualification/fault/payment',
    `related_id` VARCHAR(64) DEFAULT NULL COMMENT '关联业务ID（订单号等）',
    `is_read` TINYINT NOT NULL DEFAULT 0 COMMENT '是否已读: 0-未读, 1-已读',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `read_time` DATETIME DEFAULT NULL COMMENT '阅读时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_is_read` (`is_read`),
    KEY `idx_created_time` (`created_time`),
    KEY `idx_type` (`type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='站内消息通知表';

-- =====================================================
-- 13. AI 会话追踪表 (ai_chat_trace)
-- =====================================================
DROP TABLE IF EXISTS `ai_chat_trace`;
CREATE TABLE `ai_chat_trace` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '追踪ID',
    `session_id` VARCHAR(64) NOT NULL COMMENT '会话ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `role` VARCHAR(20) NOT NULL COMMENT '角色: user/assistant/system',
    `content` TEXT NOT NULL COMMENT '消息内容',
    `model` VARCHAR(100) DEFAULT NULL COMMENT '使用的模型',
    `token_usage` INT DEFAULT NULL COMMENT 'Token用量',
    `latency_ms` INT DEFAULT NULL COMMENT '响应耗时(ms)',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_session_id` (`session_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI会话追踪表';

-- =====================================================
-- 14. AI 工具调用日志表 (ai_tool_call_log)
-- =====================================================
DROP TABLE IF EXISTS `ai_tool_call_log`;
CREATE TABLE `ai_tool_call_log` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `session_id` VARCHAR(64) NOT NULL COMMENT '会话ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `tool_name` VARCHAR(100) NOT NULL COMMENT '工具名称',
    `tool_input` TEXT COMMENT '工具输入参数(JSON)',
    `tool_output` TEXT COMMENT '工具输出结果(JSON)',
    `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-失败, 1-成功',
    `error_msg` VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
    `latency_ms` INT DEFAULT NULL COMMENT '执行耗时(ms)',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_session_id` (`session_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_tool_name` (`tool_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI工具调用日志表';

-- =====================================================
-- 15. AI 用户记忆与本地知识库表 (ai_memory)
-- =====================================================
DROP TABLE IF EXISTS `ai_memory`;
CREATE TABLE `ai_memory` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '记忆ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID；0 表示本地知识库',
    `memory_key` VARCHAR(100) NOT NULL COMMENT '记忆键',
    `memory_value` TEXT NOT NULL COMMENT '记忆值',
    `category` VARCHAR(50) DEFAULT 'general' COMMENT '分类: preference/context/fact',
    `importance` TINYINT DEFAULT 5 COMMENT '重要性: 1-10',
    `created_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_key` (`user_id`, `memory_key`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI用户记忆表';

-- =====================================================
-- RAGFlow 知识库内容初始化脚本
-- 用于填充 AI 助手的知识库
-- =====================================================

-- 使用 AI 记忆表存储知识库内容（作为 RAGFlow 不可用时的降级方案）

-- =====================================================
-- 1. 设备知识库
-- =====================================================

INSERT INTO `ai_memory` (`user_id`, `memory_key`, `memory_value`, `category`, `importance`) VALUES
-- DJI Mavic 3
(0, 'drone_dji_mavic3_info', 'DJI Mavic 3 是一款专业航拍无人机。主要参数：4/3 CMOS哈苏相机，46分钟续航，0.9kg最大载重，75km/h最高速度，30km最大航程。日租金299元。适合专业航拍、影视拍摄、婚礼跟拍等场景。', 'fact', 9),

-- DJI Mini 3 Pro
(0, 'drone_dji_mini3pro_info', 'DJI Mini 3 Pro 是一款轻便型航拍无人机。主要参数：249g起飞重量免注册，34分钟续航，0.25kg最大载重，58km/h最高速度，18km最大航程。日租金149元。适合新手入门、旅行拍摄、Vlog制作。', 'fact', 9),

-- DJI Air 2S
(0, 'drone_dji_air2s_info', 'DJI Air 2S 是一款中端航拍无人机。主要参数：一英寸传感器，5.4K视频，31分钟续航，0.6kg最大载重，68km/h最高速度，18.5km最大航程。日租金199元。适合航拍爱好者、短视频创作。', 'fact', 9),

-- DJI Inspire 2
(0, 'drone_dji_inspire2_info', 'DJI Inspire 2 是一款专业影视航拍平台。主要参数：可换镜头设计，双操控模式，27分钟续航，1.4kg最大载重，94km/h最高速度，15km最大航程。日租金599元。适合专业影视制作、大型活动拍摄。', 'fact', 9),

-- DJI Phantom 4 Pro
(0, 'drone_dji_phantom4pro_info', 'DJI Phantom 4 Pro V2.0 是一款经典航拍无人机。主要参数：一英寸传感器，30分钟续航，0.5kg最大载重，72km/h最高速度，15km最大航程。日租金249元。适合测绘、巡检、航拍。', 'fact', 9),

-- DJI Agras T40
(0, 'drone_dji_agrast40_info', 'DJI Agras T40 是一款农业植保无人机。主要参数：40kg喷洒载荷，25分钟续航，45km/h最高速度，10km最大航程。日租金899元。适合农业植保、农药喷洒、播种作业。', 'fact', 9);

-- =====================================================
-- 2. 租赁规则知识库
-- =====================================================

INSERT INTO `ai_memory` (`user_id`, `memory_key`, `memory_value`, `category`, `importance`) VALUES
(0, 'rental_rule_qualification', '租赁无人机前必须完成实名认证。用户需要在个人中心提交飞行资质（如CAAC无人机驾驶员执照），等待管理员审核通过后方可租赁。资质审核通常在1-2个工作日内完成。', 'fact', 10),

(0, 'rental_rule_order_flow', '租赁流程：1.浏览设备 → 2.选择设备和租赁日期 → 3.创建订单 → 4.支付 → 5.等待发货 → 6.确认收货 → 7.使用设备 → 8.归还设备 → 9.评价。订单创建后24小时内未支付将自动取消。', 'fact', 10),

(0, 'rental_rule_payment', '支付方式支持：支付宝（沙箱环境）和模拟支付。订单创建后需在24小时内完成支付，超时订单自动取消。支付成功后订单状态变为"已支付"，等待商家发货。', 'fact', 9),

(0, 'rental_rule_cancellation', '订单取消规则：待支付状态的订单可直接取消；已支付未发货的订单可申请退款；已发货的订单不支持取消，需联系客服处理。', 'fact', 9),

(0, 'rental_rule_return', '设备归还流程：1.在订单详情点击"申请退租" → 2.按商家要求寄回设备 → 3.商家确认收货 → 4.订单完成。归还时请确保设备完好，如有损坏将扣除押金。', 'fact', 9),

(0, 'rental_rule_late_return', '逾期归还规则：超过租赁期限未归还设备，将按日租金的150%收取逾期费用。逾期超过7天，系统将自动扣除全部押金并标记用户信用异常。', 'fact', 8);

-- =====================================================
-- 3. 故障报修知识库
-- =====================================================

INSERT INTO `ai_memory` (`user_id`, `memory_key`, `memory_value`, `category`, `importance`) VALUES
(0, 'fault_report_guide', '故障报修流程：1.进入"故障报修"页面 → 2.选择故障设备 → 3.选择故障类型（硬件故障/软件故障/其他） → 4.详细描述故障现象 → 5.上传故障照片 → 6.提交报修申请 → 7.等待管理员审核。审核通过后将安排维修。', 'fact', 9),

(0, 'fault_common_issues', '常见故障处理：螺旋桨断裂-立即停止使用并报修；电池续航异常-检查电池健康状态；信号丢失-检查遥控器连接；摄像头故障-重启设备后报修。所有硬件故障请勿自行拆解。', 'fact', 8),

(0, 'fault_emergency', '紧急情况处理：设备失控-立即关闭电机电源；坠落损坏-拍照记录现场并报修；进水-断电后自然晾干，不要使用吹风机，尽快送修。', 'fact', 9);

-- =====================================================
-- 4. 空域备案知识库
-- =====================================================

INSERT INTO `ai_memory` (`user_id`, `memory_key`, `memory_value`, `category`, `importance`) VALUES
(0, 'airspace_rule', '空域备案规则：在管制区域飞行需提前进行空域备案。备案需提供：飞行区域名称、详细地址、经纬度、飞行半径、最大飞行高度、计划飞行时间、飞行用途。审核通过后方可飞行。', 'fact', 9),

(0, 'airspace_restricted', '禁飞区域：机场周边、军事管制区、政府机关、大型活动现场、人口密集区等。在禁飞区域飞行将面临行政处罚。建议飞行前使用无人机管理APP查询禁飞区。', 'fact', 10);

-- =====================================================
-- 5. 法规知识库
-- =====================================================

INSERT INTO `ai_memory` (`user_id`, `memory_key`, `memory_value`, `category`, `importance`) VALUES
(0, 'regulation_pilot_license', '飞行资质要求：250g以上无人机需要实名登记。操控轻型无人机（4kg以下）需取得相应执照。操控小型无人机（15kg以下）需取得CAAC驾驶员执照。建议租赁前确认是否具备相应资质。', 'fact', 10),

(0, 'regulation_insurance', '保险建议：建议租赁期间购买无人机保险，覆盖意外损坏、丢失等情况。部分高端设备（如Inspire 2）租赁费用已包含基础保险。', 'fact', 7),

(0, 'regulation_max_altitude', '飞行高度限制：民用无人机最大飞行高度为120米（真高）。超过120米飞行需特殊审批。建议飞行前确认当地空域限制。', 'fact', 9);

-- =====================================================
-- 6. FAQ 知识库
-- =====================================================

INSERT INTO `ai_memory` (`user_id`, `memory_key`, `memory_value`, `category`, `importance`) VALUES
(0, 'faq_how_to_rent', '租赁步骤：1.注册账号 → 2.完成实名认证 → 3.浏览设备选择心仪的无人机 → 4.选择租赁日期 → 5.创建订单并支付 → 6.等待发货 → 7.收到设备后确认收货开始使用。', 'fact', 10),

(0, 'faq_payment_methods', '支付方式：目前支持支付宝（沙箱环境）和模拟支付。正式环境将接入微信支付和支付宝正式接口。', 'fact', 8),

(0, 'faq_refund_policy', '退款政策：已支付未发货的订单可申请全额退款；已发货未收货的订单需承担运费；已收货的订单不支持退款，可申请退租。', 'fact', 9),

(0, 'faq_damage_policy', '损坏赔偿：设备归还时如有损坏，将根据损坏程度扣除维修费用或押金。人为损坏（如坠落、进水）需承担全部维修费用。建议使用过程中小心操作。', 'fact', 9),

(0, 'faq_contact', '联系方式：如有其他问题，请在系统内使用AI助手咨询，或联系客服。客服工作时间：周一至周五 9:00-18:00。', 'fact', 7);
