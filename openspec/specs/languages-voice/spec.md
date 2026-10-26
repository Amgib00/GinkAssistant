# Languages and voice

## Purpose
Gink answers and listens in the person's language, on every platform.

## Requirements

### Requirement: Reply language
With the reply language "Same as my message" (the default), Gink SHALL be told to answer in the language the person writes in; with a chosen language, it SHALL always answer in that language.

#### Scenario: Writing in French
- **WHEN** a person writes in French with the default setting
- **THEN** the AI is instructed to reply in French

### Requirement: Automatic speech language
With the speech language "Automatic (any language)" (the default), the apps SHALL transcribe speech with Whisper on the Gink server (which detects the language), and SHALL fall back to Google recognition in the device's language when the server can't be used.

#### Scenario: The server is unreachable
- **WHEN** the transcription request fails
- **THEN** recognition falls back to Google with the device's language

### Requirement: Voice on Android
On Android, Gink SHALL ask for the microphone permission when first needed, listen with the phone's speech recognizer, speak with the natural Gink voices from the server and fall back to the phone's own voice, and declare the speech services Android 11+ requires.

#### Scenario: Microphone refused
- **WHEN** the person refuses the microphone permission
- **THEN** Gink says it needs the microphone and where to allow it

### Requirement: "Hey Gink"
On desktops Gink SHALL listen offline for "Hey Gink" (Vosk), and on Android while Gink is open (the phone's recognizer); a question said together with the wake phrase SHALL be answered without asking again.

#### Scenario: Said in one go
- **WHEN** a person says "Hey Gink, what's the weather in Dakar?"
- **THEN** Gink answers that question directly

### Requirement: Hey Gink keeps listening
Every app SHALL declare the microphone permission in the form its build tool reads (Briefcase: "permission", singular), and on Android the wake listener SHALL keep listening through busy, network and server hiccups (waiting longer each time, up to 30 seconds), switch to online recognition when the phone has no offline language, and stop only when the microphone permission is off or the phone has no speech service, saying why.

#### Scenario: A busy recognizer
- **WHEN** the phone's recognizer reports "busy" several times in a row
- **THEN** Hey Gink keeps listening and still wakes on "Hey Gink"
