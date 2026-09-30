# lancha-ai-studio

模块化单体框架骨架：一个后端进程按模块装载，一个前端工程按模块划分，公共能力只做一份。

- 架构约定与开发流程见 [docs/架构规范.md](docs/架构规范.md)
- `modules/example` 是模块样板，新建模块时复制改名即可，不含任何真实业务

## 快速开始

```bash
cd deploy && docker compose -p lancha up -d postgres

cd ../backend
pip install -r requirements/dev.txt
cp .env.example .env
alembic -n platform upgrade head && alembic -n example upgrade head
python scripts/sync_permissions.py
python main.py                       # http://127.0.0.1:8000/health

cd ../frontend
npm install
cp .env.example .env.local
npm run dev                          # http://localhost:5173
```

本框架不含认证。开发期身份由 `X-User-Id` 请求头模拟，需要先在 `platform.app_user` 里建一个用户：

```sql
INSERT INTO platform.app_user (id, username, display_name, is_superuser, is_active)
VALUES (1, 'admin', 'admin', true, true);
```

## 检查命令

```bash
cd backend  && pytest                          # 含架构边界测试
cd backend  && alembic -n platform check       # 模型与迁移一致性
cd frontend && npm run lint && npm run typecheck
```
