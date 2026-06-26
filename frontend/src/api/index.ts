import type { MorningBrief, TrackerStock, AccuracyStats, WinRateByScore, MonthlyReturn, CumulativeReturn } from '../types'
import axios from 'axios'

// API 配置
const USE_REAL_API = import.meta.env.VITE_USE_REAL_API === 'true'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const STATIC_DATA_URL = '/data'

console.log('[API] 配置:', { USE_REAL_API, API_BASE_URL, STATIC_DATA_URL })

// ===== 指数数据（实时） =====

export interface IndexData {
  code: string
  name: string
  close: number
  pct: number
  change: number
  high: number
  low: number
  open: number
  prev_close: number
  amplitude: number
  source: string
}

export async function fetchIndices(): Promise<IndexData[]> {
  if (!USE_REAL_API) {
    console.log('[API] 使用静态数据模式')
    return []
  }
  
  try {
    const response = await axios.get(`${API_BASE_URL}/api/indices`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch indices:', error)
    return []
  }
}

// ===== 板块热力图数据（实时） =====

export interface HeatmapSector {
  name: string
  value: number      // 市值/成交额（控制面积）
  change: number     // 涨跌幅（控制颜色）
  leader: string     // 领涨股
  netInflow: number  // 资金净流入
}

export async function fetchHeatmapData(): Promise<HeatmapSector[]> {
  if (!USE_REAL_API) {
    console.log('[API] 使用静态数据模式')
    return []
  }
  
  try {
    const response = await axios.get(`${API_BASE_URL}/api/heatmap`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch heatmap:', error)
    return []
  }
}

// ===== 北向资金（实时） =====

export async function fetchNorthBound() {
  if (!USE_REAL_API) return null
  
  try {
    const response = await axios.get(`${API_BASE_URL}/api/north-bound`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch north-bound:', error)
    return null
  }
}

// ===== 早报相关 =====

export async function fetchMorningBrief(date: string): Promise<MorningBrief | null> {
  try {
    // 优先使用实时 API
    if (USE_REAL_API) {
      const response = await axios.get(`${API_BASE_URL}/api/brief/${date}`)
      return response.data
    }
    
    // 降级到静态数据
    const response = await axios.get(`${STATIC_DATA_URL}/brief/${date}.json`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch morning brief:', error)
    return null
  }
}

export async function fetchAvailableDates(): Promise<string[]> {
  try {
    if (USE_REAL_API) {
      const response = await axios.get(`${API_BASE_URL}/api/brief-dates`)
      return response.data.dates
    }
    
    const response = await axios.get(`${STATIC_DATA_URL}/dates.json`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch available dates:', error)
    return []
  }
}

// ===== 跟踪相关 =====

export async function fetchTrackerStocks(): Promise<TrackerStock[]> {
  try {
    if (USE_REAL_API) {
      const response = await axios.get(`${API_BASE_URL}/api/tracker/stocks`)
      return response.data
    }
    
    const response = await axios.get(`${STATIC_DATA_URL}/tracker/stocks.json`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch tracker stocks:', error)
    return []
  }
}

export async function fetchWinRateByScore(): Promise<WinRateByScore | null> {
  try {
    const response = await axios.get(`${STATIC_DATA_URL}/tracker/winrate_by_score.json`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch win rate by score:', error)
    return null
  }
}

export async function fetchMonthlyReturns(): Promise<MonthlyReturn[]> {
  try {
    const response = await axios.get(`${STATIC_DATA_URL}/tracker/monthly_returns.json`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch monthly returns:', error)
    return []
  }
}

export async function fetchCumulativeReturns(): Promise<CumulativeReturn[]> {
  try {
    const response = await axios.get(`${STATIC_DATA_URL}/tracker/cumulative_returns.json`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch cumulative returns:', error)
    return []
  }
}

// ===== 复盘相关 =====

export async function fetchAccuracyStats(): Promise<AccuracyStats | null> {
  try {
    const response = await axios.get(`${STATIC_DATA_URL}/stats/accuracy.json`)
    return response.data
  } catch (error) {
    console.error('Failed to fetch accuracy stats:', error)
    return null
  }
}

// ===== 健康检查 =====

export async function checkAPIHealth(): Promise<boolean> {
  try {
    const response = await axios.get(`${API_BASE_URL}/health`)
    return response.data.status === 'healthy'
  } catch {
    return false
  }
}
