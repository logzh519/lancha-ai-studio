<script setup lang="ts">
import { usePlatformStore } from '@shared/core'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

const platform = usePlatformStore()
const router = useRouter()

const searchKeyword = ref('')
const activeCategory = ref('all')

interface ModuleMeta {
  description: string
  category: string
  categoryLabel: string
  tags: string[]
  iconType: 'tiktok' | 'zap' | 'inbox' | 'system'
  gradient: string
  defaultRoute: string
}

const MODULE_EXTRAS: Record<string, ModuleMeta> = {
  tiktok: {
    description: '专注于海外短视频爆款内容孵化。支持爆款脚本库结构化拆解、类目与时长推荐及参考视频关联管理。',
    category: 'tiktok',
    categoryLabel: '社媒矩阵',
    tags: ['爆款脚本库', '短视频生产', '类目匹配', '参考视频'],
    iconType: 'tiktok',
    gradient: 'linear-gradient(135deg, #000000 0%, #1e1e2d 50%, #fe2c55 100%)',
    defaultRoute: '/tiktok/script-templates',
  },
  example_a: {
    description: '核心生产流与条目生命周期管理，演示业务模块状态持久化与基于总线的事件广播。',
    category: 'service',
    categoryLabel: '业务示例',
    tags: ['条目生命周期', '数据流转', '事件发布'],
    iconType: 'zap',
    gradient: 'linear-gradient(135deg, #2563eb 0%, #3b82f6 100%)',
    defaultRoute: '/example_a/items',
  },
  example_b: {
    description: '进程内事件订阅与通知收件箱，实时接收并消费跨模块生产业务事件。',
    category: 'service',
    categoryLabel: '业务示例',
    tags: ['事件收件箱', '异步分发', '解耦契约'],
    iconType: 'inbox',
    gradient: 'linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)',
    defaultRoute: '/example_b/events',
  },
}

const SYSTEM_EXTRA: ModuleMeta = {
  description: '统一管理团队组织成员身份标识、飞书授权绑定与细粒度 RBAC 角色权限体系。',
  category: 'system',
  categoryLabel: '平台管控',
  tags: ['成员管理', 'RBAC授权', '角色配置', '操作权限'],
  iconType: 'system',
  gradient: 'linear-gradient(135deg, #475569 0%, #334155 100%)',
  defaultRoute: '/platform/users',
}

interface AppCardItem {
  id: string
  title: string
  name: string
  version?: string
  description: string
  category: string
  categoryLabel: string
  tags: string[]
  iconType: 'tiktok' | 'zap' | 'inbox' | 'system'
  gradient: string
  defaultRoute: string
  subMenus: Array<{ title: string; path: string }>
}

const allCards = computed<AppCardItem[]>(() => {
  const list: AppCardItem[] = []

  // 1. 业务模块
  for (const mod of platform.modules) {
    const extra = MODULE_EXTRAS[mod.name] || {
      description: `${mod.title}业务能力模块，提供一体化生产管理功能。`,
      category: 'other',
      categoryLabel: '业务模块',
      tags: ['生产能力', '业务模块'],
      iconType: 'zap',
      gradient: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
      defaultRoute: mod.menus[0]?.path || '/',
    }

    const subMenus = mod.menus.map((m) => ({ title: m.title, path: m.path }))

    list.push({
      id: mod.name,
      title: mod.title,
      name: mod.name,
      version: `v${mod.version}`,
      description: extra.description,
      category: extra.category,
      categoryLabel: extra.categoryLabel,
      tags: extra.tags,
      iconType: extra.iconType,
      gradient: extra.gradient,
      defaultRoute: mod.menus[0]?.path || extra.defaultRoute,
      subMenus,
    })
  }

  // 2. 系统管理（如果有系统菜单权限）
  if (platform.platformMenus.length > 0) {
    list.push({
      id: 'platform',
      title: '系统管理与管控',
      name: 'platform',
      version: 'Core',
      description: SYSTEM_EXTRA.description,
      category: SYSTEM_EXTRA.category,
      categoryLabel: SYSTEM_EXTRA.categoryLabel,
      tags: SYSTEM_EXTRA.tags,
      iconType: SYSTEM_EXTRA.iconType,
      gradient: SYSTEM_EXTRA.gradient,
      defaultRoute: platform.platformMenus[0]?.path || '/platform/users',
      subMenus: platform.platformMenus.map((m) => ({ title: m.title, path: m.path })),
    })
  }

  return list
})

