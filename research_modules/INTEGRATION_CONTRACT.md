# Research Module Integration Contract

This contract applies to the offline D1-D6 research modules. It defines data
handoff rules only; it does not define real-world control, engagement, or
hardware behavior.

## Track Identity

- `global_track_id` is center-owned and must not be rewritten by D3, D4, D5, or
  D6.
- `truth_id` is evaluation-only and must never be used as an operational
  assignment key.
- `track_version` is separate from `plan_version`. A terminal association must
  match the assigned `global_track_id` and the current `track_version`.

## Time And Frames

- Observations must carry both `measurement_timestamp` and `arrival_timestamp`.
- Fusion and association use `measurement_timestamp`; `arrival_timestamp` is
  for latency accounting and replay ordering.
- The shared workspace is local NED. D1 rejects unconverted ENU, WGS84, or
  arbitrary sensor-frame observations. EO detections are allowed in `pixel`
  frame before projection.
- Canonical tracks exported from D1 must include `frame_id="ned"`, `valid_at`,
  `published_at`, 6D state, and 6x6 covariance.

## Covariance Handoff

- D1 publishes 6x6 covariance.
- D2 consumes the XY covariance block.
- D3 consumes normalized uncertainty derived from covariance; it must not infer
  threat from track quality.
- D5 consumes XYZ covariance for image-plane projection.
- D6 may record covariance trace for reports.

## Assignment And Authorization

- D3 emits candidate plans with `human_authorization_state="required"` even if
  a caller misconfigures the planner.
- A D3 plan is not valid for terminal lock until an external review layer marks
  it as `authorized`, `approved`, `human_approved`, or `operator_approved`.
- D3 rejects stale `previous_plan` versions.
- D5 defaults to version-checked terminal association and returns `hold` for
  unauthorized or version-mismatched assignments.

## Terminal States

The terminal decision vocabulary is:

- `locked`: unique geometry match, current version, authorized assignment, and
  sufficient local MOT quality.
- `ambiguous`: multiple plausible local tracks, poor local track quality, or
  nonverified identity overlap.
- `hold`: verified friend overlap, authorization failure, or version mismatch.
- `reacquire`: assigned track unavailable or no local visual track inside gate.

Unknown identity is not hostile identity. `ambiguous` and `hold` must not be
converted into automatic authorization.

## Degraded Mode

- D4 must not return from degraded/failed to normal on heartbeat alone.
  Recovery requires dual-track merge and human acceptance.
- Degraded hierarchy is center C2 -> secondary reconnaissance node -> fully
  distributed CBBA. Secondary nodes are modeled with
  `node_role="secondary_recon"` and may be `coordinator_only=True`.
- Backup, secondary-node, and lease priority are evaluated before ordinary
  resource quality.
- Nonconverged CBBA results are audit data only and must not publish active
  assignments.
- Secondary reconnaissance image cues are scoped to local resources. They can
  assist D5 terminal association, but cannot authorize terminal lock, override
  track-version checks, or rewrite `global_track_id`.

## Evaluation Rules

- D6 counts only effective assignment authorization states as assigned.
- High-threat targets remain unassigned if no effective assignment exists.
- Terminal ambiguity and friend hold events are de-duplicated across
  `TerminalRecord` and `EventRecord`.
