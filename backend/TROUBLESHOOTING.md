# 故障排查指南

## 502 Bad Gateway 错误

当遇到 502 Bad Gateway 错误时，通常表示 Nginx 无法连接到后端服务。

### 1. 检查后端服务状态

```bash
# 检查服务状态
sudo systemctl status uniuni-backend-main

# 如果服务未运行，启动它
sudo systemctl start uniuni-backend-main

# 如果服务失败，查看日志
sudo journalctl -u uniuni-backend-main -n 50 --no-pager
```

### 2. 检查服务日志

```bash
# 查看最近的日志
sudo journalctl -u uniuni-backend-main -f

# 查看所有日志
sudo journalctl -u uniuni-backend-main --no-pager
```

### 3. 检查端口监听

```bash
# 检查 8000 端口是否在监听
sudo netstat -tlnp | grep 8000
# 或
sudo ss -tlnp | grep 8000

# 测试本地连接
curl http://127.0.0.1:8000/health
```

### 4. 检查环境变量

```bash
# 检查 .env 文件是否存在
ls -la /home/ubuntu/myproject-prod/backend/.env

# 检查 POSTGRES_URL 是否设置
cat /home/ubuntu/myproject-prod/backend/.env
```

### 5. 检查数据库连接

```bash
# 手动测试数据库连接
cd /home/ubuntu/myproject-prod/backend
source venv/bin/activate
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print('POSTGRES_URL:', os.getenv('POSTGRES_URL'))"
```

### 6. 检查 Nginx 配置

```bash
# 检查 Nginx 配置
sudo nginx -t

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log

# 查看 Nginx 配置
cat /etc/nginx/sites-enabled/uniuni-main
```

### 7. 手动启动服务测试

```bash
# 停止 systemd 服务
sudo systemctl stop uniuni-backend-main

# 手动启动服务查看错误
cd /home/ubuntu/myproject-prod/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 8. 常见问题

#### 问题：数据库连接失败
**解决方案：**
- 检查 `POSTGRES_URL` 环境变量是否正确
- 检查数据库服务器是否可访问
- 检查防火墙设置

#### 问题：依赖包缺失
**解决方案：**
```bash
cd /home/ubuntu/myproject-prod/backend
source venv/bin/activate
pip install -r requirements.txt
```

#### 问题：Python 版本不匹配
**解决方案：**
```bash
# 检查 Python 版本
python3 --version

# 重新创建虚拟环境
cd /home/ubuntu/myproject-prod/backend
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 问题：权限问题
**解决方案：**
```bash
# 检查文件权限
ls -la /home/ubuntu/myproject-prod/backend/

# 确保用户有权限
sudo chown -R ubuntu:ubuntu /home/ubuntu/myproject-prod
```

### 9. 重启服务

```bash
# 重启后端服务
sudo systemctl restart uniuni-backend-main

# 重启 Nginx
sudo systemctl restart nginx

# 检查服务状态
sudo systemctl status uniuni-backend-main
sudo systemctl status nginx
```

### 10. 查看实时日志

```bash
# 同时查看后端和 Nginx 日志
sudo journalctl -u uniuni-backend-main -f &
sudo tail -f /var/log/nginx/error.log
```

