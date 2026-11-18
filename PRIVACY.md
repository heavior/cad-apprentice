# Privacy

cad-apprentice runs on your computer. It collects nothing and sends nothing to the kit's author or to
anyone else. It has no server, no account, no analytics and no tracking.

## What leaves your computer

None of it is sent by the kit's own code. It comes from the tools the kit works with:

- **Your AI agent** (Claude Code, Codex or another) sends what you type, the files it reads and the
  pictures of your design to its own model provider. That provider's privacy policy applies.
- **Autodesk Fusion** saves each version of your design to your Autodesk cloud, as it does for any
  design you save. Autodesk's privacy policy applies.
- **git** downloads the kit from its repository the first time and pulls updates once per session.
  It sends nothing of yours.

## What stays on your computer

The kit writes only on your computer: your design's scripts, pictures and STL files in your project
folder, run requests and logs in the kit folder, and a small entry file in Fusion's Scripts folder.
[Prerequisites, permissions and data](README.md#prerequisites-permissions-and-data) lists every
place.

## Contributing back

The kit never sends your library changes anywhere, and your agent isn't told to. If your agent added
something useful to the library, please consider contributing it back:
[Contributing](README.md#contributing) has a prompt to give your agent.

## Questions

Open an issue in the kit's repository.
