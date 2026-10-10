# AGENTS.md

# Body Controller

## Project Mission

Body Controller is a hackathon project that turns physical body movements into configurable controls for keyboard-based games.

The system uses camera-based pose detection to recognize movements such as jumping, crouching, and leaning. Recognized movements are represented as platform-independent gesture events and then mapped to game-specific keyboard controls.

The project is NOT intended to build motion controls for one specific game.

The core product is a configurable physical input layer:

Camera
→ Pose Detection
→ Gesture Recognition
→ Gesture Event
→ Control Mapping
→ Keyboard Input
→ Game

The primary hackathon MVP is the laptop implementation.

A separate mobile implementation is being developed independently by another developer.


# Primary Product Principle

The computer-vision and gesture system answers:

"What did the player physically do?"

The profile system answers:

"What should that movement do in this game?"

These responsibilities MUST remain separate.

For example:

Player jumps
→ Gesture system emits JUMP
→ Active game profile maps JUMP to SPACE
→ Input controller sends SPACE

The gesture engine should never care that JUMP maps to SPACE.


# Technology Stack

## Runtime

Use:

- Python 3.12

The laptop implementation is a Python 3.12 application.

Do not change the Python version without a concrete compatibility reason.


## Computer Vision

### MediaPipe Pose Landmarker

Use MediaPipe Pose Landmarker for real-time human pose estimation.

MediaPipe is responsible for converting camera images into body landmarks.

Use a pretrained MediaPipe-compatible pose model stored under:

laptop/models/

The MVP does NOT require training a custom pose-estimation model.


### OpenCV

Use OpenCV for:

- Webcam access
- Camera frame capture
- Video/image frame handling
- Image conversion where required by MediaPipe
- Initial real-time debug visualization

Do not introduce another computer-vision framework unless a concrete technical limitation requires it.


# Gesture Recognition

Gesture recognition is custom Body Controller logic built on top of pose landmarks returned by MediaPipe.

Initial canonical gesture vocabulary:

- JUMP
- CROUCH
- LEAN_LEFT
- LEAN_RIGHT
- PRIMARY_GESTURE

Prefer interpretable pose-landmark geometry, calibration, thresholds, and temporal/state-based logic.

Do NOT train a custom gesture-recognition neural network for the MVP.


# Game Input

Keyboard output must be isolated inside:

laptop/src/input_controller.py

Select and validate an appropriate Python keyboard-input library against the actual demo operating system and demo games before treating the library as a permanent dependency.

Do not assume a keyboard-input library works with a particular game until it has been tested.

No pose-detection or gesture-recognition module may directly call a keyboard-input library.


# Testing

Use pytest for automated tests.

Prioritize tests covering deterministic application logic such as:

- Gesture classification
- Gesture state transitions
- Gesture cooldown behavior
- Debouncing
- Calibration calculations
- Profile loading
- Profile validation
- Gesture-to-control mappings

Tests for deterministic gesture logic should not require a live webcam.


# Linting and Formatting

Use Ruff for Python linting and formatting.

Do not introduce additional formatting or linting tools unless necessary.


# Data Formats

Use JSON for:

- Game profiles
- Shared gesture definitions

Do not introduce a database for the MVP.


# Repository Layout

The laptop implementation uses a deliberately simple source structure.

Application source code lives directly inside:

laptop/src/

Do NOT create another package-name directory such as:

laptop/src/body_controller/

unless explicitly requested.

The intended repository structure is:

body-controller/
│
├── README.md
├── AGENTS.md
├── LICENSE
├── .gitignore
├── .python-version
│
├── laptop/
│   ├── main.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   │
│   ├── models/
│   │
│   ├── src/
│   │   ├── app.py
│   │   ├── config.py
│   │   ├── camera.py
│   │   ├── pose_detector.py
│   │   ├── gesture.py
│   │   ├── gesture_engine.py
│   │   ├── gesture_state.py
│   │   ├── calibration.py
│   │   ├── profile.py
│   │   ├── profile_loader.py
│   │   ├── input_controller.py
│   │   └── debug_view.py
│   │
│   └── tests/
│       ├── test_gesture_engine.py
│       ├── test_gesture_state.py
│       ├── test_calibration.py
│       └── test_profile_loader.py
│
├── mobile/
│
├── shared/
│   └── gesture_schema.json
│
├── profiles/
│   ├── runner.json
│   └── platformer.json
│
└── docs/
    ├── architecture.md
    └── demo-plan.md

