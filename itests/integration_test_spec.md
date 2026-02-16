# Integration test plan: deterministic local-command landscape camera

## Scope
- Add a deterministic image generator used as a `local_command` camera source.
- Add an integration test that runs a virtualized 25-hour capture timeline (including day transition and month transition) without waiting in real time.
- Keep all generated runtime artifacts in temporary directories rooted under `itests/`.

## Why this approach
- Running the full app clock for 25 hours in real time is not practical.
- `snap()` already encapsulates the capture loop and file output path logic, so using it with controlled time gives broad integration coverage while staying fast.
- A subprocess-driven generator validates the `local_command` execution path end-to-end.

## Deterministic landscape generator specs
- Output is a JPEG image (default 320x180, configurable).
- Bottom half: green ground.
- Top half: sky color based on sun elevation:
  - day: blue,
  - twilight (around sunrise/sunset): pink blending,
  - night: darker sky.
- Sun and moon positions are derived from:
  - GPS coordinates (lat/lon),
  - timestamp,
  - camera azimuth (`80°`),
  - field of view (`120°`).
- Object visibility uses their azimuth/elevation and projects them into image coordinates.
- Determinism:
  - no randomness,
  - same input args + timestamp => byte-identical output in practice for the same Pillow runtime.

## Integration test specs
- Use a dedicated config template in `itests/config.integration.local_command.yaml` with one camera using `local_command`.
- Runtime setup:
  - create temp root with `tempfile.TemporaryDirectory(dir=itests_dir)`.
  - place `work_dir`, mock-time file, and concrete config there.
- Time virtualization:
  - patch `fenetre.datetime.now()` reads from a mutable virtual clock,
  - patch `fenetre.interruptible_sleep()` to advance the virtual clock instantly,
  - update the generator time-file after each virtual sleep.
- Capture span:
  - start at `2024-01-31T00:00:00Z`,
  - run hourly for 25 hours (26 written frames: 00:00 through next day 01:00),
  - this guarantees day and month transitions.
- Assertions:
  - expected day directories exist (`2024-01-31`, `2024-02-01`),
  - expected frame counts per day (24 and 2),
  - generated noon frame has higher brightness than midnight frame,
  - thread exits cleanly.

## Constraints / tradeoffs
- This validates the snap loop + local command + file layout, not the full process-level thread orchestration from `load_and_apply_configuration()`.
- The generator is intentionally simple to keep CPU usage low for Raspberry Pi-class environments.
