<script setup lang="ts">
import { usePlatformStore, useSessionStore } from '@shared/core'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const platform = usePlatformStore()
const session = useSessionStore()
const route = useRoute()
const router = useRouter()

// 模块快速切换弹窗/下拉
const switcherOpen = ref(false)
const switcherSearch = ref('')
const switcherRef = ref<HTMLElement | null>(null)

function toggleSwitcher(): void {
  switcherOpen.value = !switcherOpen.value
  if (switcherOpen.value) {
    switcherSearch.value = ''
  }
}

function closeSwitcher(): void {
  switcherOpen.value = false
}

function handleGlobalClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null
  if (!target?.closest('.app-switcher-wrapper')) {
    closeSwitcher()
  }
}

onMounted(() => {
  window.addEventListener('click', handleGlobalClick)
})

onBeforeUnmount(() => {
  window.removeEventListener('click', handleGlobalClick)
})

// 当前路径状态判定
const isHome = computed(() => route.path === '/' || route.path === '')

const currentModuleKey = computed<string>(() => {
  const path = route.path
  if (path === '/' || path === '') return ''
  if (path.startsWith('/platform')) return 'platform'
  const segment = path.split('/')[1]
  return segment || ''
})

// 当前激活的模块对象
const activeModule = computed(() => {
  if (currentModuleKey.value === 'platform') {
    return {
      name: 'platform',
      title: '系统管理',
      icon: 'shield',
      gradient: 'linear-gradient(135deg, #475569 0%, #334155 100%)',
      menus: platform.platformMenus,
    }
  }
  const found = platform.modules.find((m) => m.name === currentModuleKey.value)
  if (!found) return null

  let gradient = 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)'
  if (found.name === 'tiktok') {
    gradient = 'linear-gradient(135deg, #111827 0%, #fe2c55 100%)'
  } else if (found.name === 'example_b') {
    gradient = 'linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)'
  }

  return {
    ...found,
    gradient,
  }
})

// 模块侧边栏或内导航菜单树
const currentModuleMenuTree = computed(() => {
  if (!currentModuleKey.value) return []
  if (currentModuleKey.value === 'platform') {
    return platform.platformMenus
  }
  const group = platform.menuTree.find((g) => g.module === currentModuleKey.value)
  return group ? group.children : []
})

// 切换器里的可用模块列表（支持搜索）
const switcherList = computed(() => {
  const kw = switcherSearch.value.trim().toLowerCase()
  const list = [
    ...platform.modules.map((m) => ({
      key: m.name,
      title: m.title,
      desc: `${m.title} 专属业务工作台`,
      route: m.menus[0]?.path || `/${m.name}`,
      tag: `v${m.version}`,
    })),
  ]

  if (platform.platformMenus.length > 0) {
    list.push({
      key: 'platform',
      title: '系统管理',
      desc: '用户身份与角色权限配置',
      route: platform.platformMenus[0]?.path || '/platform/users',
      tag: '管控',
    })
  }

  if (!kw) return list
  return list.filter((item) => item.title.toLowerCase().includes(kw) || item.key.toLowerCase().includes(kw))
})

function switchModule(routePath: string): void {
  closeSwitcher()
  router.push(routePath)
}
</script>

