# AGENTS.md

## Project

Body Controller

## Mission

Build a configurable physical input system that allows a player to control keyboard-based games using body movements detected through a camera.

The project should NOT be optimized for one specific game.

The system must separate:

1. Observing the player
2. Detecting body pose
3. Recognizing a physical gesture
4. Representing that gesture as an event
5. Mapping the event to a configured control
6. Sending the control to the game

The primary hackathon MVP is the laptop implementation.

A separate mobile implementation is being developed independently.

---

# Core Architecture

The intended pipeline is:

```text
Camera
   ↓
Pose Detection
   ↓
Gesture Recognition
   ↓
Gesture Event
   ↓
Control Mapping
   ↓
Input Output
   ↓
Game
```

Each stage should have a clear responsibility.

Avoid tightly coupling stages.

---

# Critical Architecture Rule

Pose and gesture code MUST NOT directly decide which keyboard key belongs to a gesture.

Avoid designs conceptually equivalent to:

```python
if jump_detected:
    press("space")
```

Instead:

```python
gesture = Gesture.JUMP
```

A separate mapping layer should determine:

```python
key = active_profile.get_mapping(gesture)
```

This separation is fundamental to the product.

The same `JUMP` event may produce:

```text
SPACE
```

in one profile and:

```text
UP
```

in another.

---

# Canonical Gesture Events

Start with:

```text
JUMP
CROUCH
LEAN_LEFT
LEAN_RIGHT
PRIMARY_GESTURE
```

These identifiers represent physical actions and must not contain game-specific meaning.

Do not introduce multiple names for the same action.

For example, avoid simultaneously creating:

```text
JUMP
JUMPING
PLAYER_JUMP
UPWARD_JUMP
```

Prefer one canonical event:

```text
JUMP
```

Additional gesture events may be introduced when justified.

---

# Laptop MVP

The laptop implementation is the primary development target.

The laptop pipeline should eventually be capable of operating completely independently:

```text
Laptop webcam
      ↓
Pose detection
      ↓
Gesture recognition
      ↓
Gesture event
      ↓
Profile mapping
      ↓
Keyboard output
      ↓
Game
```

Do not make laptop functionality dependent on mobile functionality.

---

# Mobile

The `/mobile` directory belongs to the separate mobile implementation.

Do not redesign or modify mobile architecture unless explicitly asked.

Mobile may use different frameworks or pose-estimation technology.

Where interoperability is required, communicate through shared gesture concepts rather than sharing platform-specific camera or vision implementation details.

The laptop implementation must continue working when the mobile implementation is unavailable.

---

# Laptop Modules

The laptop implementation should maintain clear module boundaries.

Suggested responsibilities:

## Camera

Responsible for:

- Opening the selected camera
- Reading frames
- Releasing camera resources
- Camera-related configuration

The camera layer should not recognize gestures.

## Pose

Responsible for:

- Running pose estimation
- Converting frames into pose-landmark results
- Returning normalized pose information

The pose layer should not generate keyboard input.

## Gestures

Responsible for:

- Interpreting pose landmarks
- Identifying physical actions
- Maintaining gesture state where necessary
- Applying thresholds
- Handling gesture cooldown/debounce behavior
- Emitting canonical gesture events

## Calibration

Responsible for user-specific baseline information when needed.

Examples may include neutral body position or relative movement thresholds.

Avoid assuming identical body dimensions, camera position, or distance for every user.

## Profiles

Responsible for:

- Loading mappings
- Validating mappings
- Switching active profiles
- Mapping gesture events to configured controls

## Input

Responsible for communicating configured keyboard actions to the operating system.

This module receives control commands.

It should not perform pose recognition.

## Application

Responsible for:

- Connecting the modules
- Managing application lifecycle
- Processing the pipeline
- Handling clean startup and shutdown

## UI / Debug View

May display:

- Camera preview
- Pose landmarks
- Active gesture
- Active profile
- Calibration state
- Mapping information
- FPS or useful debugging information

Avoid spending significant development effort on visual polish until the end-to-end pipeline works reliably.

---

# Gesture Recognition Philosophy

Reliability is more important than quantity.

Prefer:

```text
4-5 reliable gestures
```

over:

```text
15 unreliable gestures
```

When possible, use pose landmarks and interpretable geometric/state-based logic before introducing custom model training.

Gesture implementations should consider:

- Relative body positions
- Neutral calibration
- Confidence thresholds
- Temporal state
- Cooldowns
- Debouncing
- Hysteresis where useful