// 分类列表
const categories = computed(() => {
  const catSet = new Set<string>()
  allCards.value.forEach((card) => catSet.add(card.category))

  const options = [{ key: 'all', label: '全部能力' }]
  if (catSet.has('tiktok')) options.push({ key: 'tiktok', label: '社媒矩阵' })
  if (catSet.has('service')) options.push({ key: 'service', label: '业务模块' })
  if (catSet.has('system')) options.push({ key: 'system', label: '平台管控' })
  if (catSet.has('other')) options.push({ key: 'other', label: '其它扩展' })
  return options
})

// 过滤后的卡片
const filteredCards = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  return allCards.value.filter((card) => {
    const matchCategory = activeCategory.value === 'all' || card.category === activeCategory.value
    if (!matchCategory) return false

    if (!kw) return true
    const inTitle = card.title.toLowerCase().includes(kw)
    const inName = card.name.toLowerCase().includes(kw)
    const inDesc = card.description.toLowerCase().includes(kw)
    const inTags = card.tags.some((t) => t.toLowerCase().includes(kw))
    return inTitle || inName || inDesc || inTags
  })
})

function navigateTo(route: string): void {
  router.push(route)
}
</script>

<template>
  <div class="plaza-wrapper">
    <!-- 顶部检索与分类筛选控制栏 -->
    <header class="plaza-toolbar">
      <div class="search-box">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="search-icon">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          v-model="searchKeyword"
          type="search"
          placeholder="搜索能力、模块名称或业务标签..."
          class="search-input"
        />
        <button v-if="searchKeyword" type="button" class="clear-btn" @click="searchKeyword = ''">
          ✕
        </button>
      </div>

      <div class="category-pills">
        <button
          v-for="cat in categories"
          :key="cat.key"
          type="button"
          class="pill-btn"
          :class="{ active: activeCategory === cat.key }"
          @click="activeCategory = cat.key"
        >
          {{ cat.label }}
        </button>
      </div>
    </header>

    <!-- 卡片网格区 -->
    <section class="cards-section">
      <div v-if="filteredCards.length > 0" class="cards-grid">
        <div
          v-for="card in filteredCards"
          :key="card.id"
          class="app-card"
          @click="navigateTo(card.defaultRoute)"
        >
          <!-- 卡片上部：图标与基本标识 -->
          <div class="card-header">
            <div class="icon-wrap" :style="{ background: card.gradient }">
              <!-- TikTok 图标 -->
              <svg v-if="card.iconType === 'tiktok'" viewBox="0 0 24 24" fill="currentColor" class="card-svg">
                <path
                  d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.89 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.31 0 .61.05.89.14v-3.52a6.34 6.34 0 0 0-.89-.06 6.34 6.34 0 0 0-6.34 6.32 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V8.75a8.28 8.28 0 0 0 4.76 1.48V6.78c-.3 0-.6-.03-.9-.09z"
                />
              </svg>
              <!-- 业务示例 A: Zap -->
              <svg
                v-else-if="card.iconType === 'zap'"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                class="card-svg"
              >
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              <!-- 业务示例 B: Inbox -->
              <svg
                v-else-if="card.iconType === 'inbox'"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                class="card-svg"
              >
                <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
                <path
                  d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"
                />
              </svg>
              <!-- 系统管理: Shield/Settings -->
              <svg
                v-else
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                class="card-svg"
              >
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </div>

            <div class="card-titles">
              <div class="title-row">
                <h3 class="card-title">{{ card.title }}</h3>
                <span v-if="card.version" class="card-version">{{ card.version }}</span>
              </div>
              <span class="card-category-tag">{{ card.categoryLabel }}</span>
            </div>
          </div>

          <!-- 卡片说明 -->
          <p class="card-description">{{ card.description }}</p>

          <!-- 标签 Tags -->
          <div class="card-tags">
            <span v-for="tag in card.tags" :key="tag" class="tag-item">{{ tag }}</span>
          </div>

          <!-- 子菜单快捷导航 -->
          <div v-if="card.subMenus.length > 0" class="card-sublinks">
            <span class="sublinks-label">常用入口：</span>
            <div class="sublinks-list">
              <RouterLink
                v-for="sub in card.subMenus"
                :key="sub.path"
                :to="sub.path"
                class="sublink-btn"
                @click.stop
              >
                {{ sub.title }}
              </RouterLink>
            </div>
          </div>

          <!-- 卡片底部操作栏 -->
          <div class="card-footer">
            <div class="status-indicator">
              <span class="status-dot"></span>
              <span class="status-text">正常运行</span>
            </div>
            <button type="button" class="action-btn">
              <span>立即进入</span>
              <svg viewBox="0 0 20 20" fill="currentColor" class="action-arrow">
                <path
                  fill-rule="evenodd"
                  d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z"
                  clip-rule="evenodd"
                />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="empty-state">
        <div class="empty-icon-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="empty-icon">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
            <line x1="8" y1="11" x2="14" y2="11" />
          </svg>
        </div>
        <h3>未找到匹配的能力或应用</h3>
        <p>尝试切换筛选分类，或清除搜索关键词后重新查找。</p>
        <button type="button" class="reset-filter-btn" @click="searchKeyword = ''; activeCategory = 'all'">
          重置筛选条件
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.plaza-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
}

