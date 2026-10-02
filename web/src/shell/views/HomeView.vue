<script setup lang="ts">
import { usePlatformStore } from '@shared/core'

const platform = usePlatformStore()
</script>

<template>
  <section>
    <h1>已启用的模块</h1>
    <p v-if="platform.modules.length === 0" class="weak">
      没有取到模块信息，确认后端已启动且 /api/modules 可访问。
    </p>
    <ul>
      <li v-for="module in platform.modules" :key="module.name">
        {{ module.title }}（{{ module.name }} v{{ module.version }}）
      </li>
    </ul>
  </section>
</template>

<style scoped>
.weak {
  color: var(--color-text-weak);
}
</style>
