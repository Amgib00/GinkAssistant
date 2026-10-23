# Email delivery

## Purpose
Sign-up, sign-in and password-reset codes reach people's inboxes, on any hosting plan, and the owner can see why when they don't.

## Requirements

### Requirement: Sending email
The server SHALL send email through Brevo's HTTPS API when BREVO_API_KEY and a verified sender are set (Render's free plan blocks SMTP), otherwise through Gmail SMTP, and otherwise SHALL log the code together with the reason it wasn't emailed; a failure SHALL never break sign-in.

#### Scenario: Unverified sender
- **WHEN** Brevo refuses the sender
- **THEN** the reason, including "verify this sender address in Brevo", is logged with the code

### Requirement: Test email
The owner dashboard SHALL send a test email on request and show either success or the exact reason it failed.

#### Scenario: Checking delivery
- **WHEN** the owner sends a test email
- **THEN** the dashboard shows "Sent" or the provider's reason
