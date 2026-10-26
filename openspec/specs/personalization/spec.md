# Personalization

## Purpose
People choose how Gink writes to them (style, warmth, enthusiasm, emoji, structure) without changing what Gink can do.

## Requirements

### Requirement: Style and tone
Settings > Personalization SHALL offer a base style (default, professional, friendly, concise, candid, playful) and Less / Default / More for warmth, enthusiasm, emoji and headers and lists; each non-default choice SHALL add one instruction to every chat and agent request (apps and web), and the defaults SHALL add nothing.

#### Scenario: Concise without emoji
- **WHEN** the person chooses Concise and less emoji
- **THEN** Gink's instructions include being brief and not using emoji

#### Scenario: New settings show their real value
- **WHEN** a person who never changed these settings opens the panel
- **THEN** every choice shows Default

### Requirement: Prompt library
Typing "/" at the start of a message SHALL open a menu of built-in prompts and the person's own (theirs first), filtered by what follows the "/", chosen with the arrow keys and Enter or Tab (which never sends the message) or a click, and closed with Escape; Settings > Personalization > Prompt library SHALL let them add (up to 50, 2000 characters each, no duplicates) and delete their own prompts.

#### Scenario: Picking a prompt
- **WHEN** the person types "/tra" and presses Enter
- **THEN** the message box contains "Translate this into French:" ready to complete, and nothing is sent

### Requirement: Prompts on every device
When signed in, the person's prompts SHALL be kept with their account: each device SHALL take the account's list when Gink starts, upload its own prompts the first time the account has none, and send every addition or deletion right away; signed out, prompts stay on the device; deleting the account deletes them.

#### Scenario: Deleting on another device
- **WHEN** a prompt is deleted on one device
- **THEN** it is gone from the "/" menu on the other devices the next time Gink starts there
