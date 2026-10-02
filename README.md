# lancha-ai-studio

模块化单体框架骨架：一个后端进程按模块装载，一个前端工程按模块划分，公共能力只做一份。

- 架构约定与开发流程见 [docs/架构规范.md](docs/架构规范.md)
- `modules/example` 是模块样板，新建模块时复制改名即可，不含任何真实业务

## 快速开始

```bash
cd deploy && docker compose -p lancha up -d postgres

cd ../server
pip install -r requirements/dev.txt
cp .env.example .env
alembic -n platform upgrade head && alembic -n example upgrade head
python scripts/sync_permissions.py
python main.py                       # http://127.0.0.1:8000/health

cd ../web
npm install
cp .env.example .env.local
npm run dev                          # http://localhost:5173
```

## 认证

默认 `AUTH_MODE=dev_header`，身份由 `X-User-Id` 请求头模拟（仅限本地开发），需要先在空表里建一个用户：

```sql
INSERT INTO platform.app_user (username, display_name, is_superuser, is_active)
VALUES ('admin', 'admin', true, true);
```

不要显式指定 `id`：显式插入不会推进自增序列，之后飞书登录自动建用户时会撞主键。空表的第一条记录 `id` 就是 1，与 `VITE_DEV_USER_ID=1` 对得上。

切换到飞书登录：在 `server/.env` 里设 `AUTH_MODE=feishu` 并填齐 `FEISHU_APP_ID` /
`FEISHU_APP_SECRET` / `FEISHU_REDIRECT_URI`（缺一项后端启动即报错），同时删掉 `web/.env.local` 的 `VITE_DEV_USER_ID`。
开发期 `FEISHU_REDIRECT_URI` 填 `http://localhost:5173/api/auth/feishu/callback`（前端地址，经 Vite 代理转发），
飞书开放平台的重定向 URL 要与它完全一致。

第一个超级管理员仍然手工指定——先用飞书扫码登录一次，再执行：

```sql
UPDATE platform.app_user SET is_superuser = true WHERE username = '你的企业邮箱（小写）';
```

`username` 取的是飞书返回的**企业邮箱**并统一转小写；该账号没有企业邮箱时，`username` 为 `feishu_<open_id>`。
拿不准就先查一下再改：

```sql
SELECT u.id, u.username, u.display_name, i.email
FROM platform.app_user u JOIN platform.user_identity i ON i.user_id = u.id;
```

之后就能在「角色管理」里建角色，在「用户管理」里把角色分配给其他人（超级管理员跳过权限校验，默认可见这两个菜单）。

## 检查命令

```bash
cd server   && pytest                          # 含架构边界测试
cd server   && alembic -n platform check       # 模型与迁移一致性
cd web      && npm run lint && npm run typecheck
```
