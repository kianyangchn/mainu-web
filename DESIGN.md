# Mainu Web Mobile Redesign Spec (V1)

## 1. Product Frame
- **Purpose**: Transform Mainu from a utilitarian uploader into a polished, mobile-first travel companion that guides planners through capture, translation, and sharing.
- **Core Loop**: Capture menu photos → Receive structured translation → Share with travel party → Coordinate selections together.
- **Experience Principles**: Wander-Ready (evokes light travel energy), Togetherness (supports shared decisions), Confident Clarity (trustworthy translation), Effortless Flow (gentle guidance with minimal text).

## 2. Audience Notes
- **Primary Persona**: Trip coordinator juggling logistics on a phone; needs friendly guidance, quick AI feedback, and reassurance the translation is accurate.
- **Secondary Persona**: Link recipients (friends/family) browsing dishes in transit; viewer mode must feel delightful, legible, and low effort.

## 3. Journey Overview (Mobile)
1. Landing (capture-focused welcome)
2. Upload workflow (select multiple photos, optional language pick)
3. Processing feedback state
4. Result planner hub (section navigation, share, collaborative cues)
5. Share link confirmation
6. Viewer opens read-only menu (consistent styling)
   - Error branches: unsupported file, empty upload, expired/invalid share.

## 4. Global Layout & Navigation
- **Viewport**: Base 375–430px, 16px side gutters, 8px spacing grid.
- **Structure**: Light top status strip with logo + descriptor; stacked content; sticky bottom bar for primary CTA on key screens.
- **Background Motif**: Soft gradients with abstract travel arcs/dashed paths reused across pages for continuity.
- **Brand Elements**: Rounded pills, soft shadows (blur 24px @ 12% opacity), duotone micro-illustrations (tickets, luggage, skyline).

## 5. Screen Blueprints
### A. Welcome / Capture (replace `home.html`)
- Compact brand hero with rotating taglines ("One menu, zero confusion").
- Upload module: large photo card with floating “+” icon; copy limited to “Add menu photos.” Secondary link “Tips for crisp shots” (modal or popover).
- Language chips: horizontal pill carousel with top destinations plus “Auto-detect” default.
- Optional “Recent menus” placeholder row for future history.
- Sticky bottom CTA: “Translate menu” gradient button with safe-area padding.

### B. Upload Review (post file select)
- Thumbnail carousel showing selected pages with edit/delete icons and “Add another” tile.
- Inline warning banner for rejected files (icon + single sentence).

### C. Processing State
- Full-bleed card featuring animated airplane trail spinner, single message “We’re unpacking the menu…” and dotted progress estimate.

### D. Result / Planner Hub
- Summary card: editable restaurant name, detected language chip, share pill showing TTL countdown (24h).
- Section navigation: sticky horizontal tabs; tapping scrolls to section list.
- Dish cards: gradient border, translated name prominent, original name chip, description truncating at 2 lines, price badge right-aligned. Reserve icon slots for spice/veg indicators.
- Collaboration row: buttons for “Save picks” (future), “Share link” primary, “Download PDF” secondary (future-ready). Share CTA mirrored in bottom sticky bar.
- Empty state: travel illustration with “No dishes found yet—try another photo.”

### E. Share Link View (`share.html`)
- Hero header matching gradient motif, copy “Shared by Alex” (fallback generic), TTL pill (“Expires in 23h”).
- Quick actions: copy link (icon button), language toggle (if alt data available), optional open-in-app stub.
- Section accordions: default open first section, show dish count badge.
- Dish cards mirrored from planner view but read-only; emphasize price and compact description.
- Footer: friendly sign-off ("Bon appétit! – mainu") within gradient bar.

### F. Error / Expired Share
- Illustration of folded map with closed route.
- Message “This menu link has ended its trip.” CTA “Start a new menu” or “Ask your host to resend.” Small detail text with error code for debugging.

