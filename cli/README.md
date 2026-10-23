# Gink in your terminal

```bash
pip install gink-ai
gink login                                   # paste your API key (Gink > Settings > Developers)
gink "What's the weather in Dakar?"
gink                                         # chat: /new, /model NAME, /models, /search on|off, /exit
cat notes.txt | gink "summarise this"
gink -s "latest news in Senegal"             # search the web (with sources)
gink --image "a baobab at sunset" -o tree.png
gink models
```

Your key can also come from `GINK_API_KEY`; another server from `GINK_BASE_URL`
(default `https://gink-server.onrender.com/v1`). `gink logout` forgets the saved key.
