<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'

export type ConfirmType = 'danger' | 'warning' | 'info'

interface Props {
  open?: boolean
  title?: string
  message?: string
  type?: ConfirmType
  confirmText?: string
  cancelText?: string
  confirmLoading?: boolean
  showCancel?: boolean
  showClose?: boolean
  closeOnClickOverlay?: boolean
  closeOnEsc?: boolean
  teleport?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  title: '确认提示',
  message: '',
  type: 'warning',
  confirmText: '确定',
  cancelText: '取消',
  confirmLoading: false,
  showCancel: true,
  showClose: true,
  closeOnClickOverlay: true,
  closeOnEsc: true,
  teleport: true,
})

const emit = defineEmits<{
  (e: 'update:open', val: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
  (e: 'after-leave'): void
}>()

function handleConfirm(): void {
  if (props.confirmLoading) return
  emit('confirm')
}

function handleCancel(): void {
  if (props.confirmLoading) return
  emit('update:open', false)
  emit('cancel')
}

function handleOverlayClick(): void {
  if (props.closeOnClickOverlay) {
    handleCancel()
  }
}

function handleKeydown(e: KeyboardEvent): void {
  if (props.open && props.closeOnEsc && e.key === 'Escape') {
    handleCancel()
  }
}

let originalOverflow = ''

watch(
  () => props.open,
  (isOpen) => {
    if (typeof document === 'undefined') return
    if (isOpen) {
      originalOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = originalOverflow
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', handleKeydown)
  }
})

onUnmounted(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', handleKeydown)
  }
  if (typeof document !== 'undefined' && props.open) {
    document.body.style.overflow = originalOverflow
  }
})
</script>

<template>
  <Teleport to="body" :disabled="!teleport">
    <Transition name="confirm-fade" @after-leave="emit('after-leave')">
      <div
        v-if="open"
        class="confirm-overlay"
        role="dialog"
        aria-modal="true"
        @click.self="handleOverlayClick"
      >
        <div class="confirm-card" :class="[`is-${type}`]">
          <button
            v-if="showClose"
            type="button"
            class="confirm-close-btn"
            aria-label="关闭"
            @click="handleCancel"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>

          <div class="confirm-content-wrap">
            <div class="confirm-icon-box" :class="[`type-${type}`]">
              <!-- Danger Icon -->
              <svg
                v-if="type === 'danger'"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>

              <!-- Warning Icon -->
              <svg
                v-else-if="type === 'warning'"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>

              <!-- Info Icon -->
              <svg
                v-else
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
            </div>

            <div class="confirm-text-area">
              <h3 class="confirm-title">{{ title }}</h3>
              <div class="confirm-message">
                <slot>{{ message }}</slot>
              </div>
            </div>
          </div>

          <div class="confirm-actions">
            <button
              v-if="showCancel"
              type="button"
              class="confirm-btn btn-cancel"
              :disabled="confirmLoading"
              @click="handleCancel"
            >
              {{ cancelText }}
            </button>
            <button
              type="button"
              class="confirm-btn btn-action"
              :class="[`btn-${type}`]"
              :disabled="confirmLoading"
              @click="handleConfirm"
            >
              <span v-if="confirmLoading" class="btn-spinner" />
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-md, 16px);
}

.confirm-card {
  position: relative;
  width: 100%;
  max-width: 440px;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius-lg, 14px);
  border: 1px solid var(--color-border, #e2e8f0);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.confirm-close-btn {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm, 6px);
  color: var(--color-text-weak, #94a3b8);
  cursor: pointer;
  transition: all var(--transition-fast, 150ms);
}

.confirm-close-btn svg {
  width: 16px;
  height: 16px;
}

.confirm-close-btn:hover {
  background: var(--color-surface-subtle, #f1f5f9);
  color: var(--color-text, #0f172a);
}

.confirm-content-wrap {
  display: flex;
  gap: 16px;
  padding: 24px 24px 20px;
}

.confirm-icon-box {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.confirm-icon-box svg {
  width: 24px;
  height: 24px;
}

.confirm-icon-box.type-danger {
  background: var(--color-danger-light, #fef2f2);
  color: var(--color-danger, #ef4444);
}

.confirm-icon-box.type-warning {
  background: var(--color-warning-light, #fffbeb);
  color: var(--color-warning, #f59e0b);
}

.confirm-icon-box.type-info {
  background: var(--color-primary-light, #eff6ff);
  color: var(--color-primary, #2563eb);
}

.confirm-text-area {
  flex: 1;
  min-width: 0;
  padding-top: 2px;
}

.confirm-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text, #0f172a);
  line-height: 1.4;
}

.confirm-message {
  font-size: 14px;
  color: var(--color-text-muted, #475569);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.confirm-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 24px 18px;
  background: #fafbfc;
  border-top: 1px solid var(--color-border-subtle, #f1f5f9);
}

.confirm-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 500;
  border-radius: var(--radius, 8px);
  cursor: pointer;
  transition: all var(--transition-fast, 150ms);
  border: 1px solid transparent;
}

.confirm-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-cancel {
  background: #ffffff;
  border-color: var(--color-border, #e2e8f0);
  color: var(--color-text-muted, #475569);
}

.btn-cancel:hover:not(:disabled) {
  background: var(--color-surface-subtle, #f1f5f9);
  color: var(--color-text, #0f172a);
  border-color: var(--color-border-hover, #cbd5e1);
}

.btn-action.btn-danger {
  background: var(--color-danger, #ef4444);
  color: #ffffff;
  box-shadow: 0 1px 2px 0 rgba(239, 68, 68, 0.2);
}

.btn-action.btn-danger:hover:not(:disabled) {
  background: #dc2626;
}

.btn-action.btn-warning {
  background: var(--color-warning, #f59e0b);
  color: #ffffff;
  box-shadow: 0 1px 2px 0 rgba(245, 158, 11, 0.2);
}

.btn-action.btn-warning:hover:not(:disabled) {
  background: #d97706;
}

.btn-action.btn-info {
  background: var(--color-primary, #2563eb);
  color: #ffffff;
  box-shadow: 0 1px 2px 0 rgba(37, 99, 235, 0.2);
}

.btn-action.btn-info:hover:not(:disabled) {
  background: var(--color-primary-hover, #1d4ed8);
}

.btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 动效 */
.confirm-fade-enter-active,
.confirm-fade-leave-active {
  transition: opacity 0.2s ease;
}

.confirm-fade-enter-active .confirm-card,
.confirm-fade-leave-active .confirm-card {
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s ease;
}

.confirm-fade-enter-from,
.confirm-fade-leave-to {
  opacity: 0;
}

.confirm-fade-enter-from .confirm-card,
.confirm-fade-leave-to .confirm-card {
  opacity: 0;
  transform: scale(0.95) translateY(-8px);
}
</style>
