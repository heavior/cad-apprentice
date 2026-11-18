# Privacy

cad-apprentice runs on your computer. It collects nothing and sends nothing to the kit's author or to
anyone else. It has no account, no analytics and no tracking.

The one exception is the optional [design rules server](#the-design-rules-server). An agent talks to
it only if you connect it, for example through the ChatGPT plugin. Everything else in the kit works
without it.

## In short

- **Personal data collected:** none by the kit on your computer. If you connect the design rules
  server, it gets the rule names and search words your agent sends, plus your IP address and your
  agent's user agent.
- **What it's used for:** to answer your agent's request. The server's request logs are used only to
  keep it running and stop abuse.
- **Who receives it:** the design rules server and Google, which hosts it. Your agent and Autodesk
  Fusion send their own data, under their own policies (see below).
- **How long it's kept:** the server saves nothing itself. Google keeps its request logs for 30 days,
  and Firebase Hosting keeps IP addresses for a few months to detect abuse. The kit keeps no data of
  yours anywhere but your own computer. Files it writes there stay until you delete them.
- **Your controls:** don't connect the design rules server, and nothing is sent to it. Remove the
  plugin, the runner add-in, the kit's data folder and the design folders in Fusion's Scripts
  folder, and nothing of the kit is left. [Uninstall](README.md#uninstall) lists each one.

## What leaves your computer

Apart from the design rules server below, none of it is sent by the kit's own code. It comes from
the tools the kit works with:

- **Your AI agent** (Claude Code, Codex or another) sends what you type, the files it reads and the
  pictures of your design to its own model provider. That provider's privacy policy applies.
- **Autodesk Fusion** saves each version of your design to your Autodesk cloud, as it does for any
  design you save. Autodesk's privacy policy applies.
- **GitHub** serves the kit's files when you install or update the kit. Nothing of yours is sent.

## The design rules server

`https://cad-apprentice.web.app/mcp` is a small read-only MCP server with the kit's rules. It's listed
in [mcp.json](mcp.json). It has no account and no sign-in, sets no cookies and stores nothing.

- **What it gets:** the tool your agent calls and its words: a rule set name or search words. It
  sends back the matching rules. Your design, your files and your chat are never sent to it.
- **Request logs:** Google Cloud logs each request: time, address, status, your IP address and
  user agent. The search words aren't in those logs. They are kept 30 days by default
  ([Cloud Logging](https://docs.cloud.google.com/logging/quotas)). Only the kit's author can read
  them, to fix problems and stop abuse.
- **Hosting:** Google's Firebase runs the server for the kit's author. Firebase Hosting keeps IP
  addresses for a few months to detect abuse ([Firebase privacy](https://firebase.google.com/support/privacy)).

## What stays on your computer

The kit writes only on your computer: your design's scripts, pictures and STL files in your project
folder; `kit.txt`, run requests and logs in `~/Library/Application Support/cad-apprentice/`; a
folder for each design in Fusion's Scripts folder (its entry file, its last run's log, pictures and
STLs); and a copy of the runner add-in in Fusion's AddIns folder. If you installed the plugin, your agent keeps a copy of it in its own plugin folder.
[Prerequisites, permissions and data](README.md#prerequisites-permissions-and-data) lists every
place.

## Contributing back

The kit never sends your library changes anywhere, and your agent isn't told to. If your agent added
something useful to the library, please consider contributing it back:
[Contributing](README.md#contributing) has a prompt to give your agent.

## Questions

Open an issue in the kit's repository.