## 6. Visual System
### Color Palette
- Primary: `#2F7BFF` (Sky Trail 500), `#1D5BDB` (Sky Trail 700).
- Accent: `#FF8360` (Sunset Coral) for highlights/interactive feedback.
- Background: `#F5F9FF`, cards `#FFFFFF`, supporting `#E0ECFF`.
- Neutrals: text `#0F1B39` (primary), `#5A6785` (secondary), `#94A3C1` (muted).
- Status: success `#2ECC71`, warning `#FFB347`, error `#FF6B6B`.

### Typography
- Headings: "Clash Display" (or fallback `Poppins`, weight 600).
- Body/UI: `Inter` 400/500 (already integrated).
- Scale: 32/28 hero, 22 section headings, 18 card titles, 16 body, 13 captions.

### Iconography & Illustration
- Feather-style outlined icons, 24px standard.
- Duotone travel illustrations (Primary + Sunset Coral) for hero, empty, error states.

### Components
- Buttons: Primary (gradient fill, 16px radius), Secondary (outline with `#CCE0FF` border), Ghost (text only). Minimum height 48px.
- Chips: pill, 12px horizontal padding, active uses solid Primary with white text.
- Cards: 20px radius, padding 20px, option for background blur in hero.
- Progress indicator: 48px circular with animated dotted trail.
- Accordions: 1px `#E0ECFF` border, summary row with chevron rotation.

### Spacing & Elevation
- Base spacing 8px increments; major vertical rhythm 24px.
- Shadows: Level 1 `0 8px 24px rgba(47,123,255,0.12)`, Level 2 `0 16px 40px rgba(15,27,57,0.14)`.

### Motion
- 200–250 ms ease-out for component transitions; 400 ms ease-in-out for modal/overlay.
- Provide reduced-motion fallbacks (respect `prefers-reduced-motion`).

## 7. Content Guidelines
- Keep copy concise; max two lines per instruction.
- Favor icons/illustrations over explanatory text.
- Microcopy only where necessary (TTL reminder, error hints).
- Friendly tone with subtle travel references; avoid technical jargon.

## 8. Accessibility & Responsiveness
- Contrast ≥ 4.5:1 on text over gradients.
- Tap targets ≥ 48px height, ensure sticky CTAs clear keyboard safe area (use `env(safe-area-inset-bottom)`).
- Focus states: 2px outline in Sunset Coral.
- Tablet/desktop: center column at 540px width, extend background motif without breaking mobile hierarchy.

## 9. Implementation Roadmap
1. Extract design tokens (colors, spacing, radii, shadows, motion) into CSS variables in `:root` for reuse across templates.
2. Refactor `home.html` and `share.html` to new structure (hero, cards, sticky CTA) with shared component classes (Button, Card, Chip, Accordion).
3. Introduce optional processing overlay: template can render `processing` state with spinner card while awaiting response.
4. Prepare SVG assets (hero, empty, error, icons) and place under a forthcoming static directory; ensure inline SVG support for recoloring.
5. Implement sticky bottom action bars with safe-area padding and graceful degradation on older browsers.
6. Validate cross-browser (Safari iOS, Chrome Android) plus reduced-motion/high-contrast scenarios.
7. Plan future enhancements (favorites, open-in-app) as hidden/disabled buttons to preserve layout.

## 10. QA Checklist
- Layout validated on iPhone 13 mini, iPhone 15 Pro Max, Pixel 7.
- File picker interaction keeps CTA visible and unobstructed.
- Section tabs remain accessible via swipe and tap; accordions functional for long lists.
- Share TTL pill updates correctly; expired share screen matches spec.
- Screen reader navigation: hero → main actions → lists respects semantic ordering.

## 11. Next Steps
1. Produce hi-fi mocks in Figma using this system for landing, processing, results, share, and error states.
2. Share tokens + component library with engineering before implementation sprint.
3. Schedule joint design QA once templates updated to ensure fidelity with spec.
