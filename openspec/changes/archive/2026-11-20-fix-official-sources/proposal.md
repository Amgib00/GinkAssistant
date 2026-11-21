## Why

The "Official" badge on sources was wrong both ways: universities counted as official while the UN, the
World Bank and the EU didn't, and the app showed the badge for any source whose line merely said
"official" -- including lists the AI wrote itself.

## What Changes

- Official = government domains (.gov, .gouv.xx, .gob.xx, .go.xx, .gc.ca, europa.eu...), international
  public bodies (.int and a list: un.org, worldbank.org, imf.org, unicef.org...), or the website of the
  organisation the question names (wave.com for a question about Wave). Not universities or news.
- The app shows the badge only for Gink's own marker (" \u00b7 official" at the end of a source line).

## Impact

- Modified spec: web-search. Server ranking/marking and the app's Sources list.
