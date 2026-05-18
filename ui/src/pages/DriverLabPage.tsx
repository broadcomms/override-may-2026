import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import type {
  TorcsDriverConfigWire,
  TorcsDriverProfile,
  TorcsDriverProfileSummary,
} from "@/api/types";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { hasTorcsSurface } from "@/lib/env";

const SPEED_FIELDS = [
  "target_speed_kmh",
  "min_target_speed_kmh",
  "centre_clamp_m",
  "centre_factor",
  "curvature_clamp",
  "curvature_penalty",
  "visible_road_threshold_m",
  "visible_road_penalty",
] as const;

const STEERING_FIELDS = ["steer_gain", "centering_gain", "track_sensor_gain"] as const;
const THROTTLE_FIELDS = [
  "steer_speed_penalty_kmh",
  "accel_ramp_up",
  "accel_decay",
  "low_speed_boost_cutoff_kmh",
  "low_speed_boost_denominator_offset",
] as const;
const BRAKING_FIELDS = [
  "overspeed_margin_kmh",
  "overspeed_divisor_kmh",
  "overspeed_cap",
  "angle_threshold_rad",
  "angle_min_speed_kmh",
  "angle_brake_force",
  "track_pos_threshold",
  "track_pos_min_speed_kmh",
  "track_pos_brake_force",
] as const;
const TRACTION_FIELDS = ["slip_threshold", "accel_cut"] as const;
const LAUNCH_GUARD_FIELDS = [
  "duration_s",
  "track_pos_limit",
  "angle_limit_rad",
  "steer_angle_gain",
  "steer_track_pos_gain",
  "steer_clip",
] as const;
const RECOVERY_FIELDS = [
  "offtrack_trackpos_threshold",
  "offtrack_angle_threshold_rad",
  "angle_recovery_speed_cap_kmh",
  "stuck_time_threshold_s",
  "recovery_speed_kmh",
  "steer_back_angle_gain",
  "steer_back_track_pos_gain",
  "high_speed_brake_force",
  "damaged_reverse_speed_threshold_kmh",
  "damaged_reverse_accel",
  "damaged_reverse_track_pos_gain",
  "damaged_reverse_steer_clip",
  "backward_relaunch_speed_threshold_kmh",
  "backward_relaunch_accel",
  "backward_relaunch_angle_gain",
  "backward_relaunch_track_pos_gain",
  "backward_relaunch_steer_clip",
  "fallback_accel",
  "fallback_brake",
] as const;

const FIELD_LABEL_OVERRIDES: Record<string, string> = {
  target_speed_kmh: "Target speed cap km/h",
  min_target_speed_kmh: "Minimum target speed km/h",
  centre_clamp_m: "Centre sensor clamp m",
  centre_factor: "Centre sensor gain",
};

function cloneProfile(profile: TorcsDriverProfile): TorcsDriverProfile {
  return JSON.parse(JSON.stringify(profile)) as TorcsDriverProfile;
}

