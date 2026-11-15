# Gink in your terminal

```bash
pip install gink-ai
gink login                                   # opens your browser to approve -- a passkey works (or: gink login --key)
gink "What's the weather where I am?"
gink                                         # chat: /new, /model NAME, /models, /search on|off, /exit
cat notes.txt | gink "summarise this"
gink -s "latest news in my country"             # search the web (with sources)
gink --image "a baobab at sunset" -o tree.png
gink see label.jpg "what does this say?"     # about a photo (Gink Pro)
gink models
```

Your key can also come from `GINK_API_KEY`; another server from `GINK_BASE_URL`
(default `https://gink-server.onrender.com/v1`). `gink logout` forgets the saved key.

## Images

```bash
gink --image "a lighthouse at dawn" --style watercolor --aspect 16:9
gink ideas                                            # ready-made looks
gink --image "my dog" --idea statue --photo dog.jpg   # start from your own photo
gink --image "an x-ray of my camera"                  # X-ray, exploded view, cutaway: picked from your words
```

## Photos

```bash
gink see broken-tap.jpg                    # Gink works out what it needs: reads text, finds what's wrong, solves sums
gink see menu.jpg "translate this"
```

Like the Live camera in the apps: careful with anything about health (general terms only, never a diagnosis or a
dose, and "get help now" when it could be urgent). In a workspace in healthcare mode, nothing that identifies a
patient is read out.

## Workspaces

```bash
gink workspace                  # your workspace (a hospital, school or business) and your role
gink workspace safety --days 30 # admins, healthcare mode: patient details removed or stopped, photos checked
```

The safety report is counts only, never what anyone wrote. In Python: `client.workspace.safety(days=30)`.

## Agents fix their work

When an agent changes files, Gink checks the whole environment before it finishes (links to files that don't
exist, JSON or Python that doesn't parse) and fixes what it finds. `gink env check ID` checks one yourself.

## Scheduled agents

```bash
gink schedule add "Update report.md with today's news" --every daily --at 08:00
gink schedule list        # run ID | pause ID | resume ID | rm ID
gink schedule add "Weekly report" --every weekly --at 09:00 --webhook https://example.com/gink-hook
gink webhook secret       # what the notifications are signed with
```

In your server (Python): `event = gink.verify_webhook(request_body_bytes, request.headers["Gink-Signature"], secret)`.

## In Python (the SDK)

```python
from gink import Client

client = Client()                                    # GINK_API_KEY, or the key `gink login` saved
it = client.interactions.create(input="Research solar growth in my country and write report.md", environment="remote")
print(it.output_text, it.files_changed, it.environment)

for event in client.interactions.create(input="Update report.md with this year's numbers",
                                        previous_interaction_id=it.id, stream=True):
    print(event.type, event.data)                    # live: step, status, done

print(client.chat("What's the weather where I am right now?"))    # live information included
found = client.search("When is the next election in my country?", with_sources=True)
for s in found["sources"]:                                           # official sources first, each with its real logo
    print("official" if s["official"] else "        ", s["title"], s["url"], s["icon"])
png = client.image("my dog", idea="figurine", photo="dog.jpg")         # Media Studio's looks
print(client.see("receipt.jpg", "add these up"))                       # about a photo (Gink Pro)
env = client.environments.get(it.environment)
print(env.download("report.md").decode())
```

Managed agents and environments: https://gink-server.onrender.com/developers/agents
