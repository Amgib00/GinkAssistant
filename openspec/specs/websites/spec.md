# Websites

## Purpose
"Make me a website for..." -- Gink builds a page and gives a shareable link.

## Requirements

### Requirement: Build and change websites
The system SHALL build a one-file website from a description (POST /sites), change it on request (POST /sites/{id}/edit), list and delete the person's websites, and count each build or change toward the daily allowance; each account SHALL have at most 20 websites.

#### Scenario: Building a site
- **WHEN** a person asks "make me a website for my bakery in Thiès"
- **THEN** they get a link /s/<id> to a page about their bakery

#### Scenario: Only the owner
- **WHEN** another account tries to change or delete the website
- **THEN** it is not found, and the website is unchanged

### Requirement: Published pages are sandboxed
Pages SHALL be served with a Content-Security-Policy sandbox without allow-same-origin, default-src 'none' and form-action 'none', SHALL have password fields, outside scripts and outside stylesheets removed, and SHALL show a "Made with Gink" badge.

#### Scenario: A page tries to steal a sign-in
- **WHEN** a hosted page's script tries to read Gink's localStorage or cookies, or send data to another server
- **THEN** reading fails with a security error, its origin is null, and the request is blocked

### Requirement: Takedown
The owner SHALL be able to remove any website with DELETE /admin/sites/{id} and the admin key.

#### Scenario: Abuse report
- **WHEN** the owner removes a website
- **THEN** its link answers 404

### Requirement: Follow-up changes
Right after Gink builds or updates a website in a chat, an instruction about it ("add more to it", "make it blue") SHALL change that same website, while questions and thanks SHALL get a normal answer; Gink SHALL never claim it can't edit the user's website.

#### Scenario: "Good, add more to it"
- **WHEN** the person writes "good add more to it" just after their website was built
- **THEN** the same website is updated and the reply links to it
