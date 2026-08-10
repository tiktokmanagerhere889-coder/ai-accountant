---
id: 014
title: Custom thin themed scrollbars for dark/light themes
stage: general
date: 2026-08-11
surface: agent
model: best
feature: none
branch: main
user: Hassan
command: "Scrollbar ko custom-style karo taake dark/light theme ke sath match kare aur patli (thin) dikhe — abhi default browser-scrollbar white/bright hai jo dark theme ke sath mismatch karti hai. globals.css mein add karo: [the Webkit + Firefox CSS block]. Dono dark aur light theme mein test karo (color-tokens automatically theme ke hisaab se badalne chahiye kyunke CSS-variables use ho rahi hain). Screenshot dikhao dono themes ka confirm karne ke liye."
labels: ["scrollbar", "css", "theming", "globals.css", "dark-mode", "webkit"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - frontend/src/app/globals.css (Webkit + Firefox scrollbar rules inside @layer base, tokens auto-switch light/dark)
tests:
 - "Playwright screenshots of dark + light themes (1000x600 forced scroll) -> both show thin 8px themed thumb"
 - "getComputedStyle -> dark --border resolves to oklch(1 0 0 / 10%), light to oklch(0.922 0 0)"
 - "No console errors during both theme renders"
---

## Prompt

Scrollbar ko custom-style karo taake dark/light theme ke sath match kare aur
patli (thin) dikhe — abhi default browser-scrollbar white/bright hai jo dark
theme ke sath mismatch karti hai. globals.css mein add karo: [the Webkit +
Firefox CSS block]. Dono dark aur light theme mein test karo (color-tokens
automatically theme ke hisaab se badalne chahiye kyunke CSS-variables use ho
rahi hain). Screenshot dikhao dono themes ka confirm karne ke liye.

## Response snapshot

Default browser scrollbar was bright/white and clashed with dark theme.
Added custom rules to globals.css inside @layer base (after the html rule):

  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 8px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--muted-foreground); }
  * { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }

Used var(--border) (a muted line token present in BOTH themes: light
oklch(0.922 0 0), dark oklch(1 0 0 / 10%)) + var(--muted-foreground) on
hover. NOTE: user suggested var(--text-secondary), but that token does NOT
exist in globals.css — --muted-foreground is the correct secondary-text
token. Because both vars are CSS custom properties, the thumb auto-rethemes
with the .dark class — no theme-specific CSS needed.

Verified with Playwright (1000x600 viewport -> forced scroll on the dashboard
main.flex-1.overflow-y-auto container, scrolled to 260px, screenshotted dark
then toggled to light): DARK thumb = translucent white on dark surface;
LIGHT thumb = soft gray on white. getComputedStyle confirmed --border
resolves to the dark token (oklch(1 0 0 / 10%)) under .dark. 0 console
errors. Screenshots: scrollbar-dark.png, scrollbar-light.png under
C:/Users/Hassan/AppData/Local/Temp/shot-tool/shots/.

## Outcome

- ✅ Impact: thin (8px) themed scrollbars everywhere (dashboard container,
  dialogs, tables, code blocks) — no more bright default bar in dark theme.
- 🧪 Tests: Playwright dark + light screenshots show correct per-theme thumb;
  getComputedStyle confirms token swap; 0 console errors.
- 📁 Files: frontend/src/app/globals.css (commit 67d8d9d).
- 🔁 Next prompts: none required.
- 🧠 Reflection: User named --text-secondary, but the actual token set has
  --muted-foreground (secondary text) and --border (muted line). Verify
  token existence in globals.css before using a suggested var name — CSS
  custom properties do not fail loudly when undefined, so a wrong var()
  silently falls back to the inherited/browser default. Prefer a token that
  exists in BOTH :root and .dark so the same rule themes itself.

## Evaluation notes (flywheel)

- Failure modes observed: the initial "track" background of the default
  scrollbar remains transparent-white in dark if only ::-webkit-scrollbar is
  styled; must also set track transparent (done). User-suggested token
  --text-secondary does not exist — validated against globals.css before use.
- Graders run and results (PASS/FAIL): dark-theme screenshot PASS; light-
  theme screenshot PASS; getComputedStyle token resolution PASS; console
  errors PASS (0).
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): null