Do not reorganize this structure without a concrete technical reason.


# Module Responsibilities

## main.py

`laptop/main.py` is the application entry point.

Keep it small.

Its primary responsibility should be starting the laptop application.

Complex application logic should not accumulate in `main.py`.


## app.py

Coordinates the laptop application.

Expected conceptual flow:

camera
→ pose detector
→ gesture engine
→ gesture event
→ profile
→ input controller

Responsibilities may include:

- Starting application components
- Running the primary application loop
- Coordinating modules
- Managing application lifecycle
- Handling clean startup and shutdown

Do not place gesture-classification mathematics inside `app.py`.


## config.py

Centralizes application configuration.

Examples:

- Environment variables
- Reasonable application defaults
- Runtime feature flags

Avoid scattering configuration constants across unrelated modules.


## camera.py

Responsible for camera interaction.

Responsibilities include:

- Opening the selected camera
- Reading frames
- Applying configured camera resolution
- Detecting camera failures
- Releasing camera resources

The camera module must not recognize gestures or send game controls.


## pose_detector.py

Encapsulates MediaPipe Pose Landmarker.

Input:

camera frame

Output:

pose-landmark result

Responsibilities include:

- Loading the configured MediaPipe pose model
- Configuring MediaPipe
- Running pose inference
- Returning pose landmarks in a usable form

Keep MediaPipe-specific implementation details isolated here when practical.

The rest of Body Controller should not depend unnecessarily on MediaPipe-specific internals.


## gesture.py

Defines canonical gesture concepts.

Initial gesture vocabulary:

JUMP
CROUCH
LEAN_LEFT
LEAN_RIGHT
PRIMARY_GESTURE

Prefer one canonical identifier per physical action.

Avoid duplicate concepts such as:

JUMP
JUMPING
PLAYER_JUMP
JUMP_GESTURE

Use JUMP.


## gesture_engine.py

Interprets pose landmarks and determines what physical action occurred.

Input:

pose landmarks and relevant state/calibration data

Output:

canonical gesture event or no gesture

This is the primary gesture-classification layer.

Initial responsibilities include recognizing:

- Lean left
- Lean right
- Jump
- Crouch
- One additional upper-body gesture

Do not send keyboard commands from this module.


## gesture_state.py

Handles temporal gesture state.

This module exists because a player may remain in a gesture position across many camera frames.

For example:

Player crouches
→ CROUCH starts
→ Emit CROUCH once
→ Player remains crouched
→ Do not emit CROUCH every frame
→ Player returns to neutral

Appropriate concepts may include:

- State transitions
- Cooldowns
- Debouncing
- Gesture activation
- Gesture release
- Hysteresis

One physical action should not accidentally produce dozens of game inputs simply because it appears across many frames.


## calibration.py

Handles user-specific or camera-specific baseline measurements where necessary.

Possible calibration information includes:

- Neutral body center
- Neutral shoulder height
- Relative body scale
- Useful movement thresholds

Avoid assuming that every player:

- Has identical body dimensions
- Stands at the same distance from the camera
- Places the camera at the same height
- Begins at identical image coordinates

Prefer relative measurements where appropriate.


## profile.py

Represents a game-control profile.

A profile maps canonical gestures to game controls.

Example:

JUMP → space
CROUCH → s
LEAN_LEFT → a
LEAN_RIGHT → d

A profile contains game/control meaning.

Gesture recognition does not.


## profile_loader.py

Loads and validates external game-profile configuration.

Profiles live under:

profiles/

The profile loader should:

- Read profile files
- Validate required structure
- Reject invalid mappings clearly
- Produce usable profile objects

Changing profiles should not require changing pose or gesture code.


## input_controller.py

Handles actual operating-system input.

Input:

configured keyboard action

Output:

keyboard event sent to the operating system/game

This module is the boundary between Body Controller and OS-level game input.

Keep the selected keyboard-input dependency isolated in this module.

If the keyboard-input library must later change, pose detection and gesture recognition should remain unaffected.


## debug_view.py

Provides development and demonstration feedback.

Useful information may include:

- Camera feed
- Pose landmarks
- Current recognized gesture
- Active profile
- Current mapped output
- Calibration state
- FPS/performance information

The debug view should make it clear where failures occur.

