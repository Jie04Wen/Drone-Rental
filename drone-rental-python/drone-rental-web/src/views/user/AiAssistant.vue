<template>
  <div class="ai-assistant-page">
    <div class="ai-assistant-toolbar">
      <router-link to="/ai-memory" class="memory-link">记忆管理</router-link>
    </div>
    <ChatWindow/>
  </div>
</template>

<script setup>
import ChatWindow from '@/components/ai/ChatWindow.vue'
</script>

<style scoped lang="scss">
.ai-assistant-page {
  height: calc(100vh - 120px);
  padding: 24px;
  display: flex;
  flex-direction: column;

  :deep(.chat-window) {
    flex: 1;
    min-height: 0;
  }
}

.ai-assistant-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;

  .memory-link {
    color: #3b82f6;
    font-size: 14px;
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }
}

@media (max-width: 768px) {
  .ai-assistant-page {
    height: calc(100vh - 80px);
    padding: 12px;
  }
}
</style>
