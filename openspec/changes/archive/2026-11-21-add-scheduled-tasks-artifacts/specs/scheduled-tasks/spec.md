## ADDED Requirements

### Requirement: Tasks that run by themselves
A signed-in person SHALL be able to give Gink a task to do once or on a repeat (hourly, daily, weekdays, weekly on a chosen day, monthly on a chosen date) at a local time in their time zone. Gink's server SHALL run it at that time even when the person's apps are closed, searching the web and reading pages as the task needs, and SHALL put the result as Gink's message in the task's own chat, synced to all the person's devices, and by email when they asked for that.

#### Scenario: Morning news
- **WHEN** someone in Europe/Paris schedules "give me the three biggest stories" every day at 08:00
- **THEN** at 08:00 Paris time the server searches, writes the stories into the task's chat, and the next run is the next day at 08:00, also across daylight-saving changes

#### Scenario: A one-time reminder
- **WHEN** a task set for once on a date has run
- **THEN** it is not run again and shows as done

### Requirement: Scheduling from a chat
When someone asks in a chat for something later or on a repeat, the answer SHALL say what will happen and offer the task as a card; a new answer SHALL create the task at once, and a chat opened again SHALL show the task as it is now without creating it again.

#### Scenario: The same card twice
- **WHEN** the same schedule card is created a second time
- **THEN** the server returns the task it already made instead of a new one

### Requirement: Managing tasks
Settings > Scheduled tasks SHALL list every task with when it runs next and how its last run went, and SHALL let the person add, pause, resume, run now, open the task's chat and delete; deleting a task SHALL keep its chat and results.

#### Scenario: Run now
- **WHEN** someone presses Run now
- **THEN** the task runs at once, its next scheduled time stays the same, and pressing it again within a minute is refused

### Requirement: Limits and rules
Each run SHALL count as one message of the day; the Free plan SHALL allow 3 tasks and Gink Pro 25, with hourly tasks only on Pro; children under 13 SHALL NOT have tasks; a teen's parental quiet time SHALL postpone a run; workspace rules SHALL apply at creation and at every run; a run the AI service couldn't do SHALL be tried once more ten minutes later.

#### Scenario: A fourth task on Free
- **WHEN** someone on the Free plan with 3 tasks adds another
- **THEN** it is refused with a message that names the limit and Gink Pro
