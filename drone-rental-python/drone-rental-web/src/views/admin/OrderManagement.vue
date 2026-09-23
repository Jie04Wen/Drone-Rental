<template>
  <div class="order-management-page">
    <PageHeader title="订单管理" subtitle="管理所有租赁订单"/>

    <!-- 搜索筛选 -->
    <GlassCard class="filter-card">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="订单号">
          <el-input v-model="filters.orderNo" placeholder="请输入订单号" clearable/>
        </el-form-item>
        <el-form-item label="用户手机">
          <el-input v-model="filters.userPhone" placeholder="请输入手机号" clearable/>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.orderStatus" placeholder="全部" clearable style="width: 120px;">
            <el-option label="待支付" :value="0"/>
            <el-option label="待发货" :value="1"/>
            <el-option label="待收货" :value="2"/>
            <el-option label="租赁中" :value="3"/>
            <el-option label="已归还" :value="4"/>
            <el-option label="已取消" :value="5"/>
            <el-option label="已退款" :value="6"/>
            <el-option label="待归还/待寄回" :value="7"/>
            <el-option label="待商家收货" :value="8"/>
          </el-select>
        </el-form-item>
        <el-form-item label="日期范围">
          <el-date-picker
              v-model="filters.dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </GlassCard>

    <!-- 订单列表 -->
    <GlassCard class="table-card">
      <el-table :data="orderList" v-loading="loading" style="width: 100%">
        <el-table-column label="订单信息" width="360">
          <template #default="{ row }">
            <div class="order-info">
              <span class="order-no">{{ row.orderNo }}</span>
              <span class="order-time">{{ formatDateTime(row.createdTime) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="用户" width="200">
          <template #default="{ row }">
            <div class="user-info">
              <span class="user-name">{{ row.username || '-' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="设备" prop="droneModel" width="200"/>
        <el-table-column label="租赁周期" width="220" align="center" header-align="center">
          <template #default="{ row }">
            <span class="rental-period">{{ formatDate(row.rentalStartTime) }} ~ {{
                formatDate(row.rentalEndTime)
              }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="center" header-align="center">
          <template #default="{ row }">
            <span class="price">¥{{ money(row.payableAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="200" align="center" header-align="center">
          <template #default="{ row }">
            <StatusTag :text="getStatusText(row.orderStatus)" :type="getStatusType(row.orderStatus)" size="small"/>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" align="center" header-align="center">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button text type="primary" @click="handleViewDetail(row)">详情</el-button>
              <!-- 待发货(1): 发货 / 退款 -->
              <template v-if="row.orderStatus === 1">
                <el-button text type="success" @click="handleShip(row)">发货</el-button>
                <el-button text type="danger" @click="handleRefund(row)">退款</el-button>
              </template>
              <!-- 待商家收货(8): 验机并结算押金 -->
              <template v-if="row.orderStatus === 8">
                <el-button text type="warning" @click="handleConfirmReturn(row)">验机结算</el-button>
              </template>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.pageSize"
            :total="total"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            background
            @size-change="fetchOrderList"
            @current-change="fetchOrderList"
        />
      </div>
    </GlassCard>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="订单详情" width="800px">
      <div v-if="currentOrder" class="order-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="订单号">{{ currentOrder.orderNo }}</el-descriptions-item>
          <el-descriptions-item label="订单状态">
            <StatusTag :text="getStatusText(currentOrder.orderStatus)" :type="getStatusType(currentOrder.orderStatus)"/>
          </el-descriptions-item>
          <el-descriptions-item label="用户ID">{{ currentOrder.userId }}</el-descriptions-item>
          <el-descriptions-item label="用户名">{{ currentOrder.username || '-' }}</el-descriptions-item>
          <el-descriptions-item label="设备型号">{{ currentOrder.droneModel }}</el-descriptions-item>
          <el-descriptions-item label="单价">¥{{ currentOrder.unitPrice }}/天</el-descriptions-item>
          <el-descriptions-item label="租赁周期">{{ formatDate(currentOrder.rentalStartTime) }} ~
            {{ formatDate(currentOrder.rentalEndTime) }}
          </el-descriptions-item>
          <el-descriptions-item label="租赁天数">{{ currentOrder.rentalDays }} 天</el-descriptions-item>
          <el-descriptions-item label="押金">¥{{ currentOrder.depositAmount }}</el-descriptions-item>
          <el-descriptions-item label="租金">¥{{ money(currentOrder.totalAmount) }}</el-descriptions-item>
          <el-descriptions-item label="实付金额">
            <span class="price-highlight">¥{{ money(currentOrder.payableAmount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.depositStatus !== 0" label="押金结算">
            退还 ¥{{ money(currentOrder.depositRefundAmount) }} / 扣除 ¥{{ money(currentOrder.depositDeductionAmount) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.rentalRefundAmount > 0" label="提前归还退款">
            退还 {{ currentOrder.unusedRentalDays }} 天租金 ¥{{ money(currentOrder.rentalRefundAmount) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.returnAppliedTime" label="退租申请时间">
            {{ formatDateTime(currentOrder.returnAppliedTime) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.returnExpressNo" label="寄回物流">
            {{ currentOrder.returnExpressCompany }} {{ currentOrder.returnExpressNo }}
          </el-descriptions-item>
          <el-descriptions-item v-if="currentOrder.returnShippedTime" label="寄回时间">
            {{ formatDateTime(currentOrder.returnShippedTime) }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">{{
              formatDateTime(currentOrder.createdTime)
            }}
          </el-descriptions-item>
        </el-descriptions>
        <el-table v-if="returnLogs.length" :data="returnLogs" size="small" class="return-log-table">
          <el-table-column label="时间" prop="createdTime" width="170"/>
          <el-table-column label="动作" width="130">
            <template #default="{ row }">{{ getReturnActionText(row.action) }}</template>
          </el-table-column>
          <el-table-column label="状态流转" width="200">
            <template #default="{ row }">{{ getStatusText(row.fromStatus) }} → {{
                getStatusText(row.toStatus)
              }}
            </template>
          </el-table-column>
          <el-table-column label="备注" prop="remark" min-width="180" show-overflow-tooltip/>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 发货弹窗 -->
    <el-dialog v-model="shipVisible" title="订单发货" width="500px">
      <el-form :model="shipForm" label-width="100px">
        <el-form-item label="快递公司">
          <el-select v-model="shipForm.expressCompany" placeholder="请选择快递公司">
            <el-option label="顺丰速运" value="SF"/>
            <el-option label="京东物流" value="JD"/>
            <el-option label="中通快递" value="ZTO"/>
            <el-option label="圆通速递" value="YTO"/>
          </el-select>
        </el-form-item>
        <el-form-item label="快递单号">
          <el-input v-model="shipForm.expressNo" placeholder="请输入快递单号"/>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="shipVisible = false">取消</el-button>
        <el-button type="primary" :loading="shipping" @click="handleConfirmShip">确认发货</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="returnVisible" title="确认归还并结算费用" width="560px" :close-on-click-modal="false">
      <el-form label-width="120px">
        <el-form-item label="寄回时间">
          <span>{{ formatDateTime(returnForm.returnShippedTime) }}</span>
        </el-form-item>
        <el-form-item label="租金结算">
          <span v-if="returnForm.faultFullRefund" class="refund-preview">故障当天退还，租金全额退款</span>
          <span v-else>计费 {{ returnForm.chargeableRentalDays }} 天，退还 {{ returnForm.unusedRentalDays }} 天</span>
        </el-form-item>
        <el-form-item label="应退租金">
          <span class="refund-preview">¥{{ money(returnForm.rentalRefundAmount) }}</span>
        </el-form-item>
        <el-form-item label="订单押金">
          <strong>¥{{ money(returnForm.depositAmount) }}</strong>
        </el-form-item>
        <el-form-item label="扣除金额">
          <el-input-number
              v-model="returnForm.deductionAmount"
              :min="0"
              :max="returnForm.depositAmount"
              :precision="2"
              :step="100"
              :disabled="returnForm.faultFullRefund"
              style="width: 220px"
          />
        </el-form-item>
        <el-form-item label="应退押金">
          <span class="refund-preview">¥{{ money(depositRefundPreview) }}</span>
        </el-form-item>
        <el-form-item label="退款合计">
          <strong class="refund-preview">¥{{ money(totalRefundPreview) }}</strong>
        </el-form-item>
        <el-form-item label="扣除原因" :required="returnForm.deductionAmount > 0">
          <el-input
              v-model="returnForm.deductionReason"
              type="textarea"
              :rows="3"
              maxlength="255"
              show-word-limit
              placeholder="扣除押金时请填写损坏、逾期或维修费用说明"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="returnVisible = false">取消</el-button>
        <el-button type="primary" :loading="settling" @click="submitReturn">确认结算并归还</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import {ref, reactive, computed, onMounted} from 'vue'
import {useRoute} from 'vue-router'
import {ElMessage, ElMessageBox} from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import GlassCard from '@/components/common/GlassCard.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import {getAdminOrders, getAdminOrderDetail, getReturnLogs, shipOrder, confirmReturn, refundOrder} from '@/api/order'

const route = useRoute()

const loading = ref(false)
const shipping = ref(false)
const orderList = ref([])
const total = ref(0)
const detailVisible = ref(false)
const shipVisible = ref(false)
const returnVisible = ref(false)
const settling = ref(false)
const currentOrder = ref(null)
const returnLogs = ref([])

const filters = reactive({
  orderNo: '',
  userPhone: '',
  orderStatus: null,
  dateRange: null
})

const pagination = reactive({
  page: 1,
  pageSize: 10
})

const shipForm = reactive({
  orderId: null,
  expressCompany: '',
  expressNo: ''
})

const returnForm = reactive({
  orderId: null,
  depositAmount: 0,
  returnShippedTime: null,
  chargeableRentalDays: 0,
  unusedRentalDays: 0,
  rentalRefundAmount: 0,
  faultFullRefund: false,
  deductionAmount: 0,
  deductionReason: ''
})

const depositRefundPreview = computed(() => Math.max(
    Number(returnForm.depositAmount || 0) - Number(returnForm.deductionAmount || 0),
    0
))
const totalRefundPreview = computed(() => (
    depositRefundPreview.value + Number(returnForm.rentalRefundAmount || 0)
))

const money = (value) => Number(value || 0).toFixed(2)

const getStatusText = (status) => {
  const map = {
    0: '待支付',
    1: '待发货',
    2: '待收货',
    3: '租赁中',
    4: '已归还',
    5: '已取消',
    6: '已退款',
    7: '待归还/待寄回',
    8: '待商家收货'
  }
  return map[status] || '未知'
}

const getStatusType = (status) => {
  const map = {
    0: 'warning',
    1: 'info',
    2: 'info',
    3: 'primary',
    4: 'success',
    5: 'default',
    6: 'default',
    7: 'warning',
    8: 'info'
  }
  return map[status] || 'default'
}

const getReturnActionText = (action) => ({
  apply_return: '用户申请退租',
  submit_return_shipment: '用户提交寄回物流',
  inspect_and_settle: '管理员验机结算'
}[action] || action)

const getPaymentMethod = (method) => {
  const map = {alipay: '支付宝', wechat: '微信支付', balance: '余额支付'}
  return map[method] || method || '-'
}

// 格式化日期时间
const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  return dateTime.replace('T', ' ').substring(0, 19)
}

// 格式化日期
const formatDate = (dateTime) => {
  if (!dateTime) return '-'
  return dateTime.substring(0, 10)
}

const fetchOrderList = async () => {
  loading.value = true
  try {
    const params = {
      ...filters,
      page: pagination.page,
      pageSize: pagination.pageSize
    }
    if (filters.dateRange?.length) {
      params.startDate = filters.dateRange[0]
      params.endDate = filters.dateRange[1]
    }
    delete params.dateRange

    const res = await getAdminOrders(params)
    orderList.value = res.data?.records || []
    total.value = res.data?.total || 0
  } catch (error) {
    console.error('获取订单列表失败:', error)
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.page = 1
  fetchOrderList()
}

const handleReset = () => {
  Object.assign(filters, {orderNo: '', userPhone: '', orderStatus: null, dateRange: null})
  pagination.page = 1
  fetchOrderList()
}

const handleViewDetail = async (row) => {
  try {
    const [res, logsRes] = await Promise.all([getAdminOrderDetail(row.id), getReturnLogs(row.id)])
    currentOrder.value = res.data
    returnLogs.value = logsRes.data || []
    detailVisible.value = true
  } catch (error) {
    ElMessage.error('获取订单详情失败')
  }
}

const handleShip = (row) => {
  shipForm.orderId = row.id
  shipForm.expressCompany = ''
  shipForm.expressNo = ''
  shipVisible.value = true
}

const handleConfirmShip = async () => {
  if (!shipForm.expressCompany || !shipForm.expressNo) {
    ElMessage.warning('请填写快递信息')
    return
  }

  shipping.value = true
  try {
    await shipOrder(shipForm.orderId, {
      expressCompany: shipForm.expressCompany,
      expressNo: shipForm.expressNo
    })
    ElMessage.success({ message: '发货成功', duration: 1000 })
    shipVisible.value = false
    fetchOrderList()
  } catch (error) {
    // 错误已处理
  } finally {
    shipping.value = false
  }
}

const handleConfirmReturn = (row) => {
  Object.assign(returnForm, {
    orderId: row.id,
    depositAmount: Number(row.depositAmount || 0),
    returnShippedTime: row.returnShippedTime,
    chargeableRentalDays: Number(row.chargeableRentalDays || 0),
    unusedRentalDays: Number(row.unusedRentalDays || 0),
    rentalRefundAmount: Number(row.rentalRefundAmount || 0),
    faultFullRefund: Boolean(row.faultFullRefund),
    deductionAmount: 0,
    deductionReason: ''
  })
  returnVisible.value = true
}

const submitReturn = async () => {
  if (returnForm.faultFullRefund && returnForm.deductionAmount > 0) {
    ElMessage.warning('故障当天退还应全额退款，不能扣除押金')
    return
  }
  if (returnForm.deductionAmount > returnForm.depositAmount) {
    ElMessage.warning('扣除金额不能超过订单押金')
    return
  }
  if (returnForm.deductionAmount > 0 && !returnForm.deductionReason.trim()) {
    ElMessage.warning('扣除押金时必须填写扣除原因')
    return
  }
  try {
    await ElMessageBox.confirm(
        `${returnForm.faultFullRefund ? '故障当天退还，全额退款。' : ''}` +
        `本次退还租金 ¥${money(returnForm.rentalRefundAmount)}、押金 ¥${money(depositRefundPreview.value)}，` +
        `扣除押金 ¥${money(returnForm.deductionAmount)}，退款合计 ¥${money(totalRefundPreview.value)}，是否继续？`,
        '确认费用结算',
        {type: 'warning'}
    )
    settling.value = true
    await confirmReturn(returnForm.orderId, {
      deductionAmount: returnForm.deductionAmount,
      deductionReason: returnForm.deductionReason.trim() || null
    })
    ElMessage.success({ message: '归还及费用结算成功', duration: 1000 })
    returnVisible.value = false
    fetchOrderList()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
  } finally {
    settling.value = false
  }
}

const handleRefund = async (row) => {
  try {
    const {value: reason} = await ElMessageBox.prompt('请输入退款原因', '订单退款', {
      confirmButtonText: '确认退款',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '请输入退款原因',
      inputValidator: (v) => (v && v.trim().length > 0) || '退款原因不能为空'
    })
    await ElMessageBox.confirm(`将全额退还实付金额 ¥${money(row.payableAmount)}，是否继续？`, '确认全额退款', {
      type: 'warning'
    })
    await refundOrder(row.id, {mode: 'full', reason: reason.trim()})
    ElMessage.success({ message: '全额退款成功', duration: 1000 })
    fetchOrderList()
  } catch (error) {
    if (error === 'cancel') return
  }
}

onMounted(() => {
  if (route.query.status !== undefined) {
    filters.orderStatus = Number(route.query.status)
  }
  fetchOrderList()
})
</script>

<style lang="scss" scoped>
.order-management-page {
  min-height: 100%;
}

.filter-card {
  margin-bottom: 24px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;

  .el-form-item {
    margin-bottom: 0;
  }
}

.table-card {
  :deep(.el-table) {
    --el-table-bg-color: transparent;
    --el-table-tr-bg-color: transparent;
    --el-table-header-bg-color: #f8fafc;
  }

  :deep(.el-table__cell) {
    vertical-align: middle;
  }
}

.order-info, .user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.order-no {
  font-weight: 500;
  color: #0f172a;
}

.order-time {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.rental-period {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.table-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: nowrap;
  gap: 8px;
  white-space: nowrap;

  :deep(.el-button) {
    margin-left: 0;
  }
}

.user-name {
  font-weight: 500;
  color: #0f172a;
}

.user-phone {
  font-size: 12px;
  color: #64748b;
}

.price {
  color: #3b82f6;
  font-weight: 600;
}

.price-highlight {
  font-size: 18px;
  font-weight: 700;
  color: #3b82f6;
}

.refund-preview {
  color: #16a34a;
  font-size: 18px;
  font-weight: 700;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 24px;
}

.return-log-table {
  margin-top: 20px;
}
</style>