For example:

Camera working?
Pose detected?
Gesture recognized?
Profile mapped?
Input sent?

Do not prioritize elaborate UI design before the core pipeline works.


# Core Architecture Rule

DO NOT write code conceptually equivalent to:

if jump_detected:
    press("space")

inside gesture-recognition code.

Preferred architecture:

gesture = Gesture.JUMP

followed by a separate mapping operation:

control = active_profile.get_mapping(gesture)

followed by:

input_controller.execute(control)

This separation is fundamental to the project.


# Gesture Recognition Philosophy

Reliability is more important than quantity.

Prefer:

4-5 reliable gestures

over:

15 unreliable gestures.

Use pose landmarks and deterministic logic when they adequately solve the problem.

Useful techniques may include:

- Relative landmark positions
- Calibration baselines
- Confidence thresholds
- Temporal comparisons
- State transitions
- Cooldowns
- Debouncing
- Hysteresis

Do not introduce custom neural-network training without a demonstrated need.


# Initial Gesture Priority

Implement gestures incrementally.

Priority order:

1. LEAN_LEFT
2. LEAN_RIGHT
3. JUMP
4. CROUCH
5. PRIMARY_GESTURE

Do not attempt to perfect every gesture simultaneously.

Get individual gestures working and test them before expanding the gesture set.


# Game Profiles

Game mappings MUST remain configurable.

A profile may conceptually resemble:

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

The same gesture may map differently in another profile.

For example:

Runner:
JUMP → up

Platformer:
JUMP → space

Gesture-recognition code must remain unchanged when switching these profiles.


# Initial Game Scope

Optimize the MVP for games that:

- Accept keyboard controls
- Require relatively few discrete actions
- Provide immediate visual feedback
- Do not rely heavily on precise mouse aiming

Good demo categories include:

- Endless runners
- Simple platformers
- Other simple keyboard-controlled games

The project does NOT claim universal game compatibility.


# Mobile Implementation

The `/mobile` directory is owned by another developer.

Do NOT modify `/mobile` unless explicitly instructed to work on the mobile implementation.

The mobile implementation may use different:

- Languages
- Frameworks
- Camera APIs
- Pose-estimation technologies
- UI architecture

Do not force the mobile implementation to mirror the laptop file structure.

The shared contract between implementations is conceptual gesture meaning.


# Laptop/Mobile Shared Contract

Where interoperability is needed, use canonical gesture events.

Initial vocabulary:

JUMP
CROUCH
LEAN_LEFT
LEAN_RIGHT
PRIMARY_GESTURE

`shared/gesture_schema.json` is the shared definition of this vocabulary.

Both implementations should use equivalent gesture meanings even if they detect those gestures differently.

Laptop functionality MUST NOT depend on mobile functionality.

The laptop MVP should operate completely independently:

Laptop camera
→ Pose detection
→ Gesture recognition
→ Gesture event
→ Profile mapping
→ Keyboard input
→ Game


# Models

`laptop/models/` stores pretrained model assets required by the laptop computer-vision pipeline.

For the initial implementation, this primarily means the MediaPipe-compatible Pose Landmarker model.

These are pretrained inference assets.

Do NOT interpret this directory as a location for custom Body Controller ML-model training.

Do not begin custom model training unless explicitly requested.


# Dependencies

Runtime dependencies belong in:

laptop/requirements.txt

Current starting dependencies:

mediapipe
opencv-python

Development-only dependencies belong in:

laptop/requirements-dev.txt

Current starting development dependencies:

pytest
ruff

Do not add dependencies speculatively.

Add a dependency when the implementation has a concrete need for it.


# Testing Strategy

Separate deterministic logic from hardware-dependent logic where practical.

For example, gesture tests should ideally be capable of operating on known landmark data without requiring:

- A webcam
- A person standing in front of the computer
- A running game

Prioritize tests for:

1. Gesture classification
2. Gesture state transitions
3. Cooldowns/debouncing
4. Calibration calculations
5. Profile parsing
6. Profile validation
7. Gesture-to-control mapping

Camera integration and game integration may require manual/integration testing.


# Engineering Guidelines

When modifying the project:

