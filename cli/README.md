# Gink in your terminal

```bash
pip install gink-ai
gink login                                   # opens your browser to approve (or: gink login --key)
gink "What's the weather in Dakar?"
gink                                         # chat: /new, /model NAME, /models, /search on|off, /exit
cat notes.txt | gink "summarise this"
gink -s "latest news in Senegal"             # search the web (with sources)
gink --image "a baobab at sunset" -o tree.png
gink models
```

Your key can also come from `GINK_API_KEY`; another server from `GINK_BASE_URL`
(default `https://gink-server.onrender.com/v1`). `gink logout` forgets the saved key.

## In Python (the SDK)

```python
from gink import Client

client = Client()                                    # GINK_API_KEY, or the key `gink login` saved
it = client.interactions.create(input="Research solar growth in Senegal and write report.md", environment="remote")
print(it.output_text, it.files_changed, it.environment)

for event in client.interactions.create(input="Update report.md with this year's numbers",
                                        previous_interaction_id=it.id, stream=True):
    print(event.type, event.data)                    # live: step, status, done

print(client.chat("What's the weather in Dakar right now?"))    # live information included
env = client.environments.get(it.environment)
print(env.download("report.md").decode())
```

Managed agents and environments: https://gink-server.onrender.com/developers/agents
