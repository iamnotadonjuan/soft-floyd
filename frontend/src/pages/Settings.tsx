import { useProfile } from "../lib/useProfile";
import ProfileForm from "../components/ProfileForm";

export default function Settings() {
  const { profile } = useProfile();

  if (profile === undefined) {
    return <div className="py-8 text-gray-400">Loading profile…</div>;
  }

  return (
    <div className="py-8">
      <ProfileForm
        initial={profile ?? undefined}
        title="Settings — Rider Profile"
        subtitle="Update your goals and preferences. Changes take effect on the next analysis."
      />
    </div>
  );
}