/* 工具栏 */
.plaza-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-md);
  padding: 18px 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  width: 320px;
  max-width: 100%;
}

.search-icon {
  position: absolute;
  left: 12px;
  width: 16px;
  height: 16px;
  color: var(--color-text-weak);
  pointer-events: none;
}

.search-input {
  width: 100%;
  height: 38px;
  padding: 0 32px 0 36px;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: 13px;
  color: var(--color-text);
  outline: none;
  transition: all var(--transition-fast);
}

.search-input:focus {
  background: var(--color-surface);
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.clear-btn {
  position: absolute;
  right: 10px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: var(--color-border);
  color: var(--color-text-muted);
  font-size: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.category-pills {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pill-btn {
  padding: 6px 14px;
  border-radius: var(--radius-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-muted);
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.pill-btn:hover {
  color: var(--color-text);
  border-color: var(--color-border-hover);
}

.pill-btn.active {
  color: #ffffff;
  background: var(--color-primary);
  border-color: var(--color-primary);
  box-shadow: 0 2px 6px 0 rgba(37, 99, 235, 0.25);
}

/* 卡片网格：桌面端单行4张 */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

@media (max-width: 1400px) {
  .cards-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 1080px) {
  .cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .cards-grid {
    grid-template-columns: 1fr;
  }
}

.app-card {
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-card);
  transition: all var(--transition-normal);
  cursor: pointer;
  position: relative;
}

.app-card:hover {
  transform: translateY(-3px);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-hover);
}

/* 卡片顶部 */
.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.icon-wrap {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.card-svg {
  width: 20px;
  height: 20px;
}

.card-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-version {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  background: var(--color-surface-subtle);
  color: var(--color-text-weak);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
}

.card-category-tag {
  font-size: 12px;
  color: var(--color-text-weak);
}

/* 卡片内容 */
.card-description {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--color-text-muted);
  line-height: 1.6;
  min-height: 42px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 标签 */
.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 16px;
}

.tag-item {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-muted);
  background: var(--color-surface-subtle);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-subtle);
}

/* 常用入口 */
.card-sublinks {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 12px;
  background: var(--color-surface-subtle);
  border-radius: var(--radius);
  margin-bottom: 18px;
  font-size: 12px;
}

.sublinks-label {
  color: var(--color-text-weak);
  flex-shrink: 0;
}

.sublinks-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.sublink-btn {
  color: var(--color-primary);
  font-weight: 500;
  text-decoration: none;
  transition: color var(--transition-fast);
}

.sublink-btn:hover {
  text-decoration: underline;
  color: var(--color-primary-hover);
}

/* 卡片底栏 */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px solid var(--color-border-subtle);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 0 2px var(--color-success-light);
}

.status-text {
  font-size: 12px;
  color: var(--color-text-weak);
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.app-card:hover .action-btn {
  background: var(--color-primary-light);
  color: var(--color-primary-hover);
}

.action-arrow {
  width: 14px;
  height: 14px;
  transition: transform var(--transition-fast);
}

.app-card:hover .action-arrow {
  transform: translateX(3px);
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 24px;
  background: var(--color-surface);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
  text-align: center;
}

.empty-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--color-surface-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-weak);
  margin-bottom: var(--space-md);
}

.empty-icon {
  width: 28px;
  height: 28px;
}

.empty-state h3 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--color-text);
}

.empty-state p {
  margin: 0 0 var(--space-lg);
  font-size: 13px;
  color: var(--color-text-weak);
}

.reset-filter-btn {
  padding: 8px 16px;
  background: var(--color-primary);
  color: #ffffff;
  border: none;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.reset-filter-btn:hover {
  background: var(--color-primary-hover);
}
</style>
