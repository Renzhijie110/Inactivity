# FastAPI Application

这是一个 FastAPI 项目。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行应用

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

或者使用 Python 直接运行：

```bash
python -m uvicorn main:app --reload
```

## API 文档

启动服务后，访问以下地址查看 API 文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 端点

- `GET /` - 根路径
- `GET /health` - 健康检查
- `GET /api/hello` - 示例 API 端点

