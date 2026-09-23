<template>
  <div class="ai-logs-page">
    <PageHeader title="AI 工具调用日志" subtitle="查看 AI 助手调用工具的记录"/>

    <GlassCard class="filter-card">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="会话ID">
          <el-input v-model="filters.sessionId" placeholder="按会话ID筛选" clearable/>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </GlassCard>

    <GlassCard class="table-card">
      <el-table :data="logList" v-loading="loading" style="width: 100%">
        <el-table-column label="工具" prop="toolName" width="200"/>
        <el-table-column label="会话ID" prop="sessionId" width="300" show-overflow-tooltip/>
        <el-table-column label="用户ID" prop="userId" width="100" align="center"/>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small">
              {{ row.status === 1 ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时(ms)" prop="latencyMs" width="100" align="center"/>
        <el-table-column label="调用时间" width="180" align="center">
          <template #default="{ row }">
            {{ formatDateTime(row.createdTime) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button text type="primary" @click="handleViewDetail(row)">详情</el-button>
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
            @size-change="fetchLogs"
            @current-change="fetchLogs"
        />
      </div>
    </GlassCard>

    <el-dialog v-model="detailVisible" title="工具调用详情" width="700px">
      <div v-if="currentLog" class="log-detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="工具名">{{ currentLog.toolName }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="currentLog.status === 1 ? 'success' : 'danger'" size="small">
              {{ currentLog.status === 1 ? '成功' : '失败' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="会话ID">{{ currentLog.sessionId }}</el-descriptions-item>
          <el-descriptions-item label="用户ID">{{ currentLog.userId }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ currentLog.latencyMs }} ms</el-descriptions-item>
          <el-descriptions-item label="调用时间">{{ formatDateTime(currentLog.createdTime) }}</el-descriptions-item>
          <el-descriptions-item v-if="currentLog.errorMsg" label="错误信息" :span="2">
            {{ currentLog.errorMsg }}
          </el-descriptions-item>
        </el-descriptions>
        <div class="log-section">
          <h4>输入参数</h4>
          <pre class="log-code">{{ formatJson(currentLog.toolInput) }}</pre>
        </div>
        <div class="log-section">
          <h4>输出结果</h4>
          <pre class="log-code">{{ formatJson(currentLog.toolOutput) }}</pre>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import {ref, reactive, onMounted} from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import GlassCard from '@/components/common/GlassCard.vue'
import {aiApi} from '@/api/ai'

const loading = ref(false)
const logList = ref([])
const total = ref(0)
const detailVisible = ref(false)
const currentLog = ref(null)

const filters = reactive({sessionId: ''})
const pagination = reactive({page: 1, pageSize: 10})

const formatDateTime = (dt) => {
  if (!dt) return '-'
  return String(dt).replace('T', ' ').substring(0, 19)
}

const formatJson = (str) => {
  if (!str) return '-'
  try {
    return JSON.stringify(JSON.parse(str), null, 2)
  } catch (e) {
    return str
  }
}

const fetchLogs = async () => {
  loading.value = true
  try {
    const res = await aiApi.getToolLogs({
      sessionId: filters.sessionId || undefined,
      page: pagination.page,
      pageSize: pagination.pageSize
    })
    logList.value = res.data?.records || []
    total.value = res.data?.total || 0
  } catch (e) {
    console.error('获取工具日志失败:', e)
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.page = 1
  fetchLogs()
}

const handleReset = () => {
  filters.sessionId = ''
  pagination.page = 1
  fetchLogs()
}

const handleViewDetail = (row) => {
  currentLog.value = row
  detailVisible.value = true
}

onMounted(() => {
  fetchLogs()
})
</script>

<style lang="scss" scoped>
.ai-logs-page {
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

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 24px;
}

.log-detail {
  .log-section {
    margin-top: 16px;

    h4 {
      font-size: 14px;
      font-weight: 600;
      margin: 0 0 8px;
    }

    .log-code {
      background: #f5f7fa;
      border-radius: 8px;
      padding: 12px;
      font-size: 12px;
      max-height: 240px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-all;
      margin: 0;
    }
  }
}
</style>
