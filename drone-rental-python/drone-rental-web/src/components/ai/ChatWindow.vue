<template>
  <div class="chat-window">
    <!-- 移动端侧边栏遮罩 -->
    <div
        v-if="sidebarVisible"
        class="chat-window__overlay"
        @click="sidebarVisible = false"
    />
    <!-- 侧边栏: 会话列表 -->
    <div class="chat-window__sidebar" :class="{ 'is-open': sidebarVisible }">
      <div class="chat-window__sidebar-header">
        <span>会话</span>
        <el-button text size="small" @click="handleNewSession">+ 新建</el-button>
      </div>
      <div class="chat-window__session-list">
        <div
            v-for="s in sessions"
            :key="s.id"
            class="chat-window__session-item"
            :class="{ active: s.id === sessionId }"
            @click="handleSwitchSessionMobile(s.id)"
        >
          <span v-if="editingId !== s.id" class="session-title">{{ s.title }}</span>
          <input
              v-else
              v-model="editingTitle"
              class="session-title-input"
              @blur="handleRenameConfirm(s.id)"
              @keyup.enter="handleRenameConfirm(s.id)"
              @keyup.escape="editingId = null"
              ref="titleInput"
          />
          <span class="session-actions">
            <el-button text size="small" class="session-action" @click.stop="handleRenameStart(s)">✏</el-button>
            <el-button text size="small" class="session-action" @click.stop="handleDeleteSession(s.id)">×</el-button>
          </span>
        </div>
        <div v-if="!sessions.length" class="chat-window__empty-sessions">
          暂无会话
        </div>
      </div>
    </div>

    <!-- 主聊天区 -->
    <div class="chat-window__main">
      <div class="chat-window__header">
        <el-button class="chat-window__menu-btn" text @click="sidebarVisible = true">
          <el-icon>
            <Menu/>
          </el-icon>
        </el-button>
        <span>AI 智能助手</span>
        <el-button text @click="handleClear">清空对话</el-button>
      </div>
      <div class="chat-window__messages" ref="messagesRef">
        <div v-if="!messages.length" class="chat-window__welcome">
          <div class="welcome-icon">🌻</div>
          <div class="welcome-title">你好，我是小葵</div>
          <div class="welcome-desc">我可以帮你推荐无人机、识别无人机照片、查询订单、引导报修等</div>
          <div class="welcome-hints">
            <span @click="handleSend('推荐一台适合航拍的无人机')">推荐航拍无人机</span>
            <span @click="handleSend('查一下我的订单状态')">查看订单</span>
            <span @click="handleSend('我想了解一下租赁流程')">租赁流程</span>
          </div>
        </div>
        <ChatMessage
            v-for="(msg, index) in messages"
            :key="index"
            :message="msg"
        />
        <div v-if="loading && !streaming" class="chat-window__typing">
          <span class="dot"/><span class="dot"/><span class="dot"/>
        </div>
      </div>
      <ChatInput :loading="loading" @send="handleSend"/>
    </div>
  </div>
</template>

<script setup>
import {ref, nextTick, watch, onMounted, onBeforeUnmount} from 'vue'
import {storeToRefs} from 'pinia'
import {Menu} from '@element-plus/icons-vue'
import ChatMessage from './ChatMessage.vue'
import ChatInput from './ChatInput.vue'
import {useAiStore} from '@/stores/ai'

const aiStore = useAiStore()
const {messages, loading, streaming, sessions, sessionId} = storeToRefs(aiStore)
const messagesRef = ref(null)
const editingId = ref(null)
const editingTitle = ref('')
const titleInput = ref(null)
const sidebarVisible = ref(false)

function scrollMessagesToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

watch(messages, () => scrollMessagesToBottom(), {deep: true})

onMounted(() => {
  aiStore.restoreOnMount()
})

onBeforeUnmount(() => {
  aiStore.cancelStream()
})

function handleSend(payload) {
  aiStore.sendMessage(payload)
}

function handleClear() {
  aiStore.clearChat()
}

function handleNewSession() {
  aiStore.initSession()
}

function handleSwitchSession(sid) {
  aiStore.switchSession(sid)
}

