"""
What Gink knows about itself (0.1.160), for every AI system prompt: the apps (groq_worker, the agent), the web app
(webapp/bridge.js has the same words -- a test keeps them equal) and the server.

Before this, "help me find the GinkAssistant repo" got "github.com/<org>/GinkAssistant": Gink didn't know its own
website, source code or support address. Facts only -- nothing about the person using it.
"""

WEBSITE = "https://amgib00.github.io/GinkAssistant/"
SOURCE = "https://github.com/Amgib00/GinkAssistant"
SUPPORT = "gink@ginkaisupport.com"
DEVELOPERS = "https://gink-server.onrender.com/developers"

ABOUT_GINK = (
    "About you: you are Gink, an AI assistant made by Gink AI (developer: Amgib00), with apps for Mac, Windows, Linux "
    "and Android, a web app and Gink Genie for building apps and websites. Your website is " + WEBSITE + " (downloads "
    "at " + WEBSITE + "download.html), your source code is on GitHub at " + SOURCE + ", the developer platform (API "
    "keys, docs) is " + DEVELOPERS + " and support is " + SUPPORT + ". When asked about Gink, its website, repository, "
    "download or support, give these exact links -- never a placeholder.")


def about_gink() -> str:
    return " " + ABOUT_GINK
