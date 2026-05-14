export interface ActivitySummary {
  id: number;
  date: string;
  start_time: string;
  bike_type: "road" | "mtb" | "indoor" | "other";
  distance_km: number;
  duration_min: number;
  elev_gain_m: number;
  avg_hr: number | null;
  max_hr: number | null;
  tss_proxy: number | null;
  analyzed: boolean;
}

export interface Lap {
  lap_index: number;
  distance_km: number;
  duration_min: number;
  avg_hr: number | null;
  avg_speed_kmh: number | null;
  elev_gain_m: number;
  gap_speed_kmh: number | null;
}

export interface Metrics {
  decoupling_pct: number | null;
  hr_drift_pct: number | null;
  time_in_z1_min: number | null;
  time_in_z2_min: number | null;
  time_in_z3_min: number | null;
  time_in_z4_min: number | null;
  time_in_z5_min: number | null;
  vam_best_20min: number | null;
  gap_normalized_mps: number | null;
}

export interface TimeseriesPoint {
  t: number;
  hr: number | null;
  alt: number | null;
  speed_kmh: number | null;
}

export interface ActivityDetail extends ActivitySummary {
  sport: string;
  sub_sport: string;
  is_indoor: boolean;
  laps: Lap[];
  metrics: Metrics | null;
  timeseries: TimeseriesPoint[];
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  tokens_in: number | null;
  tokens_out: number | null;
  cache_read: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface MessagesResponse {
  activity_id: number;
  conversation_id?: number;
  messages: ChatMessage[];
}

export interface ActivitiesResponse {
  total: number;
  page: number;
  page_size: number;
  activities: ActivitySummary[];
}

export interface MonthlyCost {
  month: string;
  total_cost_usd: number;
  total_api_calls: number;
  projected_monthly_usd: number;
}
