// Mirrors packages/core/src/soft_floyd_core/profile/service.py.
// Keep field names identical to the API response — see docs/FRONTEND.md.

export type Discipline = "road" | "mtb";
export type CapabilityTier = "power" | "hr" | "cadence" | "basic";

export interface ProfileOut {
  weekly_rides: number;
  weekly_hours: number;
  primary_discipline: Discipline;
  goal_text: string;
  target_event_date: string | null;
  has_power_meter: boolean;
  has_hr_monitor: boolean;
  has_cadence_sensor: boolean;
  has_speed_sensor: boolean;
  ftp_watts: number | null;
  lthr: number | null;
  capability_tier: CapabilityTier;
  available_metrics: string[];
}

// Partial update — only send the fields the current onboarding step owns.
export type ProfileIn = Partial<Omit<ProfileOut, "capability_tier" | "available_metrics">>;

export function hasCompletedOnboarding(profile: ProfileOut): boolean {
  return profile.goal_text.trim().length > 0;
}
