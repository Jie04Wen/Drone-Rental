<template>
  <div class="guide-page">
    <div class="guide-header">
      <h1>租赁指南</h1>
      <p>从注册到归还，轻松完成无人机租赁全流程</p>
    </div>

    <div class="guide-steps">
      <div v-for="(step, i) in steps" :key="i" class="guide-step">
        <div class="guide-step__number">{{ i + 1 }}</div>
        <div class="guide-step__content">
          <h3>{{ step.title }}</h3>
          <p>{{ step.desc }}</p>
          <ul v-if="step.tips">
            <li v-for="(tip, j) in step.tips" :key="j">{{ tip }}</li>
          </ul>
        </div>
      </div>
    </div>

    <div class="guide-section">
      <h2>租赁费用说明</h2>
      <div class="guide-table">
        <table>
          <thead>
          <tr>
            <th>费用项</th>
            <th>说明</th>
          </tr>
          </thead>
          <tbody>
          <tr>
            <td>日租金</td>
            <td>按无人机型号定价，从 149 元/天到 899 元/天不等</td>
          </tr>
          <tr>
            <td>押金</td>
            <td>下单时冻结，归还检查无误后自动退还</td>
          </tr>
          <tr>
            <td>逾期费用</td>
            <td>超过租赁期限按日租金 150% 收取</td>
          </tr>
          <tr>
            <td>损坏赔偿</td>
            <td>非正常磨损需按维修费用赔偿</td>
          </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="guide-section">
      <h2>温馨提示</h2>
      <div class="guide-tips">
        <div class="guide-tip">
          <el-icon :size="24">
            <Warning/>
          </el-icon>
          <div>
            <h4>资质要求</h4>
            <p>租赁前需提交飞行资质认证并通过审核，建议提前 1-2 天提交</p>
          </div>
        </div>
        <div class="guide-tip">
          <el-icon :size="24">
            <InfoFilled/>
          </el-icon>
          <div>
            <h4>空域备案</h4>
            <p>在管制区域飞行需提前完成空域备案，审核通过后方可飞行</p>
          </div>
        </div>
        <div class="guide-tip">
          <el-icon :size="24">
            <CircleCheck/>
          </el-icon>
          <div>
            <h4>设备检查</h4>
            <p>收到设备后请当场检查外观和功能，如有问题立即联系客服</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {Warning, InfoFilled, CircleCheck} from '@element-plus/icons-vue'

const steps = [
  {
    title: '注册账号',
    desc: '使用手机号注册账号，填写基本个人信息。',
    tips: ['支持手机号注册', '注册后即可浏览设备']
  },
  {
    title: '提交飞行资质',
    desc: '在个人中心提交飞行资质认证，上传证件照片等待审核。',
    tips: ['支持民用无人驾驶航空器操控员执照', '审核通常在 1-2 个工作日内完成', '资质有效期内无需重复提交']
  },
  {
    title: '浏览与选择设备',
    desc: '在设备浏览页面按品牌、类型、价格筛选合适的无人机。',
    tips: ['查看设备详细参数和用户评价', '关注库存状态和日租金价格']
  },
  {
    title: '提交空域备案（如需）',
    desc: '在管制区域飞行需提前提交空域备案，获得审批后方可飞行。',
    tips: ['填写飞行区域、时间、用途', '审核通过后绑定到订单']
  },
  {
    title: '下单租赁',
    desc: '选择租赁日期，确认费用后提交订单。',
    tips: ['系统自动计算租金和押金', '支持支付宝、微信、余额支付']
  },
  {
    title: '等待发货与收货',
    desc: '管理员发货后，等待快递送达并确认收货。',
    tips: ['收到设备后请当场验货', '发现问题及时联系客服']
  },
  {
    title: '使用与归还',
    desc: '在租赁期内使用设备，到期后在系统中申请归还。',
    tips: ['保持设备完好', '逾期将按日租金 150% 收取费用']
  },
  {
    title: '评价与反馈',
    desc: '归还设备后可对本次租赁体验进行评价。',
    tips: ['您的评价将帮助其他用户选择', '如有问题可联系客服处理']
  }
]
</script>

<style lang="scss" scoped>
.guide-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 40px 24px;
}

.guide-header {
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

.guide-steps {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-bottom: 56px;
}

.guide-step {
  display: flex;
  gap: 20px;
  position: relative;
  padding-bottom: 32px;

  &:last-child {
    padding-bottom: 0;

    &::before {
      display: none;
    }
  }

  &::before {
    content: '';
    position: absolute;
    left: 19px;
    top: 40px;
    bottom: 0;
    width: 2px;
    background: #e2e8f0;
  }

  &__number {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: #3b82f6;
    color: #fff;
    font-size: 16px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    position: relative;
    z-index: 1;
  }

  &__content {
    flex: 1;
    padding-top: 4px;

    h3 {
      font-size: 18px;
      font-weight: 600;
      color: #0f172a;
      margin: 0 0 8px;
    }

    p {
      font-size: 15px;
      color: #64748b;
      margin: 0 0 12px;
      line-height: 1.6;
    }

    ul {
      margin: 0;
      padding-left: 20px;

      li {
        font-size: 14px;
        color: #94a3b8;
        line-height: 1.8;
      }
    }
  }
}

.guide-section {
  margin-bottom: 48px;

  h2 {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 24px;
  }
}

.guide-table {
  table {
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  }

  th, td {
    padding: 14px 20px;
    text-align: left;
    border-bottom: 1px solid #f1f5f9;
  }

  th {
    background: #f8fafc;
    font-weight: 600;
    color: #475569;
    font-size: 14px;
  }

  td {
    font-size: 14px;
    color: #64748b;
  }

  tr:last-child td {
    border-bottom: none;
  }
}

.guide-tips {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.guide-tip {
  display: flex;
  gap: 14px;
  padding: 20px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #f1f5f9;

  .el-icon {
    color: #3b82f6;
    margin-top: 2px;
    flex-shrink: 0;
  }

  h4 {
    font-size: 15px;
    font-weight: 600;
    color: #0f172a;
    margin: 0 0 6px;
  }

  p {
    font-size: 13px;
    color: #94a3b8;
    margin: 0;
    line-height: 1.6;
  }
}
</style>
