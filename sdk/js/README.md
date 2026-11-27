# gink-ai (JavaScript / TypeScript)

The Gink API: managed agents with live steps, persistent workspaces, chat with live information, web search and
images. Node 18+, Deno, Bun (anything with `fetch`).

```js
import { Gink, videoFrames } from "gink-ai";

const gink = new Gink();                    // GINK_API_KEY (create one at https://gink-server.onrender.com/developers)
const it = await gink.interactions.create({
  input: "Plot solar energy growth in my country since 2015 and write slides in HTML",
  environment: "remote",
});
console.log(it.output_text, it.files_changed);

for await (const event of gink.interactions.stream({ input: "Add this year's numbers", previous_interaction_id: it.id })) {
  console.log(event.type, event.data);      // step, status, done
}

const env = await gink.environments.get(it.environment);
console.log(await env.text("slides.html"));
console.log(await gink.chat("What's the weather where I am right now?"));
const { answer, sources } = await gink.search("When is the next election in my country?", { withSources: true });
for (const s of sources) console.log(s.official ? "official" : "        ", s.title, s.url, s.icon);   // official first, real logos
const png = await gink.image("my dog", { idea: "statue", photo: dogPhotoBytes });   // see gink.imageIdeas()
console.log(await gink.see(photoBytes, { question: "what's wrong with this?" }));  // about a photo (Gink Pro)
const { frames, duration } = await videoFrames(fileInput.files[0]);                // in a browser: a video's frames
console.log(await gink.watch(frames, { duration, question: "what happens here?" })); // about a video (Gink Pro)
const reel = await gink.readLink("https://www.facebook.com/reel/2322629778521786");  // a link, opened by Gink
console.log(reel.kind, reel.author, reel.text, reel.seen);                           // "reel", who, caption, its picture
const made = await gink.chat("Chart my sales by month", { gink_artifacts: true, gink_fit: true });
for (const a of gink.artifacts(made)) console.log(a.kind, a.filename);   // page, react, chart, table, slides, ...
```

Workspaces: `await gink.workspace.get()`; admins of one in healthcare mode: `await gink.workspace.safety({ days: 30 })`
(counts only: patient details removed or stopped, photos checked -- never words).

`see()` works like the Live camera: Gink works out what the photo needs and is careful with anything about health.
Agents check their whole environment before they finish and fix what they find (`env.check()` to check one yourself).

Scheduled agents: `await gink.schedules.create({ input: "Update report.md with today's news", every: "daily", at: "08:00" })`.

Webhooks: pass `webhook_url` to interactions or schedules; in your server,
`const event = await verifyWebhook(rawBody, req.headers["gink-signature"], secret)` (`import { verifyWebhook } from "gink-ai"`).

Keep your API key on your server: never in a web page anyone can open.
Guide: https://gink-server.onrender.com/developers/agents
