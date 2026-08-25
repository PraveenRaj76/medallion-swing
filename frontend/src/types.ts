export interface ChecklistItem {
  name: string
  value: string
  marks: number
  max_marks: number
  passed: boolean
  note: string
}

export interface ChecklistGroup {
  items: ChecklistItem[]
  total_marks: number
  max_marks: number
  cleared: number
  total_filters: number
  pct: number
  data_quality: string
  sector_pack: string
}

export interface QVT {
  quality: number
  value: number
  timing: number
}

export interface Checklist {
  fundamental: ChecklistGroup
  technical: ChecklistGroup
  composite_marks: number
  composite_max: number
  composite_pct: number
  sector_pack: string
  qvt: QVT
}

export interface BuySignalGate {
  gate: string
  passed: boolean
  detail: string
}

export interface BuySignal {
  ticker: string
  signal: string
  gates: BuySignalGate[]
  blocked_by: string[]
}

export interface ProfileResponse {
  ticker: string
  company_name: string | null
  sector: string | null
  industry: string | null
  close_price: number | null
  data_quality: string | null
  fundamentals_verified: number | null
  source: 'live' | 'cached'
  checklist: Checklist
  buy_signal: BuySignal
  raw: Record<string, unknown>
}

export interface ScreenerRow {
  ticker: string
  company_name: string
  description?: string
  sector: string
  industry: string
  composite_score: number | null
  fundamental_score: number | null
  technical_score: number | null
  close_price: number | null
  atr_value: number | null
  is_buyable: number
  last_updated: string | null
  data_quality: string
  fundamentals_verified: number
  sma_50?: number | null
  sma_200?: number | null
  rsi_14?: number | null
  alpha_3m?: number | null
  pe_ratio?: number | null
  pb_ratio?: number | null
  roic?: number | null
  roe?: number | null
  peg_ratio?: number | null
  [key: string]: unknown
}

export interface ScreenerResponse {
  as_of: string | null
  total_stocks: number
  ready_count: number
  returned: number
  data: ScreenerRow[]
}

export interface SectorRow {
  sector: string
  gics_equivalent: string
  constituent_count: number
  buyable_count: number
  buyable_pct: number
  median_composite_score: number | null
  median_fundamental_score: number | null
  median_technical_score: number | null
  median_pe: number | null
  median_peg: number | null
  sector_score: number | null
  confident_sample: boolean
  top_ticker: string | null
  top_ticker_score: number | null
  why: string
  valuation_read: string
}

export interface SectorsResponse {
  market: string
  as_of: string | null
  universe_size: number
  universe_median_pe: number | null
  rankings: SectorRow[]
  note: string | null
}

export interface ForwardTestPosition {
  position_id: number
  ticker: string
  entry_price: number
  stop_loss: number
  target: number
  current_price?: number | null
  unrealized_pnl?: number | null
  [key: string]: unknown
}

export interface ForwardTestTrade {
  ticker: string
  exit_status: string
  absolute_delta: number
  pct_return: number
  days_elapsed: number
  velocity_label: string
  entry_price: number
  exit_price: number
}

export interface ForwardTestResponse {
  user_id: number
  total_signals_tracked: number
  successful_trades: number
  bad_trades: number
  open_signals: number
  win_rate_pct: number
  win_rate_ci_95: { low: number; high: number }
  total_realized_rupee_return: number
  expectancy_rupee: number
  profit_factor: number | null
  max_drawdown_rupee: number | null
  max_drawdown_pct: number | null
  avg_hold_days: number | null
  velocity_buckets: Record<string, number>
  return_buckets: Record<string, number>
  trades: ForwardTestTrade[]
  active_positions: ForwardTestPosition[]
}
