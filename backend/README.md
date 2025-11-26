# FastAPI Application

这是一个 FastAPI 项目。

## 项目结构

```
backend/
├── __init__.py
├── main.py              # FastAPI 应用入口
├── config.py            # 配置管理
├── database.py          # 数据库连接管理
├── auth.py              # 认证相关功能
├── models.py            # Pydantic 数据模型
├── routers/             # API 路由
│   ├── __init__.py
│   ├── auth.py          # 认证路由
│   ├── proxy.py         # 代理路由
│   └── warehouse.py     # 仓库路由
└── services/            # 业务逻辑服务
    ├── __init__.py
    └── external_api.py  # 外部 API 客户端
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行应用

从 `backend` 目录运行：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

或者使用 Python 直接运行：

```bash
python -m uvicorn main:app --reload
```

## 环境变量

创建 `.env` 文件并配置以下变量：

```env
POSTGRES_URL=postgresql://user:password@localhost/dbname
EXTERNAL_API_BASE=https://noupdate.uniuni.site
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=40
```

## API 文档

启动服务后，访问以下地址查看 API 文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 主要端点

- `GET /health` - 健康检查
- `POST /api/v1/auth/token` - 代理登录（转发到外部API）
- `POST /api/auth/login` - 本地登录
- `GET /api/auth/me` - 获取当前用户信息
- `GET /api/v1/scan-records/weekly` - 代理扫描记录查询
- `GET /api/warehouse/warehouses` - 获取仓库列表
- `GET /api/warehouse/items` - 获取物品列表

