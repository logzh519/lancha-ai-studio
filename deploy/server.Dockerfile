FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# 先装平台公共依赖，代码改动不会让这一层失效
COPY server/requirements ./requirements
RUN pip install --no-cache-dir -r requirements/base.txt

COPY server/ ./

# 再装各模块自己的依赖
RUN set -e; for f in modules/*/requirements.txt; do \
      [ -s "$f" ] && pip install --no-cache-dir -r "$f"; \
    done

# 迁移与权限点同步由 docker-compose.yml 中的 migrate 服务（scripts/migrate.py）在 server 启动前执行，
# 不放在容器启动命令里，避免多副本同时迁移
CMD ["python", "main.py"]
