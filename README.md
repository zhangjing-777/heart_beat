# Heart Beat Monitor API

一个基于FastAPI的设备心跳监控系统，用于实时监控设备在线状态并自动更新设备状态。

## 📋 项目简介

Heart Beat Monitor API 是一个高性能的设备心跳监控服务，支持：
- 设备心跳数据的接收和存储
- 自动监控设备在线状态
- 设备状态自动更新（online/offline）
- 完整的RESTful API接口
- Docker容器化部署

## ✨ 主要功能

### 🔄 心跳管理
- **POST** `/heartbeat` - 创建或更新心跳记录
- **GET** `/heartbeat/{mac_address}` - 查询指定设备心跳记录
- **GET** `/heartbeat` - 获取所有心跳记录列表
- **PUT** `/heartbeat/{mac_address}` - 更新心跳记录
- **DELETE** `/heartbeat/{mac_address}` - 删除心跳记录

### 📊 系统监控
- **GET** `/` - 基础健康检查
- **GET** `/health` - 详细健康状态检查
- **POST** `/monitor/enable` - 启用心跳监听功能
- **POST** `/monitor/disable` - 禁用心跳监听功能
- **GET** `/monitor/status` - 获取监听功能状态
- **POST** `/monitor/restart` - 重启心跳监听任务

### 🤖 自动监控特性
- 自动检测心跳超时设备（默认5分钟超时）
- 自动更新设备状态为offline
- 自动恢复在线设备状态为online
- 后台任务每30秒检查一次
- 支持监听功能的动态启用/禁用

## 🏗️ 技术架构

- **后端框架**: FastAPI
- **数据库**: PostgreSQL (asyncpg驱动)
- **容器化**: Docker + Docker Compose
- **Python版本**: 3.8+
- **异步处理**: asyncio

## 📦 项目结构

```
heart-beat/
├── app.py                 # 主应用文件
├── docker-compose.yml     # Docker Compose配置
├── Dockerfile            # Docker镜像构建文件
├── requirements.txt      # Python依赖包
├── table/
│   ├── init_sql.sql     # 数据库初始化SQL
│   └── run.py           # 数据库初始化脚本
└── README.md            # 项目说明文档
```

## 🚀 快速开始

### 环境要求
- Docker & Docker Compose
- PostgreSQL数据库
- Python 3.8+ (本地开发)

### 1. 环境配置

创建 `.env` 文件并配置数据库连接信息：

```bash
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=heartbeat_db
DB_USER=your_username
DB_PASSWORD=your_password

# 或者使用DATABASE_URL
DATABASE_URL=postgresql://username:password@localhost:5432/heartbeat_db
```

### 2. 数据库初始化

```bash
cd table
python run.py
```

### 3. Docker部署

```bash
# 构建并启动服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 4. 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## 📚 API文档

启动服务后，访问以下地址查看API文档：
- **Swagger UI**: http://localhost:8206/docs
- **ReDoc**: http://localhost:8206/redoc

### 核心API示例

#### 发送心跳数据
```bash
curl -X POST "http://localhost:8206/heartbeat" \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "192.168.1.100",
    "mac_address": "00:11:22:33:44:55",
    "sn": "DEVICE001",
    "beat_time": "2024-01-01T12:00:00Z"
  }'
```

#### 查询设备心跳
```bash
curl -X GET "http://localhost:8206/heartbeat/00:11:22:33:44:55"
```

#### 启用监控功能
```bash
curl -X POST "http://localhost:8206/monitor/enable"
```

## 🗄️ 数据库设计

### heart_beat表
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | SERIAL | 主键ID |
| ip_address | VARCHAR(45) | 设备IP地址 |
| mac_address | VARCHAR(17) | 设备MAC地址（唯一） |
| sn | VARCHAR(100) | 设备序列号 |
| beat_time | TIMESTAMP WITH TIME ZONE | 心跳时间 |
| create_time | TIMESTAMP WITH TIME ZONE | 记录创建时间 |
