# 502 Bad Gateway 诊断指南

当遇到 502 Bad Gateway 错误时，说明 Nginx 无法连接到后端 FastAPI 服务。

## 常见错误：ImportError - attempted relative import

如果日志中出现以下错误：
```
ImportError: attempted relative import with no known parent package
```

**原因：** `main.py` 使用了相对导入（`from .config import settings`），但 uvicorn 直接运行 `main:app` 时无法解析相对导入。

**解决方案：** `main.py` 应该使用绝对导入（`from config import settings`），因为工作目录是 `backend`。

## 快速诊断步骤

### 1. 检查后端服务是否运行

```bash
# 检查服务状态（根据你的服务名称调整）
sudo systemctl status uniuni-backend-main
# 或者
sudo systemctl status <your-service-name>
```

如果服务未运行：
```bash
sudo systemctl start <your-service-name>
```

### 2. 检查服务日志

```bash
# 查看最近的错误日志
sudo journalctl -u <your-service-name> -n 100 --no-pager

# 实时查看日志
sudo journalctl -u <your-service-name> -f
```

### 3. 检查端口是否在监听

```bash
# 检查端口（默认是 8000，根据你的配置调整）
sudo netstat -tlnp | grep 8000
# 或
sudo ss -tlnp | grep 8000

# 测试本地连接
curl http://127.0.0.1:8000/health
```

如果 `curl` 失败，说明后端服务没有正常运行。

### 4. 检查 Nginx 错误日志

```bash
# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log
```

### 5. 检查 Nginx 配置

```bash
# 测试 Nginx 配置
sudo nginx -t

# 查看 Nginx 配置中的代理设置
cat /etc/nginx/sites-enabled/uniuni-*
```

确保 `proxy_pass` 指向正确的端口（例如 `http://127.0.0.1:8000`）。

### 6. 手动启动服务测试

```bash
# 停止 systemd 服务
sudo systemctl stop <your-service-name>

# 进入后端目录
cd /path/to/your/backend

# 激活虚拟环境
source venv/bin/activate

# 手动启动服务（查看详细错误信息）
uvicorn main:app --host 0.0.0.0 --port 8000
```

如果手动启动失败，查看错误信息：
- 数据库连接失败？
- 依赖包缺失？
- Python 版本问题？
- 环境变量未设置？

### 7. 检查环境变量

```bash
# 检查 .env 文件
cat /path/to/your/backend/.env

# 检查环境变量是否正确加载
cd /path/to/your/backend
source venv/bin/activate
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('POSTGRES_URL:', os.getenv('POSTGRES_URL'))"
```

### 8. 常见问题及解决方案

#### 问题 1: 服务启动失败 - 数据库连接错误
**症状：** 日志显示数据库连接失败

**解决方案：**
```bash
# 检查数据库是否可访问
# 检查 POSTGRES_URL 环境变量
# 检查防火墙设置
```

#### 问题 2: 服务启动失败 - 模块导入错误
**症状：** 日志显示 `ModuleNotFoundError` 或 `ImportError`

**解决方案：**
```bash
cd /path/to/your/backend
source venv/bin/activate
pip install -r requirements.txt
```

#### 问题 3: 端口被占用
**症状：** 日志显示端口已被使用

**解决方案：**
```bash
# 查找占用端口的进程
sudo lsof -i :8000
# 或
sudo netstat -tlnp | grep 8000

# 停止占用端口的进程，或修改配置使用其他端口
```

#### 问题 4: 权限问题
**症状：** 服务无法读取文件或写入日志

**解决方案：**
```bash
# 检查文件权限
ls -la /path/to/your/backend/

# 确保用户有权限
sudo chown -R <your-user>:<your-group> /path/to/your/backend
```

### 9. 重启服务

```bash
# 重启后端服务
sudo systemctl restart <your-service-name>

# 重启 Nginx
sudo systemctl restart nginx

# 检查服务状态
sudo systemctl status <your-service-name>
sudo systemctl status nginx
```

### 10. 验证修复

```bash
# 测试健康检查端点
curl http://127.0.0.1:8000/health

# 应该返回：
# {"status":"ok","service":"FastAPI Backend","database":"connected"}

# 测试通过 Nginx
curl http://your-domain/api/health
```

## 如果问题仍然存在

1. 收集以下信息：
   - 服务日志：`sudo journalctl -u <your-service-name> -n 200 --no-pager`
   - Nginx 错误日志：`sudo tail -n 100 /var/log/nginx/error.log`
   - 手动启动的输出
   - 环境变量配置（隐藏敏感信息）

2. 检查系统资源：
   ```bash
   # 检查内存使用
   free -h
   
   # 检查磁盘空间
   df -h
   
   # 检查系统负载
   uptime
   ```

3. 检查防火墙：
   ```bash
   # 检查防火墙规则
   sudo ufw status
   # 或
   sudo iptables -L
   ```

