# Architecture

## Core Pipeline

Camera
→ Pose Detection
→ Gesture Recognition
→ Gesture Event
→ Control Mapping
→ Input Output
→ Game

## Separation of Responsibilities

### Observation

Camera and pose-detection code determines where the player's body is.

### Interpretation

Gesture-recognition code determines what physical action occurred.

### Mapping

Game profiles determine what control corresponds to the recognized action.

### Output

Input code communicates the mapped control to the operating system.

## Critical Boundary

Gesture recognition must never depend on the controls of a specific game.

For example:

`JUMP`

is valid gesture-engine output.

`SPACE`

is not.

`SPACE` only becomes relevant after `JUMP` passes through an active profile.

## Platform Boundary

`/laptop` and `/mobile` are independent implementations.

Neither implementation should require the other to operate.

Shared concepts belong in `/shared`.