## ADDED Requirements

### Requirement: Pay-by-use storage for big files
The server SHALL keep large Genie file contents in a content-addressed blob store -- object storage when GINK_S3_* is set, else the server's disk -- store each content once however many versions and copies use it, and delete blobs nothing uses any more.

#### Scenario: A version of a big file
- **WHEN** Genie saves a version of a project with a 30 KB file
- **THEN** the version stores a short reference, not the 30 KB again

### Requirement: Error reports
The apps, the web app and the server SHALL report errors (kind, message, where in Gink's code, platform, version) without chats or files, with emails and keys removed, grouped per bug on the owner dashboard; people SHALL be able to turn it off.

#### Scenario: The same bug on two platforms
- **WHEN** the same error happens on Android and macOS
- **THEN** the dashboard shows one row with a count of 2 and both platforms

### Requirement: The owner's social accounts
The owner dashboard SHALL show Gink's own Facebook Page, Instagram and TikTok (followers and latest posts) read-only, from tokens set on the server, with no connect buttons.

#### Scenario: Nothing set up
- **WHEN** no social tokens are set
- **THEN** the tile says how to set them up and makes no requests