<template>
  <div class="layout">
    <!-- 全局精简顶部栏 -->
    <header class="global-header">
      <div class="header-left">
        <!-- 品牌标识：点击返回应用广场首页 -->
        <RouterLink to="/" class="brand" title="返回应用与能力广场">
          <span class="brand-logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" class="brand-icon">
              <path
                d="M12 2L2 7L12 12L22 7L12 2Z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M2 17L12 22L22 17"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M2 12L12 17L22 12"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </span>
          <div class="brand-info">
            <span class="brand-title">AI 内容生产与运营平台</span>
            <span class="brand-badge">STUDIO</span>
          </div>
        </RouterLink>

        <span class="header-divider"></span>

        <!-- 应用广场主入口 -->
        <RouterLink
          to="/"
          class="header-link-btn"
          :class="{ active: isHome }"
        >
          <svg viewBox="0 0 24 24" fill="none" class="header-icon" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" rx="1.5" />
            <rect x="14" y="3" width="7" height="7" rx="1.5" />
            <rect x="14" y="14" width="7" height="7" rx="1.5" />
            <rect x="3" y="14" width="7" height="7" rx="1.5" />
          </svg>
          <span>应用广场</span>
        </RouterLink>

        <!-- 当前模块上下文切换器 (App Switcher) -->
        <div ref="switcherRef" class="app-switcher-wrapper">
          <button
            type="button"
            class="current-app-pill"
            :class="{ 'in-module': !isHome }"
            @click="toggleSwitcher"
          >
            <span v-if="activeModule" class="app-avatar-badge" :style="{ background: activeModule.gradient }">
              {{ activeModule.title.charAt(0) }}
            </span>
            <span v-else class="app-avatar-badge empty">
              ⊞
            </span>
            <span class="app-title-text">{{ activeModule ? activeModule.title : '切换业务能力' }}</span>
            <svg viewBox="0 0 20 20" fill="currentColor" class="switcher-arrow">
              <path
                fill-rule="evenodd"
                d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                clip-rule="evenodd"
              />
            </svg>
          </button>

          <!-- 模块切换浮层面板 -->
          <div v-if="switcherOpen" class="switcher-popover" role="dialog">
            <div class="popover-search-wrap">
              <input
                v-model="switcherSearch"
                type="search"
                placeholder="搜索要跳转的应用模块..."
                class="switcher-search-input"
                autofocus
              />
            </div>
            <div class="popover-list">
              <div
                v-for="item in switcherList"
                :key="item.key"
                class="switcher-card"
                :class="{ active: currentModuleKey === item.key }"
                @click="switchModule(item.route)"
              >
                <div class="switcher-card-main">
                  <div class="switcher-card-top">
                    <span class="switcher-item-name">{{ item.title }}</span>
                    <span class="switcher-item-tag">{{ item.tag }}</span>
                  </div>
                  <span class="switcher-item-desc">{{ item.desc }}</span>
                </div>
                <svg viewBox="0 0 20 20" fill="currentColor" class="switcher-enter-icon">
                  <path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd" />
                </svg>
              </div>
            </div>
            <div class="popover-footer">
              <RouterLink to="/" class="popover-home-link" @click="closeSwitcher">
                浏览全部 {{ switcherList.length }} 个应用卡片 →
              </RouterLink>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧用户信息与操作 -->
      <div class="header-right">
        <div v-if="session.user" class="user-profile">
          <div class="user-avatar-wrap">
            <img
              v-if="session.user.avatar_url"
              :src="session.user.avatar_url"
              alt="头像"
              class="user-avatar"
            />
            <span v-else class="user-avatar-fallback">
              {{ (session.user.display_name || session.user.username || 'U').charAt(0).toUpperCase() }}
            </span>
          </div>
          <div class="user-info">
            <span class="user-name">{{ session.user.display_name || session.user.username }}</span>
            <span v-if="session.user.superuser" class="superuser-tag">超管</span>
          </div>
        </div>
        <button
          type="button"
          class="logout-btn"
          title="退出登录"
          @click="session.logout()"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="logout-icon">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          <span>退出</span>
        </button>
      </div>
    </header>

    <!-- 主工作区：根据是否在模块内，智能展示「模块专业侧栏工作台」或「全屏应用广场」 -->
    <div class="workspace-body">
      <!-- 模块专属侧栏（仅当进入具体模块且该模块有多级菜单时显示） -->
      <aside v-if="!isHome && currentModuleMenuTree.length > 0" class="module-sidebar">
        <div class="module-sidebar-header">
          <span class="module-avatar" :style="{ background: activeModule?.gradient }">
            {{ activeModule?.title.charAt(0) }}
          </span>
          <div class="module-title-box">
            <span class="module-name">{{ activeModule?.title }}</span>
            <span class="module-status-text">工作台</span>
          </div>
        </div>

        <nav class="module-nav-list">
          <RouterLink
            v-for="menu in currentModuleMenuTree"
            :key="menu.path"
            :to="menu.path"
            class="module-nav-item"
          >
            <span class="nav-bullet"></span>
            <span class="nav-item-title">{{ menu.title }}</span>
          </RouterLink>
        </nav>
      </aside>

      <!-- 视图页面挂载容器 -->
      <main class="workspace-main" :class="{ 'with-sidebar': !isHome && currentModuleMenuTree.length > 0 }">
        <div class="content-wrapper" :class="{ 'is-portal': isHome }">
          <RouterView />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background-color: var(--color-bg);
}

/* 全局顶部栏 */
.global-header {
  position: sticky;
  top: 0;
  z-index: 100;
  height: 60px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--color-border);
  box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.03);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-xl);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  cursor: pointer;
}

.brand-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: #ffffff;
  border-radius: var(--radius-md);
  box-shadow: 0 3px 8px 0 rgb(37 99 235 / 0.25);
}

.brand-icon {
  width: 18px;
  height: 18px;
}

.brand-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.brand-badge {
  font-size: 10px;
  font-weight: 800;
  padding: 1px 5px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-primary-border);
}

.header-divider {
  width: 1px;
  height: 20px;
  background: var(--color-border);
  margin: 0 4px;
}

