# oh-my-edits

An agent harness for Meta's [Edits](https://edits.instagram.com) app, packaged as a plugin for Claude Code and Codex.

Edits has two halves. The Mac app exposes a local MCP server, so an agent can already edit projects there. The iPhone app holds things the Mac app does not: the inspiration feed and its settings, saved reels, and templates. oh-my-edits connects both halves and turns the work you normally do by thumb into skills.

> Not affiliated with, endorsed by, or sponsored by Meta or Instagram. "Edits" and "Instagram" are trademarks of their owners.

## Skills

| Skill | What it does | Status |
|---|---|---|
| `edits-setup` | Interviews you, connects your agent to the Edits Mac app's MCP server, and prepares [ipb](https://github.com/ipbtools/ipb) to drive the iPhone app | Ready |
| `edits-inspiration` | Interviews you about what to see more and less of, then fills the **Your inspiration** topic lists on the phone and verifies each one | Ready |
| `edits-mac-editing` | Builds and changes videos in the Edits Mac app through its MCP server: text, shapes, masks, keyframes, audio levels, and export checks, with the tool behavior observed in Edits 457.0.0 | Ready |
| Reference search in Edits | Find reference reels in the Inspiration feed | Planned ([issues](https://github.com/NomaDamas/oh-my-edits/issues)) |
| Saved reels sorting | Sort and label reels saved in the Ideas tab | Planned |

## Requirements

- macOS with the Edits Mac app, for the MCP surface
- An iPhone on iOS 27 or later with the Edits app and [ipb](https://github.com/ipbtools/ipb), for the phone surface
- Claude Code or Codex

## Install

Claude Code:

```
/plugin marketplace add NomaDamas/oh-my-edits
/plugin install oh-my-edits@oh-my-edits
```

Codex:

```
codex plugin marketplace add NomaDamas/oh-my-edits
codex plugin add oh-my-edits@oh-my-edits
```

Then ask your agent: **"Set up oh-my-edits."**

## Safety

The Edits iPhone app is signed in to your Instagram account. oh-my-edits changes only what you approve in the session (for example, inspiration topics) and reads a few screens at a time. It never likes, follows, comments, sends messages, or publishes for you, and it does not scroll the feed in bulk. Automated use of Instagram products may conflict with Instagram's Terms of Use. You are responsible for how you use it.

## License

[Apache-2.0](LICENSE)