function handleSwitchSessionMobile(sid) {
  aiStore.switchSession(sid)
  sidebarVisible.value = false
}

function handleDeleteSession(sid) {
  aiStore.deleteSession(sid)
}

function handleRenameStart(session) {
  editingId.value = session.id
  editingTitle.value = session.title
  nextTick(() => {
    const input = document.querySelector('.session-title-input')
    if (input) input.focus()
  })
}

async function handleRenameConfirm(sid) {
  const newTitle = editingTitle.value.trim()
  if (newTitle) {
    await aiStore.renameSession(sid, newTitle)
  }
  editingId.value = null
}
</script>

<style scoped lang="scss">
.chat-window {
  display: flex;
  height: 100%;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
  position: relative;

  // 移动端遮罩
  &__overlay {
    display: none;
  }

  &__menu-btn {
    display: none;
  }

  // ── 侧边栏 ──
  &__sidebar {
    width: 220px;
    border-right: 1px solid #e4e7ed;
    display: flex;
    flex-direction: column;
    background: #fafafa;
    flex-shrink: 0;
  }

  &__sidebar-header {
    padding: 12px 16px;
    font-weight: 600;
    font-size: 14px;
    border-bottom: 1px solid #e4e7ed;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  &__session-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  &__session-item {
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 13px;
    transition: background 0.15s;

    &:hover {
      background: #e8e8e8;
    }

    &.active {
      background: #d0e4ff;
      font-weight: 500;
    }

    .session-title {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .session-actions {
      display: flex;
      gap: 4px;
      opacity: 0;
      transition: opacity 0.15s;
    }

    &:hover .session-actions {
      opacity: 1;
    }

    .session-action {
      font-size: 16px;
      color: #909399;
      padding: 4px 6px;
      border-radius: 4px;

      &:hover {
        color: #409eff;
        background: rgba(64, 158, 255, 0.1);
      }
    }

    .session-title-input {
      flex: 1;
      border: 1px solid #409eff;
      border-radius: 4px;
      padding: 2px 6px;
      font-size: 13px;
      outline: none;
    }
  }

  &__empty-sessions {
    text-align: center;
    color: #c0c4cc;
    font-size: 13px;
    padding: 32px 0;
  }

  // ── 主聊天区 ──
  &__main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__header {
    padding: 16px;
    font-weight: 600;
    border-bottom: 1px solid #e4e7ed;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  &__messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  // ── 欢迎屏 ──
  &__welcome {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    text-align: center;
    color: #606266;
  }

  .welcome-icon {
    font-size: 48px;
    margin-bottom: 12px;
  }

  .welcome-title {
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 8px;
  }

  .welcome-desc {
    font-size: 14px;
    color: #909399;
    margin-bottom: 20px;
  }

  .welcome-hints {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: center;

    span {
      padding: 8px 16px;
      border: 1px solid #dcdfe6;
      border-radius: 20px;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        border-color: #409eff;
        color: #409eff;
        background: #ecf5ff;
      }
    }
  }

  // ── 打字指示器 ──
  &__typing {
    display: flex;
    gap: 4px;
    padding: 8px;

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #909399;
      animation: bounce 1.4s infinite;

      &:nth-child(2) {
        animation-delay: 0.2s;
      }

      &:nth-child(3) {
        animation-delay: 0.4s;
      }
    }
  }
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-8px);
  }
}

// ── 移动端适配 ──
@media (max-width: 768px) {
  .chat-window {
    &__overlay {
      display: block;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.4);
      z-index: 10;
    }

    &__sidebar {
      position: absolute;
      top: 0;
      left: 0;
      bottom: 0;
      width: 70%;
      max-width: 260px;
      z-index: 20;
      transform: translateX(-100%);
      transition: transform 0.25s ease;

      &.is-open {
        transform: translateX(0);
        box-shadow: 2px 0 12px rgba(0, 0, 0, 0.15);
      }
    }

    &__menu-btn {
      display: inline-flex;
    }

    &__header {
      padding: 12px;
    }

    &__messages {
      padding: 12px;
    }

    .welcome-hints {
      flex-direction: column;
      width: 100%;

      span {
        width: 100%;
        text-align: center;
      }
    }
  }
}
</style>
