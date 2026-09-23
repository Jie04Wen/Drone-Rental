<template>
  <div class="chat-message" :class="message.role">
    <div class="chat-message__avatar">
      <el-icon v-if="message.role === 'user'">
        <User/>
      </el-icon>
      <el-icon v-else>
        <ChatDotRound/>
      </el-icon>
    </div>
    <div class="chat-message__bubble" :class="{'has-image': message.imageUrl || message.imageExpired}">
      <div v-if="message.imageUrl && !imageLoadFailed" class="chat-message__image">
        <el-image
            :src="message.imageUrl"
            :preview-src-list="[message.imageUrl]"
            :initial-index="0"
            fit="cover"
            hide-on-click-modal
            preview-teleported
            alt="用户上传的无人机照片"
            @error="imageLoadFailed = true"
        />
      </div>
      <div
          v-else-if="message.imageExpired || imageLoadFailed"
          class="chat-message__image-expired"
      >
        <el-icon>
          <Picture/>
        </el-icon>
        <span>图片已过期或暂时无法加载</span>
      </div>
      <div v-if="message.role === 'assistant' && (message.content || message.streaming)"
           class="chat-message__content markdown-body">
        <div class="chat-message__markdown" v-html="renderedContent"/>
        <span v-if="message.streaming" class="chat-message__cursor">|</span>
      </div>
      <div v-else-if="message.content" class="chat-message__content">
        {{ message.content }}
      </div>
      <div v-if="message.model && !message.streaming" class="chat-message__meta">
        <span>{{ message.model }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import {computed, ref, watch} from 'vue'
import {
  ChatDotRound,
  Picture,
  User,
} from '@element-plus/icons-vue'
import {renderMarkdown} from '@/utils/markdown'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})
const imageLoadFailed = ref(false)
watch(
    () => props.message.imageUrl,
    () => {
      imageLoadFailed.value = false
    }
)
const renderedContent = computed(() => {
  return renderMarkdown(props.message.content || '')
})
</script>

<style scoped lang="scss">
.chat-message {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;

  &.user {
    flex-direction: row-reverse;

    .chat-message__bubble {
      background: #409eff;
      color: #fff;

      &.has-image {
        padding: 8px;
        color: #303133;
        background: #eaf3ff;
      }
    }
  }

  &.assistant .chat-message__bubble {
    max-width: 82%;
    background: #f8fafc;
    border: 1px solid #e5e7eb;
    color: #1f2937;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  }

  &__avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: #e4e7ed;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  &__bubble {
    max-width: 70%;
    min-width: 0;
    padding: 12px 16px;
    border-radius: 12px;
    line-height: 1.6;
  }

  &__content {
    word-break: break-word;

    &.markdown-body {
      line-height: 1.75;
    }

    .chat-message__markdown {
      min-width: 0;
      overflow-x: auto;
    }

    &.markdown-body :deep(p) {
      margin: 0 0 8px;

      &:last-child {
        margin-bottom: 0;
      }
    }

    &.markdown-body :deep(h1),
    &.markdown-body :deep(h2),
    &.markdown-body :deep(h3),
    &.markdown-body :deep(h4) {
      margin: 12px 0 8px;
      font-weight: 600;
      line-height: 1.4;

      &:first-child {
        margin-top: 0;
      }
    }

    &.markdown-body :deep(h1) {
      font-size: 1.25em;
    }

    &.markdown-body :deep(h2) {
      font-size: 1.15em;
    }

    &.markdown-body :deep(h3) {
      font-size: 1.05em;
    }

    &.markdown-body :deep(ul),
    &.markdown-body :deep(ol) {
      margin: 4px 0 8px;
      padding-left: 1.4em;
    }

    &.markdown-body :deep(li) {
      margin: 4px 0;
    }

    &.markdown-body :deep(li::marker) {
      color: #3b82f6;
      font-weight: 600;
    }

    &.markdown-body :deep(strong) {
      color: #111827;
      font-weight: 650;
    }

    &.markdown-body :deep(blockquote) {
      margin: 8px 0;
      padding: 4px 12px;
      border-left: 3px solid #c0c4cc;
      color: #606266;
    }

    &.markdown-body :deep(code) {
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(0, 0, 0, 0.06);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.9em;
    }

    &.markdown-body :deep(pre) {
      margin: 8px 0;
      padding: 12px;
      border-radius: 8px;
      background: #1e1e1e;
      overflow-x: auto;

      code {
        padding: 0;
        background: none;
        color: #e6e6e6;
        font-size: 0.85em;
      }
    }

    &.markdown-body :deep(a) {
      color: #409eff;
      text-decoration: none;

      &:hover {
        text-decoration: underline;
      }
    }

    &.markdown-body :deep(table) {
      border-collapse: collapse;
      width: 100%;
      min-width: 520px;
      margin: 12px 0;
      font-size: 0.9em;
      background: #fff;
      border-radius: 8px;
    }

    &.markdown-body :deep(th),
    &.markdown-body :deep(td) {
      border: 1px solid #dcdfe6;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }

    &.markdown-body :deep(th) {
      background: #eef4ff;
      color: #1e3a5f;
      font-weight: 600;
    }

    &.markdown-body :deep(hr) {
      margin: 12px 0;
      border: none;
      border-top: 1px solid #dcdfe6;
    }
  }

  &__meta {
    margin-top: 4px;
    font-size: 12px;
    opacity: 0.6;
  }

  &__cursor {
    animation: blink 1s step-end infinite;
    font-weight: bold;
  }

  &__image {
    width: min(360px, 70vw);
    margin-bottom: 8px;
    overflow: hidden;
    border-radius: 10px;
    background: #f2f3f5;

    :deep(.el-image) {
      display: block;
      width: 100%;
      max-height: 280px;
    }

    :deep(img) {
      width: 100%;
      max-height: 280px;
      object-fit: cover;
    }
  }

  &__image-expired {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 220px;
    margin-bottom: 8px;
    padding: 14px;
    border: 1px dashed #dcdfe6;
    border-radius: 8px;
    color: #909399;
    background: #f5f7fa;
    font-size: 13px;
  }
}

@media (max-width: 768px) {
  .chat-message {
    gap: 8px;

    &__avatar {
      width: 32px;
      height: 32px;
    }

    &__bubble,
    &.assistant .chat-message__bubble {
      max-width: calc(100% - 40px);
      padding: 10px 12px;
    }
  }
}

@keyframes blink {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}
</style>
