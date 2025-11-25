import { useState, useEffect } from 'react'
import './App.css'
import Login from './Login'

// 使用自己的后端API（会代理到外部API）
const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000' : '')

// 固定的仓库列表
const WAREHOUSES = ['JFK', 'EWR', 'PHL', 'DCA', 'BOS', 'RDU', 'CLT', 'BUF', 'RIC', 'PIT', 'MDT', 'ALB', 'SYR', 'PWM']

function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || null)
  const [items, setItems] = useState([])
  const [selectedWarehouse, setSelectedWarehouse] = useState('')
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [pagination, setPagination] = useState({ page: 1, page_size: 10, total: 0, total_pages: 0 })

  // 如果未登录，显示登录页面
  if (!token) {
    return <Login onLogin={setToken} />
  }

  // Fetch items when warehouse or page changes (only if warehouse is selected)
  useEffect(() => {
    if (selectedWarehouse && token) {
      fetchItems()
    } else {
      // Clear items when no warehouse is selected
      setItems([])
      setPagination({ page: 1, page_size: 10, total: 0, total_pages: 0 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWarehouse, pagination.page, token])

  const fetchItems = async () => {
    if (!selectedWarehouse) {
      return
    }
    
    setLoading(true)
    try {
      const params = new URLSearchParams({
        show_cancelled: 'false',
        page: pagination.page.toString(),
        page_size: pagination.page_size.toString(),
        sort: 'nonupdated_start_timestamp',
        order: 'desc',
        warehouse: selectedWarehouse
      })

      const response = await fetch(`${API_BASE_URL}/api/v1/scan-records/weekly?${params}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'accept': 'application/json'
        }
      })
      if (response.status === 401) {
        // Token过期，清除并返回登录页面
        localStorage.removeItem('token')
        setToken(null)
        return
      }
      const data = await response.json()
      
      // 处理API响应，根据实际响应格式调整
      if (data.data || data.items || Array.isArray(data)) {
        const itemsData = data.data || data.items || data
        setItems(Array.isArray(itemsData) ? itemsData : [])
        
        // 处理分页信息
        if (data.pagination) {
          setPagination(data.pagination)
        } else if (data.total !== undefined) {
          setPagination(prev => ({
            ...prev,
            total: data.total,
            total_pages: Math.ceil(data.total / pagination.page_size)
          }))
        }
      }
    } catch (error) {
      console.error('Error fetching items:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleWarehouseChange = (e) => {
    const warehouse = e.target.value
    setSelectedWarehouse(warehouse)
    setPagination(prev => ({ ...prev, page: 1 }))
  }

  const handlePageChange = (newPage) => {
    setPagination(prev => ({ ...prev, page: newPage }))
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    setToken(null)
  }

  // 获取所有页面的数据
  const fetchAllItems = async () => {
    if (!selectedWarehouse || !token) {
      return []
    }

    const allItems = []
    let currentPage = 1
    let totalPages = 1

    try {
      // 先获取第一页以确定总页数
      const firstPageParams = new URLSearchParams({
        show_cancelled: 'false',
        page: '1',
        page_size: pagination.page_size.toString(),
        sort: 'nonupdated_start_timestamp',
        order: 'desc',
        warehouse: selectedWarehouse
      })

      const firstResponse = await fetch(`${API_BASE_URL}/api/v1/scan-records/weekly?${firstPageParams}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'accept': 'application/json'
        }
      })

      if (firstResponse.status === 401) {
        localStorage.removeItem('token')
        setToken(null)
        return []
      }

      const firstData = await firstResponse.json()
      const firstItemsData = firstData.data || firstData.items || firstData
      if (Array.isArray(firstItemsData)) {
        allItems.push(...firstItemsData)
      }

      // 获取总页数
      if (firstData.pagination) {
        totalPages = firstData.pagination.total_pages
      } else if (firstData.total !== undefined) {
        totalPages = Math.ceil(firstData.total / pagination.page_size)
      }

      // 获取剩余页面
      for (let page = 2; page <= totalPages; page++) {
        const params = new URLSearchParams({
          show_cancelled: 'false',
          page: page.toString(),
          page_size: pagination.page_size.toString(),
          sort: 'nonupdated_start_timestamp',
          order: 'desc',
          warehouse: selectedWarehouse
        })

        const response = await fetch(`${API_BASE_URL}/api/v1/scan-records/weekly?${params}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'accept': 'application/json'
          }
        })

        if (response.status === 401) {
          localStorage.removeItem('token')
          setToken(null)
          break
        }

        const data = await response.json()
        const itemsData = data.data || data.items || data
        if (Array.isArray(itemsData)) {
          allItems.push(...itemsData)
        }
      }
    } catch (error) {
      console.error('Error fetching all items:', error)
    }

    return allItems
  }

  const handleDownloadCSV = async () => {
    if (!selectedWarehouse) {
      return
    }

    setDownloading(true)
    try {
      // 获取所有数据
      const allItems = await fetchAllItems()

      if (allItems.length === 0) {
        alert('没有数据可下载')
        setDownloading(false)
        return
      }

      // CSV表头
      const headers = ['Tracking Number', 'Order ID', '仓库', 'Zone', 'Driver ID', '状态', '未更新时间']
      
      // 将数据转换为CSV格式
      const csvRows = [
        headers.join(','),
        ...allItems.map(item => [
          `"${(item.tracking_number || '').replace(/"/g, '""')}"`,
          `"${(item.order_id || '').replace(/"/g, '""')}"`,
          `"${(item.warehouse || '').replace(/"/g, '""')}"`,
          `"${(item.zone || '').replace(/"/g, '""')}"`,
          `"${(item.driver_id || '').replace(/"/g, '""')}"`,
          `"${(item.current_status || '').replace(/"/g, '""')}"`,
          `"${(item.nonupdated_start_timestamp || 'N/A').replace(/"/g, '""')}"`
        ].join(','))
      ]

      const csvContent = csvRows.join('\n')
      
      // 添加BOM以支持中文
      const BOM = '\uFEFF'
      const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `仓库数据_${selectedWarehouse}_全部_${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Error downloading CSV:', error)
      alert('下载失败，请重试')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="App">
      <header className="App-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h1>仓库数据搜索</h1>
          <button onClick={handleLogout} style={{ padding: '0.5em 1em', fontSize: '0.9em' }}>
            登出
          </button>
        </div>
        
        {/* Warehouse Selection Section */}
        <div className="search-section">
          <div className="search-form">
            <div className="form-group">
              <label htmlFor="warehouse">选择仓库:</label>
              <select
                id="warehouse"
                value={selectedWarehouse}
                onChange={handleWarehouseChange}
                disabled={loading}
              >
                <option value="">请选择仓库</option>
                {WAREHOUSES.map(wh => (
                  <option key={wh} value={wh}>
                    {wh}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Results Section */}
        <div className="results-section">
          {loading ? (
            <div className="loading">加载中...</div>
          ) : (
            <>
              <div className="results-header">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <div>
                    <h2>搜索结果</h2>
                    <p>共找到 {pagination.total} 条记录 (第 {pagination.page} / {pagination.total_pages} 页)</p>
                  </div>
                  {selectedWarehouse && (
                    <button 
                      onClick={handleDownloadCSV}
                      disabled={downloading || loading}
                      style={{ 
                        padding: '0.5em 1em', 
                        fontSize: '0.9em',
                        backgroundColor: downloading ? '#ccc' : '#4CAF50',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: downloading ? 'not-allowed' : 'pointer',
                        opacity: downloading ? 0.6 : 1
                      }}
                    >
                      {downloading ? '下载中...' : `下载CSV (全部${pagination.total}条)`}
                    </button>
                  )}
                </div>
              </div>

              {!selectedWarehouse ? (
                <div className="no-results">请先选择一个仓库</div>
              ) : items.length === 0 ? (
                <div className="no-results">没有找到匹配的记录</div>
              ) : (
                <>
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Tracking Number</th>
                          <th>Order ID</th>
                          <th>仓库</th>
                          <th>Zone</th>
                          <th>Driver ID</th>
                          <th>状态</th>
                          <th>未更新时间</th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((item) => (
                          <tr key={item.id}>
                            <td>{item.tracking_number}</td>
                            <td>{item.order_id}</td>
                            <td>{item.warehouse}</td>
                            <td>{item.zone}</td>
                            <td>{item.driver_id}</td>
                            <td>{item.current_status}</td>
                            <td>{item.nonupdated_start_timestamp || 'N/A'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination */}
                  {pagination.total_pages > 1 && (
                    <div className="pagination">
                      <button
                        onClick={() => handlePageChange(pagination.page - 1)}
                        disabled={pagination.page === 1}
                      >
                        上一页
                      </button>
                      <span>
                        第 {pagination.page} / {pagination.total_pages} 页
                      </span>
                      <button
                        onClick={() => handlePageChange(pagination.page + 1)}
                        disabled={pagination.page >= pagination.total_pages}
                      >
                        下一页
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </header>
    </div>
  )
}

export default App

