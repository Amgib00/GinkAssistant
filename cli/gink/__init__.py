"""
The Gink Python SDK (pip install gink-ai), for the Gink Developer API.

    from gink import Client

    client = Client()                                   # GINK_API_KEY, or the key `gink login` saved
    interaction = client.interactions.create(
        agent="gink-agent",
        input="Plot solar energy growth in my country since 2015 and write slides in HTML",
        environment="remote",
    )
    print(interaction.output_text, interaction.files_changed)

    for event in client.interactions.create(input="...", stream=True):   # live: each step as it happens
        print(event.type, event.data)

    answer = client.chat("What's the weather where I am?")                  # chat, with live information
    env = client.environments.create(name="notes")
    env.upload("data.csv", open("data.csv", "rb").read())
    print(env.download("report.md").decode())
"""
from .client import Client, GinkAPIError, Interaction, Environment, Event

__all__ = ["Client", "GinkAPIError", "Interaction", "Environment", "Event"]
__version__ = "0.3.2"
