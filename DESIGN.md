# Design System: InsightKit

## Brand Identity & Personality
InsightKit is an on-premise text-to-SQL analytics engine built for data teams, infrastructure engineers, and business analysts.
Visual voice: technical precision, high readability, density with hierarchy, and zero decorative noise.

## Core Dials
- App UI (`web/index.html`): ENERGY 1 (Calm, focused workspace) / RHYTHM 2 (Structured split pane with responsive stack) / MOTION 1 (Fast state transitions, zero loops)
- Landing & Review (`docs/index.html`): ENERGY 2 (Balanced technical editorial) / RHYTHM 2 (Asymmetric technical sections, code tabs, interactive demo) / MOTION 1 (Smooth scroll and clean tab state transitions)

## Color Palette (WCAG AA Compliant)

### Light Mode
- Surface background: `#f8fafc`
- Card background: `#ffffff`
- Elevation border: `#e2e8f0`
- Subtle hover fill: `#f1f5f9`
- Text primary: `#0f172a` (Contrast ratio > 13:1 on white)
- Text secondary: `#475569` (Contrast ratio > 4.6:1 on white)
- Primary accent: `#0369a1` (Deep tech cyan, contrast ratio 4.8:1 on white)
- Success: `#15803d` (4.8:1)
- Warning: `#b45309` (4.6:1)
- Error: `#b91c1c` (5.2:1)

### Dark Mode
- Surface background: `#090d16`
- Card background: `#0f172a`
- Elevation border: `#1e293b`
- Subtle hover fill: `#1e293b`
- Text primary: `#f8fafc` (Contrast ratio > 15:1 on dark)
- Text secondary: `#94a3b8` (Contrast ratio > 6.2:1 on dark)
- Primary accent: `#38bdf8` (Contrast ratio > 9.1:1 on dark)
- Success: `#34d399`
- Warning: `#fbbf24`
- Error: `#f87171`

## Typography
- Interface: `ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- Code / SQL / Metrik: `ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace`

## Component Standards
- Border radius: 6px for buttons and inputs, 10px for cards and dialogs.
- Focus indicator: 2px solid offset outline (`#38bdf8` / `#0284c7`), visible on keyboard focus.
- Touch target: minimum 44px by 44px on mobile viewport.
- No decorative emojis in headings, labels, or buttons.
- No em dashes in UI text or documentation (use comma, colon, period, or parentheses).
