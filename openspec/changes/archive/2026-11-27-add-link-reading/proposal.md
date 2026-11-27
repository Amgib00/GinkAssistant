## Why

The owner asked for Gink to see and read links by itself: "if I give it any links like this for any social media
platforms (https://www.facebook.com/reel/2322629778521786) for it to automatic see it and know", and to read pages
automatically -- with higher abilities, more tools and high-level security. Until now Gink read a pasted page's title
and text only: a Facebook reel came back as Facebook's sign-in page, so the AI could only guess what the reel was.

## What Changes

- Any link is opened by Gink's server before the answer: which site and what kind of thing it is (a reel, a video, a
  post, a song, a PDF, a picture, a page), the official preview where the site has one (oEmbed; Bluesky's public API;
  Meta's with a server token; YouTube's Data API with a key) and the page's own preview (Open Graph, JSON-LD): who
  posted it, when, its caption, length and counts; its picture is looked at, an audio or video file listened to, a
  PDF's pages read. A short follow-up still has the link. The chat says what it is opening.
- Honest limits: a platform's video is never downloaded; the AI is told only the preview could be seen, and that an
  attached video is watched whole; a sign-in page is said to be one.
- The shield: hidden page text and invisible characters removed, every link's words between markers no page can fake,
  instructions aimed at AI flagged and never followed; public addresses only, every redirect and picture checked;
  sizes by type; an allowance per person per 10 minutes.
- Agents (managed, scheduled, the apps'), Gink Genie and own-key apps open links too; `POST /v1/links/read`,
  `client.links.read()` / `read_link()`, `gink.links.read()` / `readLink()`, `gink read URL`.
- Lockdown mode: an automatic search no longer refuses the whole chat; links aren't opened.

## Out of scope

- Downloading or playing videos from social platforms, signing in to them, or pretending to be their crawlers.
- Comments, replies and private posts (only what a site shows anyone without an account).
- Watching a linked video file frame by frame on the server (it is listened to; attached videos are watched).

## Platforms

Server, macOS (Catalina too), Windows, Linux, Android (64- and 32-bit), iOS, the web app, Gink Genie, the API and
managed agents, scheduled tasks, the CLI and both SDKs (gink-ai 0.3.19), and the website.
