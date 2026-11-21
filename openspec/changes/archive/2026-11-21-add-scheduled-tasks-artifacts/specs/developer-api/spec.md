## ADDED Requirements

### Requirement: Scheduled tasks in the API
The API SHALL offer `/v1/tasks` to create, list, read (with the latest results), change, pause, resume, run (optionally waiting for the result) and delete scheduled tasks for the key's account, with the same limits as the apps; both SDKs (`tasks`) and the CLI (`gink tasks`) SHALL use it.

#### Scenario: Run and wait
- **WHEN** a developer runs a task with wait true
- **THEN** the answer has the task, its status and the result's text

### Requirement: Chat options that work like Gink's apps
Chat requests SHALL accept `gink_tasks` (a schedule block for later or repeated requests), `gink_artifacts` (finished things in titled blocks), `gink_code` (GitHub repositories read) and `gink_web: "auto"` (linked pages read and the web searched when needed); the SDKs SHALL read schedule blocks (`schedules_in` / `schedulesIn`) and artifacts (`artifacts()` with kind, file name and version).

#### Scenario: Saving artifacts
- **WHEN** `gink --save-artifacts site "make a landing page"` runs
- **THEN** the page is saved in the site folder under a file name from its title
