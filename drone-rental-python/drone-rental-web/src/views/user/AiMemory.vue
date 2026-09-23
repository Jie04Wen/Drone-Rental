<template>
  <div class="ai-memory-page">
    <PageHeader title="AI 记忆管理" subtitle="管理 AI 助手记住的偏好与信息"/>

    <GlassCard class="memory-card">
      <div class="memory-header">
        <el-button type="primary" @click="handleAdd">+ 新增记忆</el-button>
      </div>

      <el-table :data="memoryList" v-loading="loading" style="width: 100%">
        <el-table-column label="记忆键" prop="memoryKey" width="300" show-overflow-tooltip/>
        <el-table-column label="记忆值" prop="memoryValue" width="400" show-overflow-tooltip/>
        <el-table-column label="分类" prop="category" width="100" align="center"/>
        <el-table-column label="重要度" width="150" align="center">
          <template #default="{ row }">
            <el-rate v-model="row.importance" disabled size="small"/>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180" align="center">
          <template #default="{ row }">
            {{ formatDateTime(row.updatedTime || row.createdTime) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right" align="center">
          <template #default="{ row }">
            <div style="display: flex;justify-content: center;gap: 8px;">
              <el-button text type="primary" @click="handleEdit(row)">编辑</el-button>
              <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <EmptyState
          v-if="!loading && !memoryList.length"
          title="暂无记忆"
          description="新增一条记忆，AI 助手将记住你的偏好"
      />
    </GlassCard>

    <!-- 编辑/新增弹窗 -->
    <el-dialog
        v-model="dialogVisible"
        :title="editingId ? '编辑记忆' : '新增记忆'"
        width="500px"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="记忆键">
          <el-input v-model="form.memoryKey" placeholder="如：偏好的无人机品牌"/>
        </el-form-item>
        <el-form-item label="记忆值">
          <el-input v-model="form.memoryValue" type="textarea" :rows="3" placeholder="如：大疆"/>
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" placeholder="如：preference"/>
        </el-form-item>
        <el-form-item label="重要度">
          <el-rate v-model="form.importance" :max="5" show-score/>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import {ref, reactive, onMounted} from 'vue'
import {ElMessage, ElMessageBox} from 'element-plus'
import PageHeader from '@/components/common/PageHeader.vue'
import GlassCard from '@/components/common/GlassCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import {aiApi} from '@/api/ai'

const loading = ref(false)
const saving = ref(false)
const memoryList = ref([])
const dialogVisible = ref(false)
const editingId = ref(null)

const form = reactive({
  memoryKey: '',
  memoryValue: '',
  category: 'general',
  importance: 5
})

const formatDateTime = (dt) => {
  if (!dt) return '-'
  return String(dt).replace('T', ' ').substring(0, 19)
}

const fetchList = async () => {
  loading.value = true
  try {
    const res = await aiApi.getMemories()
    memoryList.value = res.data || []
  } catch (e) {
    console.error('获取记忆列表失败:', e)
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.memoryKey = ''
  form.memoryValue = ''
  form.category = 'general'
  form.importance = 5
  editingId.value = null
}

const handleAdd = () => {
  resetForm()
  dialogVisible.value = true
}

const handleEdit = (row) => {
  editingId.value = row.id
  form.memoryKey = row.memoryKey
  form.memoryValue = row.memoryValue
  form.category = row.category || 'general'
  form.importance = row.importance || 5
  dialogVisible.value = true
}

const handleSave = async () => {
  if (!form.memoryKey.trim() || !form.memoryValue.trim()) {
    ElMessage.warning('记忆键和记忆值不能为空')
    return
  }
  saving.value = true
  try {
    await aiApi.saveMemory({
      memoryKey: form.memoryKey.trim(),
      memoryValue: form.memoryValue.trim(),
      category: form.category || 'general',
      importance: form.importance
    })
    ElMessage.success({ message: '保存成功', duration: 1000 })
    dialogVisible.value = false
    fetchList()
  } catch (e) {
    // 错误已处理
  } finally {
    saving.value = false
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定删除该记忆？', '删除确认', {type: 'warning'})
    await aiApi.deleteMemory(row.id)
    ElMessage.success('删除成功')
    fetchList()
  } catch { /* empty */ }
}

onMounted(() => {
  fetchList()
})
</script>

<style lang="scss" scoped>
.ai-memory-page {
  min-height: 100%;
}

.memory-card {
  .memory-header {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 16px;
  }
}
</style>
