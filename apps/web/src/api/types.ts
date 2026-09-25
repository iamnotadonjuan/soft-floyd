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
  // Derived from the selected usual riding days after habits are saved.
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

  // Devices the Training flow (exec-plan 0010) offers to export/push a
  // planned session to. Asked once, editable in Settings.
  workout_devices: string[];

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

export interface ActivitySummaryOut {
  id: number;
  start_time: string;
  sport: string;
  sub_sport: string;
  bike_type: string;
  is_indoor: boolean;
  distance_m: number;
  duration_s: number;
  elev_gain_m: number;
  avg_hr: number | null;
  max_hr: number | null;
  avg_power_w: number | null;
  avg_cadence: number | null;
  sensors_present: string[];
  fit_status: string;
}

export interface LapOut {
  lap_index: number;
  distance_m: number;
  duration_s: number;
  avg_hr: number | null;
  avg_speed_mps: number | null;
  avg_power_w: number | null;
  avg_cadence: number | null;
  elev_gain_m: number;
}

export interface ActivityDetailOut extends ActivitySummaryOut {
  laps: LapOut[];
  record_count: number;
  records_stored: boolean;
  available_metrics: string[];
}

// Coach agent (exec-plan 0007) — mirrors soft_floyd_core.coach.*.
export interface CoachSourceOut {
  book_id: number;
  title: string;
  author: string | null;
  page_start: number;
  page_end: number;
}

export interface CoachConversationOut {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface CoachMessageOut {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: CoachSourceOut[];
  created_at: string;
}

export interface CoachConversationDetailOut extends CoachConversationOut {
  messages: CoachMessageOut[];
}

// One Server-Sent Event from POST /api/coach/conversations/{id}/messages.
// Fields left unset by the server (exclude_none) are simply absent.
export interface CoachEvent {
  type: "delta" | "tool_status" | "sources" | "done" | "error";
  text?: string;
  sources?: CoachSourceOut[];
  message?: CoachMessageOut;
}

export interface CoachMemoryNoteOut {
  id: number;
  text: string;
  created_at: string;
}

export function hasCompletedOnboarding(profile: ProfileOut): boolean {
  return profile.goal_text.trim().length > 0;
}
export interface AccountOut {
  id: number;
  email: string;
  name: string;
  picture_url: string | null;
}

// Training sessions (exec-plan 0010) — mirrors
// packages/core/src/soft_floyd_core/training/schemas.py and service.py.
export type Discipline = "road" | "mtb" | "gravel";
export type WorkoutDevice = "garmin" | "wahoo" | "zwift" | "other";
export type SessionSetting = "indoor" | "outdoor";
export type Feel = "fresh" | "normal" | "tired";
export type SessionStatus = "planned" | "done" | "skipped";
export type Emphasis = "recovery" | "endurance" | "tempo" | "threshold" | "vo2" | "climbing";
export type WorkoutStepKind = "warmup" | "interval" | "recovery" | "cooldown";
export type ExportFormat = "fit" | "zwo" | "erg";

export interface SessionRequest {
  planned_date: string;
  available_minutes: number;
  setting: SessionSetting;
  discipline: Discipline;
  bike_id: number | null;
  route_idea: string;
  feel: Feel;
}

// The POST body — bike_id/route_idea/feel may be omitted, matching the
// server's own defaults (ProfileIn-style partial-input convention).
export type SessionRequestIn = Pick<
  SessionRequest,
  "planned_date" | "available_minutes" | "setting" | "discipline"
> &
  Partial<Pick<SessionRequest, "bike_id" | "route_idea" | "feel">>;

export interface SessionIntent {
  emphasis: Emphasis;
  reasons: string[];
  off_schedule: boolean;
}

export interface StepEnd {
  kind: "time" | "distance" | "lap_button";
  seconds: number | null;
  meters: number | null;
}

export interface StepTarget {
  kind: "power" | "hr" | "cadence";
  low: number;
  high: number;
}

export interface WorkoutStep {
  kind: WorkoutStepKind;
  name: string;
  cue: string;
  end: StepEnd;
  target: StepTarget | null;
}

export interface RepeatBlock {
  kind: "repeat";
  count: number;
  steps: WorkoutStep[];
}

export type WorkoutItem = WorkoutStep | RepeatBlock;

export interface Workout {
  name: string;
  est_minutes: number;
  steps: WorkoutItem[];
}

export interface TrainingSessionOut {
  id: number;
  planned_date: string;
  bike_id: number | null;
  setting: SessionSetting;
  discipline: Discipline;
  request: SessionRequest;
  intent: SessionIntent;
  workout: Workout;
  rationale: string;
  adjustments: string | null;
  sources: CoachSourceOut[];
  status: SessionStatus;
  garmin_workout_id: string | null;
  sent_to_garmin_at: string | null;
  available_export_formats: ExportFormat[];
  created_at: string;
  updated_at: string;
}
