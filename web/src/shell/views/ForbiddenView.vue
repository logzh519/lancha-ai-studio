<template>
  <div class="exception-page">
    <div class="exception-card">
      <div class="status-code">403</div>
      <h1 class="title">无访问权限</h1>
      <p class="desc">抱歉，您的当前角色未获得该业务模块或操作接口的访问授权，请联系系统管理员分配权限。</p>
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
  background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
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
