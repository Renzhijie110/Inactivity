import { useState } from 'react'
import './Login.css'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://noupdate.uniuni.site'

function Login({ onLogin }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('40')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      // 使用 application/x-www-form-urlencoded 格式
      const formData = new URLSearchParams()
      formData.append('username', username)
      formData.append('password', password)

      const response = await fetch(`${API_BASE_URL}/api/v1/auth/token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'accept': 'application/json',
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `登录失败 (${response.status})`)
      }

      const data = await response.json()
      const token = data.access_token
      
      // 先保存token
      localStorage.setItem('token', token)
      
      // 立即更新状态，触发App组件重新渲染
      onLogin(token)
      
      // 注意：不要在finally中设置loading，因为组件可能已经卸载
    } catch (err) {
      setLoading(false)
      if (err.name === 'TypeError' && err.message.includes('fetch')) {
        setError('无法连接到服务器，请确保后端服务正在运行')
      } else {
        setError(err.message || '登录失败，请检查用户名和密码')
      }
    }
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <h1>仓库数据搜索系统</h1>
        <h2>登录</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">用户名:</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">密码:</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              required
            />
          </div>
          {error && <div className="error-message">{error}</div>}
          <button type="submit" disabled={loading}>
            {loading ? '登录中...' : '登录'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default Login

