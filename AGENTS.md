# Process management

- Do not start, stop, restart, or replace a bot, server, worker, watcher, or other background
  process unless the user explicitly requests that process action in their current message.
- Code or configuration changes alone do not authorize a process restart.
- Read-only process inspection is allowed when relevant.
