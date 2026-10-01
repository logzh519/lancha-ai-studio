<script setup lang="ts">
import { request, useSessionStore } from '@shared/core'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import ParticleField from '../components/ParticleField.vue'

const session = useSessionStore()
const route = useRoute()
const error = ref((route.query.error as string) ?? '')
// 三态：检测中 / 已配置 / 未配置；请求本身失败单独用 configFailed 表示，避免把“后端挂了”说成“没配置”
const feishuConfigured = ref(false)
const checking = ref(true)
const configFailed = ref(false)
const starting = ref(false)

onMounted(async () => {
  try {
    const config = await request<{ feishu_configured: boolean }>('/platform/auth/config')
    feishuConfigured.value = config.feishu_configured
  } catch {
    configFailed.value = true
  } finally {
    checking.value = false
  }
})

async function login(): Promise<void> {
  starting.value = true
  error.value = ''
  try {
    await session.startFeishuLogin()
  } catch (e) {
    error.value = (e as Error).message
    starting.value = false
  }
}
</script>

<template>
  <main class="login">
    <ParticleField />
    <header class="topbar">
      <span class="mark">L</span>
      <strong>lancha-ai-studio</strong>
    </header>
    <section class="copy">
      <h1>AI 内容<br />生产与运营平台</h1>
    </section>
    <section class="panel">
      <div class="panel-mark" aria-hidden="true"><span>飞</span></div>
      <h2>飞书登录</h2>
      <button type="button" :disabled="starting || !feishuConfigured" @click="login">
        {{ starting ? '正在打开飞书…' : '飞书登录' }}
      </button>
      <p v-if="configFailed" class="notice">无法连接后端服务，请确认后端已启动后刷新页面。</p>
      <p v-else-if="!checking && !feishuConfigured" class="notice">后端尚未配置飞书应用，请联系管理员。</p>
      <p v-if="error" class="notice">{{ error }}</p>
    </section>
  </main>
</template>

<style scoped>
.login {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 420px);
  align-items: center;
  min-height: 100vh;
  gap: clamp(32px, 6vw, 112px);
  padding: 108px clamp(32px, 8vw, 152px) 64px;
  background: #161d28;
}

.topbar {
  position: absolute;
  top: 28px;
  left: clamp(32px, 8vw, 152px);
  display: inline-flex;
  align-items: center;
  gap: 11px;
  color: rgba(255, 255, 255, 0.92);
  font-size: 15px;
}

.mark {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 7px;
  background: #255fd0;
  color: #fff;
  font-weight: 900;
}

.copy,
.panel {
  position: relative;
}

.copy h1 {
  max-width: 700px;
  color: #fff;
  font-size: 46px;
  line-height: 1.18;
}

.panel {
  justify-self: end;
  width: 100%;
  padding: 34px;
  border: 1px solid rgba(184, 203, 237, 0.2);
  border-radius: 10px;
  background: #242b35;
  box-shadow: 0 22px 54px rgba(0, 0, 0, 0.24);
}

.panel-mark span {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 9px;
  background: #255fd0;
  color: #fff;
  font-weight: 900;
}

.panel h2 {
  margin: 18px 0 22px;
  color: #fff;
  font-size: 22px;
}

.panel button {
  width: 100%;
  height: 42px;
  border: 0;
  border-radius: 7px;
  background: #255fd0;
  color: #fff;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
}

.panel button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.notice {
  margin: 14px 0 0;
  color: #ff9c9c;
  font-size: 13px;
  line-height: 1.7;
}

@media (max-width: 960px) {
  .login {
    grid-template-columns: 1fr;
    padding: 100px 28px 42px;
  }

  .panel {
    justify-self: stretch;
  }

  .copy h1 {
    font-size: 34px;
  }
}
</style>
