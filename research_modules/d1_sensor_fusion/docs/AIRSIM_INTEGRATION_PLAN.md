# D1 AirSim Integration Plan

## Scope

This plan is limited to AirSim/offline research simulation. It describes data adapters and evaluation flow only. It does not define real vehicle control, hardware drivers, fire-control parameters, damage logic, automatic action, or bypass of human authorization.

## Time Base

- Use AirSim simulation time as the canonical clock.
- Every sensor bridge must fill both `measurement_timestamp` and `arrival_timestamp`.
- `measurement_timestamp` comes from the simulated sensor capture time.
- `arrival_timestamp` comes from the fusion process receive time or replay log time.
- Offline replay should preserve original ordering by `arrival_timestamp`.

## Coordinate Frames

Internal fusion uses NED:

```text
x: north / forward
y: east / right
z: down
```

AirSim's default local coordinates are close to NED, so the first integration should treat AirSim world coordinates as `frame_id="ned"` and explicitly record any scene-origin offset in metadata. If later using geodetic metadata, convert WGS84 to a local tangent NED frame before fusion.

## Sensor Bridges

Radar bridge:

- Read target truth from AirSim for research simulation only.
- Convert truth to radar spherical observation `[range, azimuth, elevation, radial_velocity]`.
- Apply distance-dependent covariance and synthetic delay.
- Emit `SensorObservation(modality="radar")`.

Acoustic bridge:

- Emit coarse azimuth and optional `classification_hint` for voiceprint-like identity evidence.
- Use large angular covariance and confidence-dependent noise.
- Do not convert acoustic bearing alone into a false 3D point.

EO bridge:

- Use RGB/depth/segmentation or detector output to produce pixel boxes.
- Emit bbox center `[u_center, v_center]` with camera intrinsics/extrinsics in metadata.
- Use low confidence, small boxes, truncation, and occlusion to inflate covariance.
- Treat EO as a projection constraint, not direct 3D position truth.

## Fusion Node Contract

Input:

```python
SensorObservation(
    observation_id=...,
    sensor_id=...,
    modality="radar" | "acoustic" | "eo",
    measurement_timestamp=sim_capture_time,
    arrival_timestamp=fusion_receive_time,
    frame_id="ned" or "pixel",
    measurement=np.ndarray,
    covariance=np.ndarray,
    confidence=...,
    metadata={...},
)
```

Output:

```python
GlobalTrack(
    global_track_id=...,
    state=[px, py, pz, vx, vy, vz],
    covariance=6x6,
    timestamp=...,
    track_level="coarse" | "stable" | "handover",
    source_support={...},
)
```

`handover` is only a simulation quality label. It is not an authorization state and must not be connected directly to any action chain.

## Offline Evaluation Flow

1. Run an AirSim episode with deterministic random seed.
2. Log simulated truth and generated sensor observations.
3. Replay logs by `arrival_timestamp`.
4. Run both latency-compensated and uncompensated fusion modes.
5. Compute RMSE, continuity, grade consistency, ID switches if multi-target crossing is enabled, and latency ablation.
6. Store plots and Markdown report under the D1 module report directory.

## Future Optional Integrations

- Stone Soup can be used for JPDA/MHT/OOSM research once installed.
- FilterPy can be used as an alternate EKF backend once installed.
- ROS 2 `tf2` can manage coordinate transforms in a distributed simulation.
- These integrations must remain optional so the NumPy/SciPy fallback tests continue to run on the current host.