A gesture should not repeatedly fire every frame merely because the player remains in the triggering position.

Example:

A single jump should normally create one `JUMP` event rather than dozens of consecutive `JUMP` events.

---

# Initial Gestures

Priority:

1. LEAN_LEFT
2. LEAN_RIGHT
3. JUMP
4. CROUCH
5. PRIMARY_GESTURE

Implement and validate gestures incrementally.

Do not attempt to build the entire gesture library simultaneously.

---

# Profiles

Game mappings must be external and configurable.

Example:

```json
{
  "name": "Example Platformer",
  "mappings": {
    "JUMP": "space",
    "CROUCH": "s",
    "LEAN_LEFT": "a",
    "LEAN_RIGHT": "d",
    "PRIMARY_GESTURE": "e"
  }
}
```

Do not hardcode these mappings inside gesture detectors.

Profile configuration should eventually make changing games possible without modifying recognition code.

---

# Game Scope

Optimize initially for games that:

- Accept keyboard controls
- Require relatively few discrete actions
- Provide immediate visual feedback
- Do not require precise mouse aiming

Good categories:

- Endless runners
- Simple platformers
- Simple keyboard-controlled games

Do not prioritize:

- Competitive FPS games
- Complex mouse aiming
- Large control schemes
- Games requiring many simultaneous inputs

---

# Testing

Prioritize unit tests for deterministic logic.

Especially test:

- Gesture classification
- Gesture state transitions
- Cooldowns/debouncing
- Profile parsing
- Mapping validation

Camera and game integration can be validated separately from deterministic gesture logic.

Whenever possible, avoid requiring a live webcam simply to test landmark-to-gesture classification.

---

# Shared Code

The `/shared` directory should contain only definitions that genuinely need to be shared across implementations.

Possible examples:

- Gesture-event schema
- Gesture names
- Protocol definitions

Do not move laptop-specific functionality into `/shared` merely for architectural symmetry.

---

# Engineering Guidelines

When generating or modifying code:

1. Keep modules focused.
2. Prefer small, understandable abstractions.
3. Do not create architecture for hypothetical future requirements without justification.
4. Preserve the separation between recognition and control mapping.
5. Add type hints where useful.
6. Add docstrings to non-obvious public classes/functions.
7. Handle resources cleanly, especially cameras.
8. Fail clearly when required resources are unavailable.
9. Avoid hidden global state where practical.
10. Keep configuration outside gesture algorithms when possible.
11. Do not commit secrets or credentials.
12. Do not add network/cloud dependencies unless required by a feature.

---

# Performance Priorities

For the live-control pipeline prioritize:

1. Input responsiveness
2. Stable tracking
3. Reliable gesture recognition
4. Low accidental-trigger rate
5. Maintainable code
6. Visual polish

Avoid sacrificing responsiveness for unnecessary processing.

---

# MVP Definition of Done

The laptop MVP is successful when:

1. A camera feed opens reliably.
2. The player's pose can be tracked in real time.
3. At least four physical actions are reliably distinguished.
4. Physical actions emit canonical gesture events.
5. Gesture events pass through a configurable profile.
6. Configured keyboard controls are emitted.
7. A keyboard-controlled game responds to those controls.
8. Profiles can be changed without rewriting pose-recognition code.
9. Two different games can be demonstrated using different mappings.

---

# Non-Goals Until MVP Works

Do not prioritize:

- Universal support for every game
- Automatic game recognition
- AI-generated control profiles
- Precise mouse aiming
- Large gesture libraries
- Custom-trained gesture models
- Multiplayer control
- Cloud infrastructure
- Advanced analytics
- Complex account systems
- Cross-platform desktop support
- Mobile-dependent functionality
- Highly polished UI

These are stretch concepts only.

---

# Development Priority

Work in approximately this order:

```text
1. Camera capture
       ↓
2. Pose detection
       ↓
3. Pose visualization/debugging
       ↓
4. Gesture event definitions
       ↓
5. Lean detection
       ↓
6. Jump detection
       ↓
7. Crouch detection
       ↓
8. Gesture state/debounce
       ↓
9. Keyboard output
       ↓
10. Profile loader
       ↓
11. First real game
       ↓
12. Second real game
       ↓
13. Calibration/reliability improvements
       ↓
14. UI polish
       ↓
15. Stretch features
```

Do not skip directly to UI polish or stretch features while the core control pipeline is unreliable.

---

# Primary Product Principle

The computer vision system answers:

> What did the player physically do?

The profile system answers:

> What should that movement do in this game?

Keep those questions separate.