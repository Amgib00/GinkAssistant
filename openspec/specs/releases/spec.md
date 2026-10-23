# Releases

## Purpose
Every release builds all installers and publishes them together.

## Requirements

### Requirement: Release checks
Before building, the Release workflow SHALL check that the version looks like vX.Y.Z, matches pyproject.toml, and hasn't been released, and SHALL stop with a clear message otherwise.

#### Scenario: Version already released
- **WHEN** someone runs Release with an existing version
- **THEN** the check job fails within seconds, before any build

### Requirement: Installers
A release SHALL publish Gink-mac-arm64.dmg, Gink-mac-x86_64.dmg, Gink-windows-x64.msi, Gink-linux-amd64.deb, Gink-android.apk and Gink-android-32bit.apk.

#### Scenario: Download page
- **WHEN** the release is published
- **THEN** every button on the website's Download page downloads its file
