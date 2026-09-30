<script setup lang="ts">
import { usePlatformStore } from '@shared/core'

const platform = usePlatformStore()
</script>

<template>
  <div class="layout">
    <aside class="sider">
      <div class="brand">lancha-ai-studio</div>
      <nav>
        <p v-if="platform.menuTree.length === 0" class="empty">暂无可见菜单</p>
        <section v-for="group in platform.menuTree" :key="group.path" class="group">
          <h3>{{ group.title }}</h3>
          <RouterLink v-for="menu in group.children" :key="menu.path" :to="menu.path" class="item">
            {{ menu.title }}
          </RouterLink>
        </section>
      </nav>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}

.sider {
  width: 220px;
  flex-shrink: 0;
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

.content {
  flex: 1;
  padding: var(--space-lg);
}
</style>
