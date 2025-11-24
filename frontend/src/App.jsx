import { useState, useEffect } from 'react'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [items, setItems] = useState([])
  const [warehouses, setWarehouses] = useState([])
  const [selectedWarehouse, setSelectedWarehouse] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ page: 1, page_size: 50, total: 0, total_pages: 0 })
  const [warehouseStats, setWarehouseStats] = useState({})

  // Fetch warehouses on mount
  useEffect(() => {
    fetchWarehouses()
  }, [])

  // Fetch items when filters change
  useEffect(() => {
    fetchItems()
  }, [selectedWarehouse, searchTerm, pagination.page])

  const fetchWarehouses = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/warehouse/warehouses`)
      const data = await response.json()
      if (data.success) {
        setWarehouses(data.warehouses)
      }
    } catch (error) {
      console.error('Error fetching warehouses:', error)
    }
  }

  const fetchItems = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: pagination.page.toString(),
        page_size: pagination.page_size.toString(),
      })
      
      if (selectedWarehouse) {
        params.append('warehouse', selectedWarehouse)
      }
      
      if (searchTerm) {
        params.append('search', searchTerm)
      }

      const response = await fetch(`${API_BASE_URL}/api/warehouse/items?${params}`)
      const data = await response.json()
      
      if (data.success) {
        setItems(data.data)
        setPagination(data.pagination)
        setWarehouseStats(data.warehouse_stats || {})
      }
    } catch (error) {
      console.error('Error fetching items:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = (e) => {
    e.preventDefault()
    setPagination(prev => ({ ...prev, page: 1 }))
    fetchItems()
  }

  const handlePageChange = (newPage) => {
    setPagination(prev => ({ ...prev, page: newPage }))
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>仓库数据搜索</h1>
        
        {/* Search and Filter Section */}
        <div className="search-section">
          <form onSubmit={handleSearch} className="search-form">
            <div className="form-group">
              <label htmlFor="warehouse">仓库:</label>
              <select
                id="warehouse"
                value={selectedWarehouse}
                onChange={(e) => {
                  setSelectedWarehouse(e.target.value)
                  setPagination(prev => ({ ...prev, page: 1 }))
                }}
              >
                <option value="">全部仓库</option>
                {warehouses.map(wh => (
                  <option key={wh.code} value={wh.code}>
                    {wh.code} ({wh.count})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="search">搜索 (Tracking Number, Order ID, Driver ID):</label>
              <input
                id="search"
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="输入搜索关键词..."
              />
            </div>

            <button type="submit" disabled={loading}>
              {loading ? '搜索中...' : '搜索'}
            </button>
          </form>
        </div>

        {/* Warehouse Stats */}
        {Object.keys(warehouseStats).length > 0 && (
          <div className="warehouse-stats">
            <h3>仓库统计:</h3>
            <div className="stats-grid">
              {Object.entries(warehouseStats).map(([warehouse, count]) => (
                <div key={warehouse} className="stat-item">
                  <strong>{warehouse}:</strong> {count} 条记录
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Results Section */}
        <div className="results-section">
          {loading ? (
            <div className="loading">加载中...</div>
          ) : (
            <>
              <div className="results-header">
                <h2>搜索结果</h2>
                <p>共找到 {pagination.total} 条记录 (第 {pagination.page} / {pagination.total_pages} 页)</p>
              </div>

              {items.length === 0 ? (
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

