<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

const workshopMenus = [
  { title: '任务建单', path: '/tiktok_studio/video-workshop/task-create' },
]
</script>

<template>
  <div class="workshop-layout">
    <aside class="workshop-sidebar" aria-label="AI视频工坊菜单">
      <nav class="workshop-nav" aria-label="视频工作流">
        <RouterLink
          v-for="menu in workshopMenus"
          :key="menu.path"
          :to="menu.path"
          class="workshop-nav-item"
          active-class="is-active"
        >
          <span class="nav-index">01</span>
          <span>{{ menu.title }}</span>
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path d="M7.25 4.5a.75.75 0 0 1 1.06 0l5 5a.75.75 0 0 1 0 1.06l-5 5a.75.75 0 1 1-1.06-1.06L11.72 10 7.25 5.56a.75.75 0 0 1 0-1.06Z" />
          </svg>
        </RouterLink>
      </nav>
      <div class="workshop-sidebar-foot">
        <span class="status-mark"></span>
        15秒视频管线
      </div>
    </aside>

    <section class="workshop-content" aria-label="工坊内容">
      <RouterView />
    </section>
  </div>
</template>

<style scoped>
.workshop-layout {
  display: grid;
  grid-template-columns: 208px minmax(0, 1fr);
  min-width: 0;
  min-height: 100%;
  background: #fff;
}

.workshop-sidebar {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 24px 14px 16px;
  border-right: 1px solid #dfe7e4;
  background: #f4f8f6;
}

.workshop-sidebar-heading {
  padding: 0 10px 20px;
  border-bottom: 1px solid #dfe7e4;
}

.workshop-kicker {
  color: #0a7c71;
  font-size: 10px;
  font-weight: 800;
}

.workshop-sidebar-heading h1 {
  margin: 7px 0 0;
  color: #19312f;
  font-size: 17px;
  font-weight: 750;
}

.workshop-nav {
  display: grid;
  gap: 5px;
  padding-top: 14px;
}

.workshop-nav-item {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 10px;
  border-left: 3px solid transparent;
  color: #526865;
  font-size: 13px;
  font-weight: 620;
  text-decoration: none;
  transition: color 140ms ease, background-color 140ms ease;
}

.workshop-nav-item:hover {
  background: #eaf2ef;
  color: #19312f;
}

.workshop-nav-item.is-active {
  border-left-color: #087e75;
  background: #e5f1ee;
  color: #075f58;
}

.nav-index {
  color: #839591;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.workshop-nav-item svg {
  width: 15px;
  height: 15px;
  fill: currentColor;
}

.workshop-sidebar-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: auto 10px 0;
  padding-top: 16px;
  border-top: 1px solid #dfe7e4;
  color: #71827e;
  font-size: 11px;
}

.status-mark {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #d3934f;
}

.workshop-content {
  min-width: 0;
  overflow: auto;
}

@media (max-width: 900px) {
  .workshop-layout {
    grid-template-columns: 172px minmax(0, 1fr);
  }
}

@media (max-width: 700px) {
  .workshop-layout {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
  }

  .workshop-sidebar {
    padding: 12px 16px 0;
    border-right: 0;
    border-bottom: 1px solid #dfe7e4;
  }

  .workshop-sidebar-heading,
  .workshop-sidebar-foot {
    display: none;
  }

  .workshop-nav {
    display: flex;
    padding: 0;
  }

  .workshop-nav-item {
    min-height: 42px;
  }

  .workshop-content {
    overflow: visible;
  }
}
</style>
