# Gink in your terminal

```bash
pip install gink-ai
gink login                                   # opens your browser to approve (or: gink login --key)
gink "What's the weather where I am?"
gink                                         # chat: /new, /model NAME, /models, /search on|off, /exit
cat notes.txt | gink "summarise this"
gink -s "latest news in my country"             # search the web (with sources)
gink --image "a baobab at sunset" -o tree.png
gink models
```

Your key can also come from `GINK_API_KEY`; another server from `GINK_BASE_URL`
(default `https://gink-server.onrender.com/v1`). `gink logout` forgets the saved key.

## Images

```bash
gink --image "a lighthouse at dawn" --style watercolor --aspect 16:9
gink ideas                                            # ready-made looks
gink --image "my dog" --idea statue --photo dog.jpg   # start from your own photo
```

## Scheduled agents

```bash
gink schedule add "Update report.md with today's news" --every daily --at 08:00
gink schedule list        # run ID | pause ID | resume ID | rm ID
```

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
png = client.image("my dog", idea="figurine", photo="dog.jpg")         # Media Studio's looks
env = client.environments.get(it.environment)
print(env.download("report.md").decode())
```

Managed agents and environments: https://gink-server.onrender.com/developers/agents