1. Preserve module boundaries.
2. Favor understandable implementations over unnecessary abstractions.
3. Do not create architecture for hypothetical future features.
4. Keep gesture recognition independent from game controls.
5. Keep laptop functionality independent from mobile functionality.
6. Add type hints where useful.
7. Add docstrings for non-obvious public classes and functions.
8. Release camera and other hardware resources cleanly.
9. Fail clearly when required resources are unavailable.
10. Avoid unnecessary global state.
11. Keep tunable configuration centralized.
12. Do not commit secrets or credentials.
13. Do not add cloud/network dependencies unless a feature explicitly requires them.
14. Do not restructure the repository without a concrete reason.
15. Prioritize reliable live behavior over theoretical flexibility.


# Performance Priorities

For the real-time control loop, prioritize:

1. Responsiveness
2. Stable pose tracking
3. Reliable gesture recognition
4. Low accidental-trigger rate
5. Clean gesture state handling
6. Maintainable implementation
7. Visual polish

Do not add expensive processing unless it produces a meaningful improvement.


# MVP Definition of Done

The laptop MVP is successful when:

1. The webcam opens reliably.
2. The player's body pose is detected in real time.
3. At least four physical movements are recognized reliably.
4. Recognized movements produce canonical gesture events.
5. Gesture events pass through a configurable game profile.
6. Configured keyboard controls are emitted.
7. A real keyboard-controlled game responds.
8. Profiles can be switched without modifying gesture-recognition code.
9. A second game can use different mappings for the same gesture system.
10. The laptop implementation operates without requiring the mobile implementation.


# Explicit Non-Goals

Until the MVP works, do NOT prioritize:

- Universal game compatibility
- Custom pose-model training
- Custom gesture-model training
- Precise mouse aiming
- FPS-game support
- Large gesture libraries
- Automatic game detection
- AI-generated game profiles
- Multiplayer body controls
- Cloud infrastructure
- Databases
- Authentication/accounts
- Analytics infrastructure
- Docker
- External generative-AI APIs
- Advanced desktop UI
- Mobile-dependent laptop functionality
- Python packaging/distribution infrastructure

These are stretch concepts, not MVP requirements.


# Development Priority

Work approximately in this order:

1. Camera capture
2. MediaPipe Pose Landmarker integration
3. Real-time pose/debug visualization
4. Canonical gesture definitions
5. Lean-left and lean-right recognition
6. Jump recognition
7. Crouch recognition
8. PRIMARY_GESTURE recognition
9. Gesture state/debounce/cooldown behavior
10. Keyboard-output implementation
11. Profile loading and mapping
12. First real game integration
13. Second real game integration
14. Calibration and reliability improvements
15. UI/demo polish
16. Stretch features

Do not skip ahead to later features while the core pipeline is unreliable.


# First Implementation Milestone

The first implementation milestone is NOT the complete application.

The first milestone is:

Webcam
→ OpenCV
→ MediaPipe Pose Landmarker
→ Detected body landmarks
→ Real-time debug visualization

This milestone should establish:

- Reliable camera capture
- Successful model loading
- Real-time pose inference
- Visible pose landmarks
- Clean startup
- Clean shutdown

Do NOT implement:

- Gesture recognition
- Keyboard controls
- Game profiles
- Mobile integration

as part of this first milestone unless explicitly instructed.


# Demo Objective

The final hackathon demo should prove that Body Controller is not tied to one particular game.

Suggested demonstration flow:

1. Start Body Controller.
2. Show the live pose system recognizing the player.
3. Load a runner-style profile.
4. Demonstrate lean left/right, jump, and crouch in the first game.
5. Return to Body Controller.
6. Switch profiles.
7. Launch a second keyboard-controlled game.
8. Perform some of the same physical movements.
9. Show that the active profile changes which keyboard controls those gestures produce.

The central message is:

"The vision system determines what the player physically did. The profile determines what that movement means to the current game."


# Final Guidance for Coding Agents

Before modifying code:

1. Read this entire file.
2. Read the root README.md.
3. Read docs/architecture.md if present.
4. Inspect existing code before creating new abstractions.
5. Preserve work already implemented unless there is a concrete reason to change it.

If working on the laptop implementation:

- Work inside `/laptop`, `/profiles`, `/shared`, or relevant documentation.
- Do not modify `/mobile`.
- Preserve the gesture/profile separation.
- Prioritize the current milestone over speculative features.

Do not attempt to build the entire roadmap in one change unless explicitly instructed.

Body Controller succeeds through a small, reliable, demonstrable pipeline, not through feature count.