import type { ActivitySummaryOut } from "../api/types";
import type { Messages } from "../i18n/en";

// Callers pass `m` and `intlLocale` from useI18n() so copy, dates, and
// decimal separators follow the rider's chosen language.

export function rideTitle(ride: ActivitySummaryOut, m: Messages): string {
  if (ride.is_indoor) return m.rides.titles.indoor;
  return m.rides.titles[ride.bike_type] ?? m.rides.fallbackTitle;
}

// BikeOut.kind is a plain string from the API; fall back to it verbatim.
export function bikeKindLabel(kind: string, m: Messages): string {
  return (m.bikes.kinds as Record<string, string>)[kind] ?? kind;
}

export function rideDate(value: string, intlLocale: string): string {
  return new Date(value).toLocaleDateString(intlLocale, {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

export function rideDistance(metres: number, intlLocale: string): string {
  const km = (metres / 1000).toLocaleString(intlLocale, {
    minimumFractionDigits: 1, maximumFractionDigits: 1,
  });
  return `${km} km`;
}

export function rideDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  return hours ? `${hours}h ${String(remaining).padStart(2, "0")}m` : `${remaining}m`;
}
