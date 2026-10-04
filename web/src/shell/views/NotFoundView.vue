<template>
  <div class="exception-page">
    <div class="exception-card">
      <div class="status-code">404</div>
      <h1 class="title">页面未找到</h1>
      <p class="desc">抱歉，您访问的功能页面不存在，或者该业务模块尚未在此环境装配或启用。</p>
      <div class="actions">
        <RouterLink to="/" class="btn-primary">返回应用广场</RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.exception-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}

.exception-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 48px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  max-width: 480px;
}

.status-code {
  font-size: 72px;
  font-weight: 800;
  line-height: 1;
  background: linear-gradient(135deg, #2563eb 0%, #60a5fa 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 16px;
}

.title {
  margin: 0 0 10px;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}

.desc {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--color-text-muted);
  line-height: 1.6;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  padding: 8px 20px;
  background: var(--color-primary);
  color: #ffffff;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
  transition: all var(--transition-fast);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}
</style>
