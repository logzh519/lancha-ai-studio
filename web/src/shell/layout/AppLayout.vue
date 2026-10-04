<script setup lang="ts">
import { usePlatformStore, useSessionStore } from '@shared/core'

const platform = usePlatformStore()
const session = useSessionStore()
</script>

<template>
  <div class="layout">
    <aside class="sider">
      <div class="brand">lancha-ai-studio</div>
      <nav>
        <p v-if="platform.menuTree.length === 0 && platform.platformMenus.length === 0" class="empty">
          暂无可见菜单
        </p>
        <section v-for="group in platform.menuTree" :key="group.path" class="group">
          <h3>{{ group.title }}</h3>
          <RouterLink v-for="menu in group.children" :key="menu.path" :to="menu.path" class="item">
            {{ menu.title }}
          </RouterLink>
        </section>
        <section v-if="platform.platformMenus.length > 0" class="group">
          <h3>系统管理</h3>
          <RouterLink v-for="menu in platform.platformMenus" :key="menu.path" :to="menu.path" class="item">
            {{ menu.title }}
          </RouterLink>
        </section>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <span v-if="session.user" class="who">
          <img v-if="session.user.avatar_url" :src="session.user.avatar_url" alt="" />
          {{ session.user.display_name || session.user.username }}
        </span>
        <button type="button" @click="session.logout()">退出登录</button>
      </header>
      <main class="content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.sider {
  width: 220px;
  flex-shrink: 0;
  overflow-y: auto;
  padding: var(--space-md);
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
}

.brand {
  font-weight: 600;
  margin-bottom: var(--space-lg);
}

.group h3 {
  margin: 0 0 var(--space-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-weak);
}

.item {
  display: block;
  padding: 6px var(--space-sm);
  border-radius: var(--radius);
  font-size: 14px;
}

.item:hover,
.item.router-link-active {
  background: var(--color-bg);
  color: var(--color-primary);
}

.empty {
  font-size: 13px;
  color: var(--color-text-weak);
}

/* 框架本身不滚动；内容超出时在内容区内滚动，模块页面可用 height: 100% 撑满后自行做局部滚动 */
.content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--space-lg);
}

.main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
  gap: var(--space-md);
  height: 52px;
  padding: 0 var(--space-lg);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}

.who {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: 14px;
}

.who img {
  width: 26px;
  height: 26px;
  border-radius: 50%;
}

.topbar button {
  padding: 5px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  cursor: pointer;
}
</style>
