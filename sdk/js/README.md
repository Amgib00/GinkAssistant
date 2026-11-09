# gink-ai (JavaScript / TypeScript)

The Gink API: managed agents with live steps, persistent workspaces, chat with live information, web search and
images. Node 18+, Deno, Bun (anything with `fetch`).

```js
import { Gink } from "gink-ai";

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
const png = await gink.image("my dog", { idea: "statue", photo: dogPhotoBytes });   // see gink.imageIdeas()
```

Scheduled agents: `await gink.schedules.create({ input: "Update report.md with today's news", every: "daily", at: "08:00" })`.

Keep your API key on your server: never in a web page anyone can open.
Guide: https://gink-server.onrender.com/developers/agents
