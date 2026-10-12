# Run FinPulse on your computer

You need **Node.js 22** and **Git**. Nothing else — no Python, no database, no API key.

## 1. Install the tools (once)

| | Windows | macOS | Linux |
|---|---|---|---|
| Node.js 22 | Download the **LTS** installer from [nodejs.org](https://nodejs.org) and run it | Same, or `brew install node@22` | Same, or use [nvm](https://github.com/nvm-sh/nvm): `nvm install 22` |
| Git | [git-scm.com](https://git-scm.com/download/win) | `xcode-select --install` | `sudo apt install git` |

Open a **new** terminal afterwards and check: `node -v` should print `v22.…`.

## 2. Get the code (once)

```bash
git clone https://github.com/AnshumanSingh16/FinPulse.git
cd FinPulse
```

## 3. Start it

```bash
npm start
```

The first run installs dependencies (a minute or two). Then open **http://localhost:3000**.
Windows users can instead double-click **`start-finpulse.cmd`** in the folder.

Press **Ctrl+C** in the terminal to stop it. Next time, just run `npm start` again.

## 4. Try the demo

On the home page click **Try the demo profile**, type *"I want to buy a ₹75 lakh house"* and
click **Check**. The full walkthrough is in [docs/PERSONAL.md](docs/PERSONAL.md#five-minute-demo).

## Optional: turn on the AI features

Everything works without AI. To add live rate research, AI explanations and the AI copilot,
open the `.env` file in the project folder (created on first start) and set:

```
ANTHROPIC_API_KEY=your-key-here
```

Restart `npm start`. Never commit this file — it is already git-ignored.

## Troubleshooting

| Problem | Fix |
|---|---|
| `'npm' is not recognized` / `command not found: npm` | Node.js isn't installed, or the terminal was open during install. Install it and open a new terminal. |
| "FinPulse needs Node.js 22" | Install the current LTS from nodejs.org (or `nvm install 22 && nvm use 22`). |
| Port 3000 is already in use | Next.js picks the next free port automatically — use the address it prints (e.g. http://localhost:3001). |
| `npm install` fails | Check your internet connection. On a college/company network you may need its proxy: `npm config set proxy http://proxy:port`. |
| Your data disappeared | Data is kept in the server's memory for the demo; stopping the server clears it. Click **Try the demo profile** again. |

## For developers

```bash
npm test          # unit tests (financial maths, agents, documents)
npm run lint      # ESLint
npm run typecheck # TypeScript
npm run build     # production build
```