.header-link-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-muted);
  text-decoration: none;
  transition: all var(--transition-fast);
}

.header-link-btn:hover {
  background: var(--color-surface-subtle);
  color: var(--color-text);
}

.header-link-btn.active {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
}

.header-icon {
  width: 15px;
  height: 15px;
}

/* 模块切换器控件 */
.app-switcher-wrapper {
  position: relative;
}

.current-app-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 4px 6px;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.current-app-pill:hover {
  border-color: var(--color-border-hover);
  background: #ffffff;
}

.current-app-pill.in-module {
  background: var(--color-surface);
  border-color: var(--color-primary-border);
  box-shadow: 0 1px 3px 0 rgb(37 99 235 / 0.08);
}

.app-avatar-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
}

.app-avatar-badge.empty {
  background: var(--color-border);
  color: var(--color-text-weak);
}

.app-title-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.switcher-arrow {
  width: 14px;
  height: 14px;
  color: var(--color-text-weak);
}

/* 浮层面板 */
.switcher-popover {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  width: 340px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-dropdown);
  z-index: 200;
  animation: popoverIn 150ms ease-out;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

@keyframes popoverIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.popover-search-wrap {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.switcher-search-input {
  width: 100%;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
  font-size: 12px;
  outline: none;
  transition: all var(--transition-fast);
}

.switcher-search-input:focus {
  border-color: var(--color-primary);
  background: #ffffff;
}

.popover-list {
  max-height: 280px;
  overflow-y: auto;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.switcher-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.switcher-card:hover {
  background: var(--color-surface-subtle);
}

.switcher-card.active {
  background: var(--color-primary-light);
}

.switcher-card-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.switcher-card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}

.switcher-item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.switcher-card.active .switcher-item-name {
  color: var(--color-primary);
}

.switcher-item-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
  color: var(--color-text-weak);
  border: 1px solid var(--color-border-subtle);
}

.switcher-item-desc {
  font-size: 11px;
  color: var(--color-text-weak);
}

.switcher-enter-icon {
  width: 16px;
  height: 16px;
  color: var(--color-text-weak);
}

.switcher-card:hover .switcher-enter-icon {
  color: var(--color-primary);
  transform: translateX(2px);
}

.popover-footer {
  padding: 10px 14px;
  border-top: 1px solid var(--color-border-subtle);
  background: var(--color-surface-subtle);
  text-align: center;
}

.popover-home-link {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-primary);
  text-decoration: none;
}

.popover-home-link:hover {
  text-decoration: underline;
}

/* 顶部右侧 */
.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 3px 10px 3px 4px;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-full);
}

.user-avatar-wrap {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  overflow: hidden;
  background: var(--color-primary-light);
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-avatar {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user-avatar-fallback {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-primary);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.superuser-tag {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: var(--radius-sm);
  background: #fef3c7;
  color: #b45309;
  border: 1px solid #fde68a;
}

.logout-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.logout-icon {
  width: 13px;
  height: 13px;
}

.logout-btn:hover {
  background: var(--color-danger-light);
  border-color: #fecaca;
  color: var(--color-danger-text);
}

/* 工作区结构 */
.workspace-body {
  flex: 1;
  display: flex;
  height: calc(100vh - 60px);
  overflow: hidden;
}

/* 模块专属侧边栏 */
.module-sidebar {
  width: 210px;
  flex-shrink: 0;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  padding: var(--space-md);
  overflow-y: auto;
}

.module-sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px 16px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.module-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  color: #ffffff;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.module-title-box {
  display: flex;
  flex-direction: column;
}

.module-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text);
}

.module-status-text {
  font-size: 11px;
  color: var(--color-text-weak);
}

.module-nav-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.module-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-muted);
  text-decoration: none;
  transition: all var(--transition-fast);
}

.nav-bullet {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-text-weak);
  transition: all var(--transition-fast);
}

.module-nav-item:hover {
  background: var(--color-surface-subtle);
  color: var(--color-primary);
}

.module-nav-item:hover .nav-bullet {
  background: var(--color-primary);
  transform: scale(1.3);
}

.module-nav-item.router-link-active {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
}

.module-nav-item.router-link-active .nav-bullet {
  background: var(--color-primary);
}

/* 主内容区 */
.workspace-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.content-wrapper {
  flex: 1;
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: var(--space-lg) var(--space-xl);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-height: 100%;
}

.content-wrapper.is-portal {
  max-width: 1680px;
  display: block;
  height: auto;
}

@media (max-width: 768px) {
  .global-header {
    padding: 0 var(--space-md);
  }
  .brand-title {
    display: none;
  }
  .content-wrapper {
    padding: var(--space-md);
  }
}
</style>
