<template>
  <div class="faq-page">
    <div class="faq-header">
      <h1>常见问题</h1>
      <p>找不到答案？请联系我们获取帮助</p>
    </div>

    <div class="faq-search">
      <el-input
          v-model="searchText"
          placeholder="搜索问题..."
          :prefix-icon="Search"
          size="large"
          clearable
      />
    </div>

    <div class="faq-list">
      <div v-for="(group, i) in filteredGroups" :key="i" class="faq-group">
        <h2>{{ group.title }}</h2>
        <div v-for="(item, j) in group.items" :key="j" class="faq-item">
          <div class="faq-item__q" @click="toggle(i, j)">
            <span>{{ item.q }}</span>
            <el-icon :class="{ 'is-open': isOpen(i, j) }">
              <ArrowDown/>
            </el-icon>
          </div>
          <Transition name="expand">
            <div v-if="isOpen(i, j)" class="faq-item__a">
              <p>{{ item.a }}</p>
            </div>
          </Transition>
        </div>
      </div>

      <el-empty v-if="filteredGroups.length === 0" description="未找到相关问题"/>
    </div>
  </div>
</template>

<script setup>
import {ref, computed} from 'vue'
import {Search, ArrowDown} from '@element-plus/icons-vue'

const searchText = ref('')
const openSet = ref(new Set())

const groups = [
  {
    title: '注册与登录',
    items: [
      {
        q: '如何注册账号？',
        a: '在首页点击"注册"按钮，填写用户名、密码、手机号等信息即可完成注册。注册后建议立即提交飞行资质认证。'
      },
      {q: '忘记密码怎么办？', a: '目前请联系我们客服重置密码。后续版本将支持手机验证码找回密码。'},
      {
        q: '管理员账号和普通账号有什么区别？',
        a: '管理员账号可以访问后台管理系统，进行设备管理、订单审核、用户管理等操作。普通用户只能使用前台功能。'
      }
    ]
  },
  {
    title: '资质认证',
    items: [
      {
        q: '租赁无人机需要什么资质？',
        a: '需要持有民用无人驾驶航空器操控员执照或其他有效飞行资质证书。提交后由管理员审核，通常 1-2 个工作日完成。'
      },
      {q: '资质认证被拒绝了怎么办？', a: '请检查上传的证件是否清晰、是否在有效期内。可以重新提交符合要求的资质材料。'},
      {q: '资质认证有效期是多久？', a: '以您提交的证件有效期为准。过期后需要重新提交认证。'}
    ]
  },
  {
    title: '下单与支付',
    items: [
      {
        q: '如何下单租赁无人机？',
        a: '浏览设备详情页，选择租赁日期范围，确认费用后点击"立即租赁"。系统会自动计算租金并创建订单。'
      },
      {q: '支持哪些支付方式？', a: '目前支持支付宝（真实支付）、微信支付和余额支付。选择支付宝时会跳转到收银台完成付款。'},
      {q: '订单创建后可以取消吗？', a: '待支付状态的订单可以取消。已支付的订单需要联系客服处理退款。'},
      {q: '押金什么时候退还？', a: '归还设备并经管理员确认无损坏后，押金将自动退还至原支付账户。'}
    ]
  },
  {
    title: '设备与使用',
    items: [
      {
        q: '收到设备后发现有问题怎么办？',
        a: '请当场验货并拍照留证。如有问题立即在系统中提交故障报修，我们会安排换货或退款。'
      },
      {
        q: '租赁期间设备损坏了怎么办？',
        a: '请立即提交故障报修，描述故障情况并上传照片。我们会安排维修或更换，维修费用根据损坏程度确定。'
      },
      {q: '可以提前归还设备吗？', a: '可以。在系统中申请归还即可，剩余天数的租金按实际情况结算。'}
    ]
  },
  {
    title: '空域备案',
    items: [
      {q: '什么情况下需要空域备案？', a: '在管制区域、机场附近、军事禁区等特殊区域飞行时，需要提前提交空域备案并获得审批。'},
      {q: '空域备案审核需要多久？', a: '通常 1-3 个工作日。建议在计划飞行日期前至少 3 天提交备案申请。'},
      {q: '备案通过后有效期是多久？', a: '以您填写的计划飞行时间为准。超过有效期需重新提交备案。'}
    ]
  }
]

const isOpen = (gi, ii) => openSet.value.has(`${gi}-${ii}`)

const toggle = (gi, ii) => {
  const key = `${gi}-${ii}`
  const s = new Set(openSet.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  openSet.value = s
}

const filteredGroups = computed(() => {
  if (!searchText.value.trim()) return groups
  const kw = searchText.value.toLowerCase()
  return groups
      .map(g => ({
        title: g.title,
        items: g.items.filter(it => it.q.toLowerCase().includes(kw) || it.a.toLowerCase().includes(kw))
      }))
      .filter(g => g.items.length > 0)
})
</script>

<style lang="scss" scoped>
.faq-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 40px 24px;
}

.faq-header {
  text-align: center;
  margin-bottom: 32px;

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

.faq-search {
  margin-bottom: 40px;
}

.faq-list {
  display: flex;
  flex-direction: column;
  gap: 36px;
}

.faq-group {
  h2 {
    font-size: 18px;
    font-weight: 600;
    color: #0f172a;
    margin: 0 0 16px;
    padding-bottom: 12px;
    border-bottom: 2px solid #3b82f6;
    display: inline-block;
  }
}

.faq-item {
  border: 1px solid #f1f5f9;
  border-radius: 10px;
  margin-bottom: 8px;
  overflow: hidden;
  background: #fff;
  transition: box-shadow 0.2s;

  &:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }

  &__q {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    cursor: pointer;
    font-size: 15px;
    font-weight: 500;
    color: #334155;
    user-select: none;

    .el-icon {
      color: #94a3b8;
      transition: transform 0.2s;
      flex-shrink: 0;
      margin-left: 12px;

      &.is-open {
        transform: rotate(180deg);
        color: #3b82f6;
      }
    }
  }

  &__a {
    padding: 0 20px 16px;

    p {
      font-size: 14px;
      color: #64748b;
      line-height: 1.8;
      margin: 0;
    }
  }
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 200px;
}
</style>
