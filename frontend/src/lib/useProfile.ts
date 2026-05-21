import { useEffect, useState } from "react";
import { getProfile } from "../api/client";
import type { Profile } from "../api/types";

/**
 * Fetch the rider profile from the API.
 *
 * Returns:
 *   undefined — still loading
 *   null      — no profile set (404)
 *   Profile   — profile loaded
 */
export function useProfile() {
  const [profile, setProfile] = useState<Profile | null | undefined>(undefined);

  const fetchProfile = async () => {
    try {
      setProfile(await getProfile());
    } catch {
      setProfile(null);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, []);

  return { profile, refetch: fetchProfile };
}
