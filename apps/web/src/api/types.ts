// Mirrors packages/core/src/soft_floyd_core/profile/service.py,
// bikes/service.py, connections/service.py, and garmin/sync.py's
// LoginStartResult. Keep field names identical to the API response —
// see docs/FRONTEND.md.

export type CapabilityTier = "power" | "hr" | "cadence" | "basic";

export type BikeKind = "road" | "gravel" | "mtb" | "tt" | "indoor";

export type FocusArea =
  | "endurance"
  | "climbing"
  | "flat_speed"
  | "sprint"
  | "technical_skill"
  | "weight"
  | "first_event"
  | "consistency"
  | "enjoy";

export type SelfRatedLevel = "beginner" | "recreational" | "enthusiast" | "competitive";

export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export interface ProfileOut {
  weekly_rides: number;
  weekly_hours: number;
  goal_text: string;
  target_event_name: string | null;
  target_event_date: string | null;
  focus_areas: string[];

  years_riding: number | null;
  longest_recent_ride_km: number | null;
  followed_plan_before: boolean | null;
  self_rated_level: string | null;

  available_days: string[];
  weekday_max_minutes: number | null;
  weekend_max_minutes: number | null;

  birth_year: number | null;
  weight_kg: number | null;
  max_hr: number | null;
  health_notes: string | null;

  has_hr_monitor: boolean;
  ftp_watts: number | null;
  lthr: number | null;

  // Derived from the garage (bikes) — read-only. Update via the bikes
  // endpoints, not PUT /api/profile. See docs/design-docs/sensor-capability-model.md.
  has_power_meter: boolean;
  has_cadence_sensor: boolean;
  has_speed_sensor: boolean;
  primary_discipline: string | null;

  capability_tier: CapabilityTier;
  available_metrics: string[];
}

// Partial update — only send the fields the current step/section owns.
// Mirrors ProfileIn, which rejects has_power_meter/has_cadence_sensor/
// has_speed_sensor/primary_discipline outright (422) — those are derived.
export type ProfileIn = Partial<
  Omit<
    ProfileOut,
    | "has_power_meter"
    | "has_cadence_sensor"
    | "has_speed_sensor"
    | "primary_discipline"
    | "capability_tier"
    | "available_metrics"
  >
>;

export interface BikeOut {
  id: number;
  nickname: string;
  kind: string;
  is_primary: boolean;
  has_power_meter: boolean;
  has_cadence_sensor: boolean;
  has_speed_sensor: boolean;
  capability_tier: CapabilityTier;
}

export type BikeIn = Partial<Omit<BikeOut, "id" | "capability_tier">>;

export type ConnectionStatus =
  | "connected"
  | "disconnected"
  | "reauth_required"
  | "rate_limited"
  | "error";

export interface ConnectionOut {
  provider: string;
  display_name: string;
  status: ConnectionStatus;
  last_sync_at: string | null;
  last_error: string | null;
  supports_login_in_app: boolean;
  detail: string | null;
}

export interface LoginStartResult {
  state: "connected" | "mfa_required";
}

export function hasCompletedOnboarding(profile: ProfileOut): boolean {
  return profile.goal_text.trim().length > 0;
}
