export interface MarketIndex {
  name: string;
  value: number;
  pct: number;
  volume?: number;
}

export interface StockScore {
  symbol: string;
  name: string;
  score: number;
  stars: number;
  tags: string[];
  logic: string;
  risks?: string[];
  scoreDetail?: StockScoreDetail;
}

export interface SectorData {
  name: string;
  pct: number;
  funds?: number;
  leading?: string[];
  logic?: string;
}

export interface MorningBrief {
  date: string;
  marketTone: string;
  usImpact: string;
  emotionFeature: string;
  sentimentClass: string;
  todayPrediction: {
    direction: string;
    range: [number, number];
    position: string;
    rhythm: string;
  };
  indices: MarketIndex[];
  topGainers: SectorData[];
  topLosers: SectorData[];
  stocks: StockScore[];
  northBound?: {
    netInflow: number;
    history?: NorthBoundFlow[];
  };
  marketBreadth?: MarketSentiment;
  riskAlerts?: RiskAlert[];
  sectorFundFlow?: SectorFundFlow[];
}

export interface TrackerStock {
  symbol: string;
  name: string;
  score: number;
  stars: number;
  date: string;
  returns: {
    nextDay?: number;
    day3?: number;
    day5?: number;
    day7?: number;
  };
  entryPrice?: number;
  currentPrice?: number;
  tags?: string[];
  logic?: string;
}

export interface AccuracyStats {
  directionAccuracy: number;
  rangeAccuracy: number;
  stockWinRate: number;
  totalPredictions: number;
  correctPredictions: number;
}

// ===== 新增类型定义 =====

export interface NorthBoundFlow {
  date: string;
  netInflow: number;
  cumulative: number;
}

export interface MarketSentiment {
  upCount: number;
  downCount: number;
  flatCount: number;
  limitUp: number;
  limitDown: number;
  upRatio: number;
  limitRatio: number;
}

export interface StockScoreDetail {
  businessPurity: number;
  industryPosition: number;
  priceBenefit: number;
  earningsVerify: number;
  catalystProximity: number;
  valuationPosition: number;
  specialTag: number;
  macd: number;
  kdj: number;
  volume: number;
  ma: number;
  support: number;
}

export interface RiskAlert {
  level: 'high' | 'medium' | 'low';
  title: string;
  content: string;
}

export interface SectorFundFlow {
  name: string;
  pct: number;
  fundInflow: number;
  leadingStocks: string[];
  logic: string;
}

export interface WinRateByScore {
  score5: { win: number; total: number; winRate: number; avgReturn: number };
  score4: { win: number; total: number; winRate: number; avgReturn: number };
  score3: { win: number; total: number; winRate: number; avgReturn: number };
  score2: { win: number; total: number; winRate: number; avgReturn: number };
}

export interface MonthlyReturn {
  month: string;
  returnPct: number;
  winCount: number;
  loseCount: number;
}

export interface CumulativeReturn {
  date: string;
  strategy: number;
  benchmark: number;
}
