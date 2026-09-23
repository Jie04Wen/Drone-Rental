<template>
  <div class="chat-input">
    <div v-if="previewUrl" class="chat-input__preview">
      <img
          :src="previewUrl"
          class="chat-input__preview-image"
          alt="待识别无人机照片"
      />

      <div class="chat-input__preview-info">
        <span class="chat-input__preview-name">
          {{ selectedFile?.name }}
        </span>
        <span class="chat-input__preview-size">
          {{ formattedFileSize }}
        </span>
      </div>

      <button
          type="button"
          class="chat-input__preview-remove"
          :disabled="loading"
          aria-label="移除图片"
          @click="clearSelectedImage"
      >
        <el-icon>
          <Close/>
        </el-icon>
      </button>
    </div>

    <div
        class="chat-input__box"
        :class="{
        'is-loading': loading,
        'is-focused': focused,
      }"
    >
      <input
          ref="fileInputRef"
          type="file"
          hidden
          accept="image/jpeg,image/png,image/gif,image/webp"
          @change="handleFileChange"
      />

      <button
          type="button"
          class="chat-input__image-button"
          :disabled="loading"
          title="上传无人机照片"
          @click="openFilePicker"
      >
        <el-icon :size="19">
          <Picture/>
        </el-icon>
      </button>

      <textarea
          ref="textareaRef"
          v-model="inputText"
          class="chat-input__field"
          :placeholder="
          loading
            ? 'AI 正在识别或思考...'
            : '输入问题或上传无人机照片，Enter 发送'
        "
          :disabled="loading"
          rows="1"
          @focus="focused = true"
          @blur="focused = false"
          @keydown="handleKeydown"
          @input="autoResize"
      />

      <button
          type="button"
          class="chat-input__send"
          :class="{ 'is-active': canSend }"
          :disabled="!canSend"
          @click="handleSend"
      >
        <el-icon v-if="!loading" :size="18">
          <Promotion/>
        </el-icon>
        <span v-else class="chat-input__spinner"/>
      </button>
    </div>

    <div class="chat-input__tip">
      上传支持 JPEG、PNG、GIF、WebP，最大 10MB；图片临时保存 24 小时；AI 识别结果仅供参考，不保证完全准确。
    </div>
  </div>
</template>

<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
} from 'vue'
import {ElMessage} from 'element-plus'
import {
  Close,
  Picture,
  Promotion,
} from '@element-plus/icons-vue'

const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const ALLOWED_IMAGE_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
])

const props = defineProps({
    loading: {
        type: Boolean,
        default: false,
    },
})

const emit = defineEmits(['send'])

const inputText = ref('')
const selectedFile = ref(null)
const previewUrl = ref('')
const textareaRef = ref(null)
const fileInputRef = ref(null)
const focused = ref(false)

const canSend = computed(() => {
  return (
      Boolean(inputText.value.trim() || selectedFile.value) && !props.loading
  )
})

const formattedFileSize = computed(() => {
  const size = selectedFile.value?.size || 0

  if (size < 1024) {
    return `${size} B`
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }

  return `${(size / 1024 / 1024).toFixed(1)} MB`
})

function openFilePicker() {
  if (!props.loading) {
    fileInputRef.value?.click()
  }
}

function handleFileChange(event) {
  const file = event.target.files?.[0]

  // 允许再次选择同一个文件。
  event.target.value = ''

  if (!file) {
    return
  }

  if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
    ElMessage.warning(
        '仅支持 JPEG、PNG、GIF 和 WebP 图片'
    )
    return
  }

  if (file.size > MAX_IMAGE_BYTES) {
    ElMessage.warning('图片大小不能超过10MB')
    return
  }

  clearPreviewUrl()

  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
}

function clearPreviewUrl() {
  if (
      previewUrl.value &&
      previewUrl.value.startsWith('blob:')
  ) {
    URL.revokeObjectURL(previewUrl.value)
  }

  previewUrl.value = ''
}

function clearSelectedImage() {
  clearPreviewUrl()
  selectedFile.value = null
}

function autoResize() {
  const element = textareaRef.value

  if (!element) {
    return
  }

  element.style.height = 'auto'
  element.style.height = `${Math.min(
      element.scrollHeight,
      120
  )}px`
}

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

function handleSend() {
  const text = inputText.value.trim()
  const image = selectedFile.value

  if ((!text && !image) || props.loading) {
    return
  }

  emit('send', {
    text,
    image,
  })

  inputText.value = ''
  clearSelectedImage()

  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

onBeforeUnmount(() => {
  clearPreviewUrl()
})
</script>

<style scoped lang="scss">
.chat-input {
  padding: 10px 16px 14px;
  border-top: 1px solid #e4e7ed;
  background: #fafafa;

  &__preview {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    width: min(360px, 100%);
    margin-bottom: 10px;
    padding: 8px 38px 8px 8px;
    border: 1px solid #dbeafe;
    border-radius: 12px;
    background: #fff;
  }

  &__preview-image {
    width: 64px;
    height: 64px;
    flex-shrink: 0;
    object-fit: cover;
    border-radius: 8px;
    background: #f2f3f5;
  }

  &__preview-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  &__preview-name {
    overflow: hidden;
    color: #303133;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__preview-size {
    margin-top: 4px;
    color: #909399;
    font-size: 12px;
  }

  &__preview-remove {
    position: absolute;
    top: 6px;
    right: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border: none;
    border-radius: 50%;
    color: #909399;
    background: transparent;
    cursor: pointer;

    &:hover {
      color: #f56c6c;
      background: #fef0f0;
    }
  }

  &__box {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    padding: 6px;
    border: 1px solid #dcdfe6;
    border-radius: 24px;
    background: #fff;
    transition: border-color 0.2s,
    box-shadow 0.2s;

    &.is-focused {
      border-color: #409eff;
      box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.12);
    }

    &.is-loading {
      background: #f5f7fa;
    }
  }

  &__image-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    flex-shrink: 0;
    border: none;
    border-radius: 50%;
    color: #606266;
    background: transparent;
    cursor: pointer;

    &:hover:not(:disabled) {
      color: #409eff;
      background: #ecf5ff;
    }

    &:disabled {
      color: #c0c4cc;
      cursor: not-allowed;
    }
  }

  &__field {
    flex: 1;
    min-width: 0;
    min-height: 24px;
    max-height: 120px;
    padding: 6px 0;
    border: none;
    outline: none;
    resize: none;
    color: #303133;
    background: transparent;
    font-family: inherit;
    font-size: 14px;
    line-height: 1.5;

    &::placeholder {
      color: #a8abb2;
    }

    &:disabled {
      color: #a8abb2;
      cursor: not-allowed;
    }
  }

  &__send {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    flex-shrink: 0;
    border: none;
    border-radius: 50%;
    color: #fff;
    background: #e4e7ed;
    cursor: not-allowed;
    transition: background 0.2s,
    transform 0.15s;

    &.is-active {
      background: #409eff;
      cursor: pointer;

      &:hover {
        background: #66b1ff;
      }

      &:active {
        transform: scale(0.94);
      }
    }
  }

  &__spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.35);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  &__tip {
    margin-top: 6px;
    padding-left: 8px;
    color: #a8abb2;
    font-size: 11px;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .chat-input {
    padding: 8px 10px 10px;

    &__tip {
      display: none;
    }
  }
}
</style>