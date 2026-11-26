# Agent safety

**Terminal-Bench's sandbox does the heavy lifting.** Every task runs in a fresh Docker container with no host access, destroyed afterward. Inside `harbor run`, your agent can't hurt you. Don't undo that:

- Don't mount your home directory, SSH keys, or `~/.gitconfig` into containers.
- Don't bake real credentials into images or `.env` files you commit. Use throwaway keys.
- `.env` is gitignored in the starter — keep it that way.

**The danger zone is your own dev loop.** When you test agent code *outside* Harbor (e.g., pointing your loop at a local shell "just to see"), it has whatever access you have:

- Develop in a scratch directory, never your home directory or a repo you care about.
- Remember the classics: `git clean -fdx`, `docker system prune`, `find ... -exec rm`, `>` truncation. An agent will eventually try one.

**API keys deserve their own paragraph, because your agent can read files.** Anything an agent `cat`s — including `.env` — enters the model conversation and the endpoint's logs. During `harbor run` you're fine: task containers don't inherit your host environment. The exposure is dev-loop testing with local shell access. In order of effort:

- Use a throwaway key created for this event, never a personal or work key. If an agent may have read it, treat it as burned and rotate it.
- Keep `.env` out of any directory you point a dev agent at — the agent needs the key *in its process environment* to call the endpoint, not on disk where it explores.
- If you already use a secrets manager, inject at runtime instead of keeping a plaintext file: e.g. `op run --env-file .env.tpl -- ./scripts/run_baseline.sh` (1Password CLI). 

**If your agent does something unexpected and concerning, tell us.** Novel failure modes are findings, not embarrassments — they're also great writeup material.


