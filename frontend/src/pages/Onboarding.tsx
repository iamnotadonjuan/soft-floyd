import ProfileForm from "../components/ProfileForm";

export default function Onboarding() {
  return (
    <div className="py-8">
      <ProfileForm
        title="Welcome to Soft Floyd 🚴"
        subtitle="Tell the coach a bit about you so every analysis is tailored to your goals."
      />
    </div>
  );
}
