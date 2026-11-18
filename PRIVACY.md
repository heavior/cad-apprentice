# Privacy

cad-apprentice runs on your computer. It collects nothing and sends nothing to the kit's author or to
anyone else. It has no server, no account, no analytics and no tracking.

## In short

- **Personal data collected:** none. The kit's author gets nothing from you.
- **What it's used for:** nothing is collected, so nothing is used.
- **Who receives it:** no one, from the kit. Your agent and Autodesk Fusion send their own data,
  under their own policies (see below).
- **How long it's kept:** the kit keeps no data of yours anywhere but your own computer. Files it
  writes there stay until you delete them.
- **Your controls:** remove the plugin, the runner add-in, the kit's data folder and the design
  folders in Fusion's Scripts folder, and nothing of the kit is left.
  [Uninstall](README.md#uninstall) lists each one.

## What leaves your computer

None of it is sent by the kit's own code. It comes from the tools the kit works with:

- **Your AI agent** (Claude Code, Codex or another) sends what you type, the files it reads and the
  pictures of your design to its own model provider. That provider's privacy policy applies.
- **Autodesk Fusion** saves each version of your design to your Autodesk cloud, as it does for any
  design you save. Autodesk's privacy policy applies.
- **GitHub** serves the kit's files when you install or update the kit. Nothing of yours is sent.

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