function formatFieldLabel(field: string): string {
  if (FIELD_LABEL_OVERRIDES[field]) return FIELD_LABEL_OVERRIDES[field];
  return field
    .replace(/_kmh/g, " km/h")
    .replace(/_rad/g, " rad")
    .replace(/_s$/g, " s")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function computeStraightLineTarget(config: TorcsDriverConfigWire): { raw: number; clipped: number } {
  const raw = config.speed.min_target_speed_kmh + (config.speed.centre_clamp_m * config.speed.centre_factor);
  const clipped = Math.max(
    config.speed.min_target_speed_kmh,
    Math.min(raw, config.speed.target_speed_kmh),
  );
  return { raw, clipped };
}

function describeApiError(error: unknown, fallback: string): string {
  if (error instanceof OverrideApiError) {
    return `${error.payload.message}${error.payload.detail ? ` — ${error.payload.detail}` : ""}`;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

type EditorMode = "edit" | "create";

export function DriverLabPage() {
  const torcsSurface = hasTorcsSurface();
  const [profiles, setProfiles] = useState<TorcsDriverProfileSummary[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [draft, setDraft] = useState<TorcsDriverProfile | null>(null);
  const [editorMode, setEditorMode] = useState<EditorMode>("edit");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TorcsDriverProfile | null>(null);

  const selectedSummary = useMemo(
    () => profiles.find((profile) => profile.profile_id === selectedProfileId) ?? null,
    [profiles, selectedProfileId],
  );
  const saveCreatesNew = editorMode === "create" || Boolean(draft?.read_only);
  const straightLineTarget = useMemo(
    () => (draft ? computeStraightLineTarget(draft.config) : null),
    [draft],
  );

  const loadProfile = useCallback(async (profileId: string) => {
    setLoading(true);
    setError(null);
    try {
      const profile = await api.getTorcsDriverProfile(profileId);
      setSelectedProfileId(profile.profile_id);
      setDraft(cloneProfile(profile));
      setEditorMode("edit");
    } catch (nextError) {
      setError(describeApiError(nextError, "Failed to load the selected driver profile."));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshProfiles = useCallback(async (profileIdHint?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.listTorcsDriverProfiles();
      setProfiles(response.profiles);
      const candidateId =
        profileIdHint
        ?? (selectedProfileId && response.profiles.some((profile) => profile.profile_id === selectedProfileId)
          ? selectedProfileId
          : response.profiles[0]?.profile_id
          ?? null);
      if (candidateId) {
        const profile = await api.getTorcsDriverProfile(candidateId);
        setSelectedProfileId(profile.profile_id);
        setDraft(cloneProfile(profile));
        setEditorMode("edit");
      } else {
        setSelectedProfileId(null);
        setDraft(null);
      }
    } catch (nextError) {
      setError(describeApiError(nextError, "Failed to load driver profiles."));
    } finally {
      setLoading(false);
    }
  }, [selectedProfileId]);

  useEffect(() => {
    if (!torcsSurface) return;
    void refreshProfiles();
  }, [refreshProfiles, torcsSurface]);

  const updateDraft = useCallback((updater: (current: TorcsDriverProfile) => TorcsDriverProfile) => {
    setDraft((current) => (current ? updater(current) : current));
  }, []);

  const updateMeta = useCallback((field: "name" | "description", value: string) => {
    updateDraft((current) => ({
      ...current,
      [field]: field === "description" && value.trim() === "" ? null : value,
    }));
  }, [updateDraft]);

  const updateConfigField = useCallback((
    section: keyof TorcsDriverConfigWire,
    field: string,
    value: number | boolean,
  ) => {
    updateDraft((current) => ({
      ...current,
      config: {
        ...current.config,
        [section]: {
          ...((current.config[section] as unknown) as Record<string, number | boolean | number[]>),
          [field]: value,
        },
      } as TorcsDriverConfigWire,
    }));
  }, [updateDraft]);

  const updateGearSpeed = useCallback((index: number, value: number) => {
    updateDraft((current) => {
      const nextGearSpeeds = [...current.config.gear.gear_speeds_kmh];
      nextGearSpeeds[index] = value;
      return {
        ...current,
        config: {
          ...current.config,
          gear: {
            ...current.config.gear,
            gear_speeds_kmh: nextGearSpeeds,
          },
        },
      };
    });
  }, [updateDraft]);

  const startNewFromCurrent = useCallback(() => {
    if (!draft) return;
    const cloned = cloneProfile(draft);
    cloned.profile_id = "new-driver-profile";
    cloned.name = draft.name.endsWith(" Copy") ? draft.name : `${draft.name} Copy`;
    cloned.origin = "user_saved";
    cloned.read_only = false;
    setDraft(cloned);
    setEditorMode("create");
    setMessage("Editing a new profile draft based on the currently selected setup.");
    setError(null);
  }, [draft]);

  const validateDraft = useCallback(async () => {
    if (!draft) return;
    setValidating(true);
    setError(null);
    setMessage(null);
    try {
      const validated = await api.validateTorcsDriverConfig(draft.config);
      updateDraft((current) => ({ ...current, config: validated.config }));
      setMessage("Driver profile config validated successfully.");
    } catch (nextError) {
      setError(describeApiError(nextError, "Driver profile validation failed."));
    } finally {
      setValidating(false);
    }
  }, [draft, updateDraft]);

  const saveDraft = useCallback(async () => {
    if (!draft) return;
    if (draft.name.trim() === "") {
      setError("Driver profile name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const validated = await api.validateTorcsDriverConfig(draft.config);
      if (saveCreatesNew) {
        const created = await api.createTorcsDriverProfile({
          name: draft.name.trim(),
          description: draft.description,
          config: validated.config,
        });
        await refreshProfiles(created.profile_id);
        setMessage(`Created driver profile ${created.name}.`);
      } else {
        const updated = await api.updateTorcsDriverProfile(draft.profile_id, {
          name: draft.name.trim(),
          description: draft.description,
          config: validated.config,
        });
        await refreshProfiles(updated.profile_id);
        setMessage(`Saved changes to ${updated.name}.`);
      }
    } catch (nextError) {
      setError(describeApiError(nextError, "Failed to save the driver profile."));
    } finally {
      setSaving(false);
    }
  }, [draft, refreshProfiles, saveCreatesNew]);

  const duplicateSelected = useCallback(async () => {
    if (!selectedProfileId || !draft) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const duplicated = await api.duplicateTorcsDriverProfile(selectedProfileId, {
        name: draft.name.endsWith(" Copy") ? draft.name : `${draft.name} Copy`,
      });
      await refreshProfiles(duplicated.profile_id);
      setMessage(`Duplicated ${draft.name} into ${duplicated.name}.`);
    } catch (nextError) {
      setError(describeApiError(nextError, "Failed to duplicate the selected profile."));
    } finally {
      setSaving(false);
    }
  }, [draft, refreshProfiles, selectedProfileId]);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await api.deleteTorcsDriverProfile(deleteTarget.profile_id);
      setDeleteTarget(null);
      await refreshProfiles();
      setMessage(`Deleted driver profile ${deleteTarget.name}.`);
    } catch (nextError) {
      setError(describeApiError(nextError, "Failed to delete the driver profile."));
    } finally {
      setSaving(false);
    }
  }, [deleteTarget, refreshProfiles]);

  if (!torcsSurface) {
    return <Navigate to="/upload" replace />;
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8 space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <div className="text-[11px] uppercase tracking-[0.24em] text-muted font-mono">
            Driver Lab
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-text">
            Tune TORCS launch behavior before the next run.
          </h1>
          <p className="max-w-3xl text-sm text-muted">
            Driver profiles stay in OVERRIDE storage, are validated against the shared runtime contract,
            and are snapshotted into each live session at launch.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/upload"
            className="inline-flex items-center rounded-pill border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:text-text"
          >
            Back to Upload
          </Link>
          <button
            type="button"
            onClick={startNewFromCurrent}
            disabled={!draft || loading || saving}
            className="inline-flex items-center rounded-pill border border-border bg-surface px-3 py-1.5 text-sm transition-colors hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            New from current
          </button>
        </div>
      </header>

      {(error || message) && (
        <section
          className={`rounded-card border px-4 py-3 text-sm ${
            error ? "border-warning/40 bg-warning/10 text-muted" : "border-accent/30 bg-accent/10 text-muted"
          }`}
        >
          {error ?? message}
        </section>
      )}

      <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="rounded-card border border-border bg-surface p-4">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.24em] text-muted font-mono">
                Saved profiles
              </div>
              <div className="text-xs text-muted mt-1">
                {profiles.length} profile{profiles.length === 1 ? "" : "s"}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void refreshProfiles(selectedProfileId)}
              disabled={loading || saving}
              className="rounded-pill border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:text-text disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Refresh
            </button>
          </div>

          <div className="space-y-2">
            {profiles.map((profile) => {
              const active = profile.profile_id === selectedProfileId;
              return (
                <button
                  key={profile.profile_id}
                  type="button"
                  onClick={() => void loadProfile(profile.profile_id)}
                  className={`w-full rounded-card border px-3 py-3 text-left transition-colors ${
                    active
                      ? "border-accent bg-accent/10"
                      : "border-border bg-surface-2 hover:border-accent/40 hover:bg-surface"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-text">{profile.name}</div>
                      <div className="mt-1 text-xs text-muted line-clamp-2">
                        {profile.description ?? "No description yet."}
                      </div>
                    </div>
                    <span
                      className={`rounded-pill px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] ${
                        profile.read_only ? "bg-border/70 text-muted" : "bg-accent/15 text-accent"
                      }`}
                    >
                      {profile.read_only ? "default" : "saved"}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="rounded-card border border-border bg-surface p-5">
          {loading && <p className="text-sm text-muted">Loading driver profile editor…</p>}

          {!loading && !draft && (
            <p className="text-sm text-muted">No driver profiles are available yet.</p>
          )}

          {!loading && draft && (
            <div className="space-y-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] uppercase tracking-[0.24em] text-muted font-mono">
                      {saveCreatesNew ? "Create draft" : "Edit profile"}
                    </span>
                    <span className="rounded-pill border border-border px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-muted">
                      {selectedSummary?.origin ?? draft.origin}
                    </span>
                  </div>
                  <h2 className="text-2xl font-semibold text-text">{draft.name}</h2>
                  <p className="max-w-3xl text-sm text-muted">
                    {draft.read_only && editorMode === "edit"
                      ? "This shipped default is read-only. Saving will create a new user profile copy instead of mutating the baseline."
                      : editorMode === "create"
                        ? "You are editing a new profile draft. Saving will add it to local Driver Lab storage."
                        : "Changes here update the selected user profile and will be used on the next live TORCS launch."}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void validateDraft()}
                    disabled={validating || saving}
                    className="rounded-pill border border-border px-3 py-1.5 text-sm transition-colors hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {validating ? "Validating…" : "Validate config"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void duplicateSelected()}
                    disabled={!selectedProfileId || saving || loading}
                    className="rounded-pill border border-border px-3 py-1.5 text-sm transition-colors hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Duplicate
                  </button>
                  <button
                    type="button"
                    onClick={() => void saveDraft()}
                    disabled={saving || validating}
                    className="rounded-pill bg-accent px-3 py-1.5 text-sm font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {saving ? "Saving…" : saveCreatesNew ? "Save as new profile" : "Save changes"}
                  </button>
                  {!draft.read_only && editorMode === "edit" && (
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(draft)}
                      disabled={saving}
                      className="rounded-pill border border-danger/40 px-3 py-1.5 text-sm text-danger transition-colors hover:bg-danger/10 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] uppercase tracking-wider text-muted">Profile name</span>
                  <input
                    type="text"
                    value={draft.name}
                    onChange={(e) => updateMeta("name", e.target.value)}
                    disabled={saving}
                    className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-text disabled:opacity-50"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] uppercase tracking-wider text-muted">Description</span>
                  <input
                    type="text"
                    value={draft.description ?? ""}
                    onChange={(e) => updateMeta("description", e.target.value)}
                    disabled={saving}
                    className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-text disabled:opacity-50"
                  />
                </label>
              </div>

              <div className="grid gap-4 2xl:grid-cols-2">
                <ConfigSectionCard
                  title="Speed envelope"
                  description={
                    straightLineTarget
                      ? `Target speed cap only clips the computed target. With the current minimum target, centre clamp, and centre gain, the ideal straight-line target is ${straightLineTarget.clipped.toFixed(1)} km/h${straightLineTarget.raw > straightLineTarget.clipped ? `, capped from ${straightLineTarget.raw.toFixed(1)} km/h` : ""}, before curvature and visibility penalties.`
                      : "Base target speed and corner visibility penalties."
                  }
                >
                  {SPEED_FIELDS.map((field) => (
                    <NumericField
                      key={field}
                      label={formatFieldLabel(field)}
                      value={draft.config.speed[field]}
                      onChange={(value) => updateConfigField("speed", field, value)}
                      disabled={saving}
                    />
                  ))}
                </ConfigSectionCard>

                <ConfigSectionCard title="Steering" description="How aggressively the driver recenters and follows track sensors.">
                  {STEERING_FIELDS.map((field) => (
                    <NumericField
                      key={field}
                      label={formatFieldLabel(field)}
                      value={draft.config.steering[field]}
                      onChange={(value) => updateConfigField("steering", field, value)}
                      disabled={saving}
                    />
                  ))}
                </ConfigSectionCard>

                <ConfigSectionCard title="Throttle" description="Acceleration ramp, decay, and low-speed boost behavior.">
                  {THROTTLE_FIELDS.map((field) => (
                    <NumericField
                      key={field}
                      label={formatFieldLabel(field)}
                      value={draft.config.throttle[field]}
                      onChange={(value) => updateConfigField("throttle", field, value)}
                      disabled={saving}
                    />
                  ))}
                </ConfigSectionCard>

                <ConfigSectionCard title="Braking" description="Overspeed, angle, and track-position braking rules.">
                  {BRAKING_FIELDS.map((field) => (
                    <NumericField
                      key={field}
                      label={formatFieldLabel(field)}
                      value={draft.config.braking[field]}
                      onChange={(value) => updateConfigField("braking", field, value)}
                      disabled={saving}
                    />
                  ))}
                </ConfigSectionCard>

                <ConfigSectionCard title="Gear speeds" description="Upshift thresholds per forward gear in km/h.">
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {draft.config.gear.gear_speeds_kmh.map((speed, index) => (
                      <NumericField
                        key={`gear-${index}`}
                        label={`Gear ${index + 1}`}
                        value={speed}
                        onChange={(value) => updateGearSpeed(index, value)}
                        disabled={saving}
                      />
                    ))}
                  </div>
                </ConfigSectionCard>

                <ConfigSectionCard title="Traction" description="Slip threshold plus acceleration cut when wheelspin rises.">
                  <label className="flex items-center justify-between rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                    <span className="text-text">Traction enabled</span>
                    <input
                      type="checkbox"
                      checked={draft.config.traction.enabled}
                      onChange={(e) => updateConfigField("traction", "enabled", e.target.checked)}
                      disabled={saving}
                    />
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {TRACTION_FIELDS.map((field) => (
                      <NumericField
                        key={field}
                        label={formatFieldLabel(field)}
                        value={draft.config.traction[field]}
                        onChange={(value) => updateConfigField("traction", field, value)}
                        disabled={saving}
                      />
                    ))}
                  </div>
                </ConfigSectionCard>

                <ConfigSectionCard title="Launch guard" description="Short-window guardrails for unstable starts and early steering corrections.">
                  {LAUNCH_GUARD_FIELDS.map((field) => (
                    <NumericField
                      key={field}
                      label={formatFieldLabel(field)}
                      value={draft.config.launch_guard[field]}
                      onChange={(value) => updateConfigField("launch_guard", field, value)}
                      disabled={saving}
                    />
                  ))}
                </ConfigSectionCard>

                <ConfigSectionCard title="Recovery" description="Off-track recovery, reverse, and relaunch behavior when the car gets stuck.">
                  {RECOVERY_FIELDS.map((field) => (
                    <NumericField
                      key={field}
                      label={formatFieldLabel(field)}
                      value={draft.config.recovery[field]}
                      onChange={(value) => updateConfigField("recovery", field, value)}
                      disabled={saving}
                    />
                  ))}
                </ConfigSectionCard>
              </div>
            </div>
          )}
        </section>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete driver profile?"
        body={
          <p>
            This removes <span className="font-medium text-text">{deleteTarget?.name}</span> from
            local Driver Lab storage. Existing sessions keep their saved config snapshots.
          </p>
        }
        confirmLabel="Delete profile"
        confirmVariant="danger"
        busy={saving}
        onConfirm={() => void confirmDelete()}
        onCancel={() => {
          if (!saving) setDeleteTarget(null);
        }}
      />
    </div>
  );
}

function ConfigSectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-card border border-border bg-surface-2 p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        <p className="mt-1 text-xs text-muted">{description}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function NumericField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  disabled: boolean;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wider text-muted">{label}</span>
      <input
        type="number"
        value={Number.isFinite(value) ? value : 0}
        step="0.01"
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text disabled:opacity-50"
      />
    </label>
  );
}