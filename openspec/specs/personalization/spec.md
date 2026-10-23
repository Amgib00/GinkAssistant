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
