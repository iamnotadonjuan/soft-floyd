import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { saveProfile } from "../api/client";
import type { GoalSlug, Profile } from "../api/types";

const DISCIPLINES = [
  { value: "road", label: "Road", emoji: "🚴" },
  { value: "mtb", label: "Mountain Bike", emoji: "🚵" },
  { value: "gravel", label: "Gravel", emoji: "🪨" },
] as const;

const GOALS: { slug: GoalSlug; label: string }[] = [
  { slug: "climbing", label: "Climbing" },
  { slug: "descending", label: "Descending / Technical" },
  { slug: "endurance", label: "Endurance" },
  { slug: "sprinting", label: "Sprinting" },
  { slug: "intervals", label: "Structured Intervals" },
  { slug: "recovery", label: "Base / Recovery" },
];

interface ProfileFormProps {
  initial?: Partial<Profile>;
  title: string;
  subtitle?: string;
}

export default function ProfileForm({ initial, title, subtitle }: ProfileFormProps) {
  const navigate = useNavigate();

  const [discipline, setDiscipline] = useState<"road" | "mtb" | "gravel">(
    initial?.discipline ?? "road"
  );
  const [city, setCity] = useState(initial?.city ?? "");
  const [country, setCountry] = useState(initial?.country ?? "");
  const [terrainNotes, setTerrainNotes] = useState(initial?.terrain_notes ?? "");
  const [goals, setGoals] = useState<GoalSlug[]>(initial?.goals ?? []);
  const [notes, setNotes] = useState(initial?.freeform_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleGoal(slug: GoalSlug) {
    setGoals((prev) =>
      prev.includes(slug) ? prev.filter((g) => g !== slug) : [...prev, slug]
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (goals.length === 0) {
      setError("Please select at least one training goal.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveProfile({
        discipline,
        city: city.trim() || undefined,
        country: country.trim() || undefined,
        terrain_notes: terrainNotes.trim() || undefined,
        goals,
        freeform_notes: notes.trim() || undefined,
      });
      navigate("/activities");
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">{title}</h1>
      {subtitle && <p className="text-gray-500 text-sm mb-6">{subtitle}</p>}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Discipline */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Primary discipline
          </label>
          <div className="flex gap-3">
            {DISCIPLINES.map((d) => (
              <button
                key={d.value}
                type="button"
                onClick={() => setDiscipline(d.value)}
                className={`flex-1 flex flex-col items-center gap-1 py-3 rounded-xl border-2 transition-colors text-sm font-medium ${
                  discipline === d.value
                    ? "border-indigo-600 bg-indigo-50 text-indigo-700"
                    : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
                }`}
              >
                <span className="text-2xl">{d.emoji}</span>
                {d.label}
              </button>
            ))}
          </div>
        </div>

        {/* Location */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Training city
            </label>
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="e.g. Medellín"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Country
            </label>
            <input
              type="text"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="e.g. CO or Colombia"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Terrain notes */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Terrain notes <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={terrainNotes}
            onChange={(e) => setTerrainNotes(e.target.value)}
            placeholder="e.g. very hilly, 1500m elevation gains"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {/* Goals */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Training goals <span className="text-gray-400 font-normal">(select all that apply)</span>
          </label>
          <div className="flex flex-wrap gap-2">
            {GOALS.map(({ slug, label }) => (
              <button
                key={slug}
                type="button"
                onClick={() => toggleGoal(slug)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                  goals.includes(slug)
                    ? "bg-indigo-600 text-white border-indigo-600"
                    : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Free-text notes */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Additional notes <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="e.g. building toward a 100km hilly event in October"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          />
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
        )}

        <button
          type="submit"
          disabled={saving || goals.length === 0}
          className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {saving ? "Saving…" : "Save profile"}
        </button>
      </form>
    </div>
  );
}
