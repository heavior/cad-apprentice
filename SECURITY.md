# Security

## Report a problem

If you find a security problem in cad-apprentice, open an
[issue](https://github.com/heavior/cad-apprentice/issues) that says you found one, without the
details. We'll set up a private way for you to send them. Please don't post the details in public
until it is fixed.

## What to know

- **The kit runs only on your computer.** It has no server and no account
  ([PRIVACY.md](PRIVACY.md)).
- **The runner add-in runs code.** It runs inside Fusion and runs every Python file named in a
  request in `~/Library/Application Support/cad-apprentice/run/requests/`. Anything that can write to that folder, or to
  the kit folder, can run code in Fusion with your Autodesk account. Keep both yours, and don't add
  requests you didn't write or read first.
- **Your design's build script is code too.** Read a script from someone else before you run it.
- **Only the latest version gets fixes.** Update the kit the way you installed it.
