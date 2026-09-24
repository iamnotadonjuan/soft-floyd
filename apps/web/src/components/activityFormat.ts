import type { ActivitySummaryOut } from "../api/types";

export function rideTitle(ride: ActivitySummaryOut): string {
  if (ride.is_indoor) return "Indoor ride";
  return {
    road: "Road ride", mtb: "Mountain bike ride", indoor: "Indoor ride", other: "Ride",
  }[ride.bike_type] ?? "Ride";
}

export function rideDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

export function rideDistance(metres: number): string {
  return `${(metres / 1000).toFixed(1)} km`;
}

export function rideDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  return hours ? `${hours}h ${String(remaining).padStart(2, "0")}m` : `${remaining}m`;
}
