# UI UX Pro Max - Design Intelligence

Comprehensive design guide for web and mobile applications. Contains 50+ styles, 161 color palettes, 57 font pairings, 161 product types with reasoning rules, 99 UX guidelines, and 25 chart types across 10 technology stacks.

## When to Apply

Use this skill for tasks involving **UI structure, visual design decisions, interaction patterns, or user experience quality control**.

### Must Use
- Designing new pages (Landing Page, Dashboard, Admin, SaaS, Mobile App)
- Creating or refactoring UI components (buttons, modals, forms, tables, charts)
- Choosing color schemes, typography systems, spacing standards, or layout systems
- Reviewing UI code for UX, accessibility, or visual consistency
- Implementing navigation structures, animations, or responsive behavior
- Making product-level design decisions (style, information hierarchy, brand expression)
- Improving perceived quality, clarity, or usability of interfaces

### Skip
- Pure backend logic development
- API or database design only
- Performance optimization unrelated to the interface
- Infrastructure or DevOps work
- Non-visual scripts or automation tasks

**Decision criteria**: If the task changes how a feature **looks, feels, moves, or is interacted with**, use this skill.

## Rule Categories by Priority (1–10)

| Priority | Category | Impact | Key Requirement |
|----------|----------|--------|-----------------|
| 1 | Accessibility | CRITICAL | Contrast 4.5:1, Alt text, Keyboard nav, Aria-labels |
| 2 | Touch & Interaction | CRITICAL | Min size 44×44px, 8px+ spacing, Loading feedback |
| 3 | Performance | HIGH | WebP/AVIF, Lazy loading, CLS < 0.1 |
| 4 | Style Selection | HIGH | Match product type, Consistency, SVG icons |
| 5 | Layout & Responsive | HIGH | Mobile-first breakpoints, No horizontal scroll |
| 6 | Typography & Color | MEDIUM | Base 16px, Line-height 1.5, Semantic color tokens |
| 7 | Animation | MEDIUM | Duration 150–300ms, Motion conveys meaning |
| 8 | Forms & Feedback | MEDIUM | Visible labels, Error near field, Helper text |
| 9 | Navigation Patterns | HIGH | Predictable back, Bottom nav ≤5, Deep linking |
| 10 | Charts & Data | LOW | Legends, Tooltips, Accessible colors |

## Quick Reference Summary

**Accessibility**: Focus rings, color contrast, keyboard navigation, descriptive labels, skip links, heading hierarchy, reduced motion support, screen reader compatibility.

**Touch & Interaction**: Minimum 44×44pt targets, 8px gaps, tap feedback within 100ms, loading states, error clarity, gesture affordances.

**Performance**: Image optimization (WebP/AVIF), lazy loading, space reservation (prevent layout shift), font loading strategy, code splitting, virtualized lists for 50+ items.

**Style Selection**: Match style to product type, maintain consistency, use SVG icons instead of emojis, align shadows/blur with chosen style, support dark mode.

**Layout & Responsive**: Mobile-first approach, systematic breakpoints (375/768/1024/1440), 16px minimum body text, readable line length (35–75 characters), no horizontal scroll, safe-area awareness.

**Typography & Color**: 1.5–1.75 line height, 65–75 character line length, consistent font scale, 4.5:1 contrast ratio, semantic color tokens, support system text scaling.

**Animation**: 150–300ms duration, use transform/opacity only, easing conveys direction, respect reduced-motion preference, maintain spatial continuity, stagger list entries 30–50ms.

**Forms & Feedback**: Visible labels (not placeholder-only), errors below fields, submit feedback (loading → success/error), progressive disclosure, inline validation on blur, error recovery guidance.

**Navigation Patterns**: Bottom nav max 5 items with labels, predictable back behavior, deep linking support, clear active state indicators, preserve scroll/state on navigation, avoid mixed nav patterns.

**Charts & Data**: Match chart type to data, accessible color palettes with patterns/texture fallbacks, legends visible, tooltips on interact, responsive charts, empty state messaging, screen reader summary.

## How to Use

### Step 1: Analyze Requirements
Extract product type (Entertainment, Tool, Productivity, hybrid), target audience, style keywords (playful, minimal, dark mode, etc.), and tech stack.

### Step 2: Generate Design System (REQUIRED)
```bash
python3 skills/ui-ux-pro-max/scripts/search.py "<product_type> <industry> <keywords>" --design-system [-p "Project Name"]
```
Returns comprehensive recommendations: pattern, style, colors, typography, effects, and anti-patterns.

### Step 2b: Persist Design System (Optional)
```bash
python3 skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system --persist -p "Project Name"
```
Creates hierarchical system: global `MASTER.md` + page-specific override files in `design-system/pages/`.

### Step 3: Supplement with Detailed Searches
```bash
python3 skills/ui-ux-pro-max/scripts/search.py "<keyword>" --domain <domain> [-n <max_results>]
```

**Domains**: `product`, `style`, `color`, `typography`, `chart`, `ux`, `google-fonts`, `landing`, `react`, `web`, `prompt`.

### Step 4: Stack Guidelines
```bash
python3 skills/ui-ux-pro-max/scripts/search.py "<keyword>" --stack react-native
```

## Common Professional UI Issues

### Icons & Visual Elements
- Use vector-based icons (SVG, Lucide, react-native-vector-icons); never use emojis for structural UI
- Maintain consistent icon sizing, stroke width, and style per hierarchy level
- Meet contrast standards: 4.5:1 for small elements, 3:1 minimum for larger glyphs
- Ensure touch targets ≥44×44pt with expanded hit area if icon is smaller

### Interaction
- Provide pressed feedback (ripple/opacity/elevation) within 80–150ms
- Keep micro-interactions 150–300ms with platform-native easing
- Ensure screen reader focus matches visual order with descriptive labels
- Avoid layout-shifting pressed states; use stable transforms only

### Light/Dark Mode
- Primary text ≥4.5:1 contrast in both themes
- Secondary text ≥3:1 contrast on dark surfaces
- Test both themes independently (not inferred)
- Modal scrim 40–60% black for foreground legibility

### Layout & Spacing
- Respect safe areas for headers, tab bars, fixed UI
- Use 4/8dp spacing rhythm consistently
- Keep long-form text readable on large devices (avoid edge-to-edge paragraphs on tablets)
- Increase horizontal insets on larger widths and landscape orientation
- Ensure scroll content is not hidden behind fixed/sticky bars

### Accessibility
- All meaningful images/icons have accessibility labels
- Form fields include labels, hints, and clear error messages
- Color is never the sole indicator of information
- Reduced motion and dynamic text size work without layout breakage
- Accessibility traits/roles/states correctly announced

## Pre-Delivery Checklist

**Visual Quality**: No emojis as icons, consistent icon family, correct brand assets, stable pressed states, semantic theme tokens used.

**Interaction**: Clear pressed feedback, touch targets ≥44×44pt, 150–300ms timing with native easing, clear disabled states, descriptive labels, no gesture conflicts.

**Light/Dark Mode**: 4.5:1 primary text contrast both themes, 3:1 secondary contrast, distinguishable dividers/states, strong modal scrim, both themes tested.

**Layout**: Safe areas respected, scroll content not hidden behind fixed bars, tested on small/large phone and tablet (portrait/landscape), correct spacing rhythm, readable text measure.

**Accessibility**: Meaningful labels/alt text, form completeness, no color-only indicators, reduced motion/dynamic type support, correct announcements.

---

**Output formats** support ASCII or Markdown via `-f markdown` flag.
