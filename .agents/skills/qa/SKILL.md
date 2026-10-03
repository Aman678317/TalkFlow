---
name: qa
description: "End-to-end quality assurance and browser testing. Exercises full user journeys, edge cases, responsive viewports, and visual feedback using real browser sessions and automation."
---

# QA & Browser Testing Mode

Perform thorough user-journey and automated functional testing across the web application.

## QA Matrix
1. **Core Workflows**: Happy path execution from authentication through primary actions to completion.
2. **Edge Cases & Bad Input**: Invalid inputs, huge payloads, special Unicode/emoji characters, network disconnections, rapid double-clicks.
3. **Session & Auth Scenarios**: Multi-tab login/refresh, expired token recovery, permission denial, logout redirection.
4. **Interactive States & Responsiveness**: Test at mobile (375px), tablet (768px), and desktop (1280px+). Check viewport scaling and touch areas.
5. **Realtime & Media Controls**: Mute/unmute, audio stream resumption, websocket reconnections, peer connection lifecycle.
6. **Execution Method**: Use Antigravity `browser_subagent` for interactive browser validation and recording, complemented by Playwright / Vitest / Pytest suites.
