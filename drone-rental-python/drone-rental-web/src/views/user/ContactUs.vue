<template>
  <div class="contact-page">
    <div class="contact-header">
      <h1>联系我们</h1>
      <p>如有任何问题，欢迎随时联系我们</p>
    </div>

    <div class="contact-grid">
      <div class="contact-card">
        <div class="contact-card__icon">
          <el-icon :size="32">
            <Phone/>
          </el-icon>
        </div>
        <h3>客服热线</h3>
        <p class="contact-card__value">400-888-8888</p>
        <p class="contact-card__desc">工作日 9:00 - 18:00</p>
      </div>

      <div class="contact-card">
        <div class="contact-card__icon">
          <el-icon :size="32">
            <Message/>
          </el-icon>
        </div>
        <h3>电子邮箱</h3>
        <p class="contact-card__value">email@email.com</p>
        <p class="contact-card__desc">24 小时内回复</p>
      </div>

      <div class="contact-card">
        <div class="contact-card__icon">
          <el-icon :size="32">
            <Location/>
          </el-icon>
        </div>
        <h3>公司地址</h3>
        <p class="contact-card__value">浙江省 杭州市 浙江工业大学</p>
        <p class="contact-card__desc">欢迎预约参观</p>
      </div>
    </div>

    <div class="contact-section">
      <h2>在线留言</h2>
      <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="您的姓名" prop="name">
              <el-input v-model="form.name" placeholder="请输入姓名"/>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系电话" prop="phone">
              <el-input v-model="form.phone" placeholder="请输入手机号"/>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="电子邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱（选填）"/>
        </el-form-item>
        <el-form-item label="留言内容" prop="message">
          <el-input v-model="form.message" type="textarea" :rows="5" placeholder="请描述您的问题或需求"/>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" @click="handleSubmit" :loading="loading">
            提交留言
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="contact-section">
      <h2>常见问题</h2>
      <div class="contact-quick-links">
        <router-link to="/faq" class="contact-quick-link">
          <el-icon>
            <QuestionFilled/>
          </el-icon>
          查看常见问题
        </router-link>
        <router-link to="/rental-guide" class="contact-quick-link">
          <el-icon>
            <Document/>
          </el-icon>
          查看租赁指南
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import {ref, reactive} from 'vue'
import {Phone, Message, Location, QuestionFilled, Document} from '@element-plus/icons-vue'
import {ElMessage} from 'element-plus'

const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  name: '',
  phone: '',
  email: '',
  message: ''
})

const rules = {
  name: [{required: true, message: '请输入姓名', trigger: 'blur'}],
  phone: [
    {required: true, message: '请输入手机号', trigger: 'blur'},
    {pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur'}
  ],
  message: [{required: true, message: '请输入留言内容', trigger: 'blur'}]
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate((valid) => {
    if (!valid) return
    loading.value = true
    setTimeout(() => {
      ElMessage.success('留言提交成功，我们会尽快与您联系！')
      formRef.value.resetFields()
      loading.value = false
    }, 1000)
  })
}
</script>

<style lang="scss" scoped>
.contact-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 40px 24px;
}

.contact-header {
  text-align: center;
  margin-bottom: 48px;

  h1 {
    font-size: 32px;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 12px;
  }

  p {
    font-size: 16px;
    color: #64748b;
    margin: 0;
  }
}

.contact-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 56px;
}

.contact-card {
  text-align: center;
  padding: 32px 20px;
  background: #fff;
  border-radius: 16px;
  border: 1px solid #f1f5f9;
  transition: box-shadow 0.3s, transform 0.3s;

  &:hover {
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
    transform: translateY(-2px);
  }

  &__icon {
    width: 64px;
    height: 64px;
    margin: 0 auto 16px;
    border-radius: 50%;
    background: rgba(59, 130, 246, 0.1);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #3b82f6;
  }

  h3 {
    font-size: 16px;
    font-weight: 600;
    color: #0f172a;
    margin: 0 0 8px;
  }

  &__value {
    font-size: 15px;
    font-weight: 500;
    color: #3b82f6;
    margin: 0 0 4px;
  }

  &__desc {
    font-size: 13px;
    color: #94a3b8;
    margin: 0;
  }
}

.contact-section {
  margin-bottom: 48px;

  h2 {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 24px;
  }
}

.contact-quick-links {
  display: flex;
  gap: 16px;
}

.contact-quick-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  color: #3b82f6;
  text-decoration: none;
  border: 1px solid #bfdbfe;
  transition: all 0.2s;

  &:hover {
    background: #eff6ff;
  }
}

@media (max-width: 640px) {
  .contact-grid {
    grid-template-columns: 1fr;
  }
}
</style>
