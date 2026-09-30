FROM node:22-alpine AS build

ARG VITE_ENABLED_MODULES=""
ENV VITE_ENABLED_MODULES=$VITE_ENABLED_MODULES

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
