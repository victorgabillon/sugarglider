# Mobile Map and contextual editing

The mobile Map workspace overlays the supplied AI action and Tools toolbar on
its map. Branding remains in Plan, Routes, About, the launcher and desktop. The
same toolbar DOM returns to its original location when leaving mobile Map;
Android window insets remain owned by the existing native layout.

On mobile touch devices (at most 840 CSS pixels with a coarse pointer and touch
support), MapLibre gestures remain enabled and the permanent NavigationControl
is absent. Pointer/desktop navigation is retained. Tools → Map display owns the
existing settings, legend and offline-map disclosures, plus accessible zoom,
reset-north and Fit points actions. These actions do not recreate settings or
change route intent. Mobile attribution uses MapLibre's compact control in
landscape too, retaining the five-second acknowledgement and full credits.

The route bar normally shows the existing visit order/topology and Generate.
Opening it or activating a route marker reveals the existing editing controls.
Done/Escape closes editing without clearing selection or changing a route.
Explicit map acquisition folds secondary controls while keeping its instruction
and Cancel available, then returns to an editor the user had opened. Required
endpoint-adjustment warnings are outside the dismissible editor. Immutable/AI
snapshot views do not expose manual editing controls.

Disclosure state is presentation-only. Required point objects, automatic intent,
Undo/Redo, search acquisition, generation, scoring, routing, AI prompts and GPX
serialization retain their existing owners. A multi-touch gesture cannot enter
the ordinary point-add callback. Dock/credit clearance uses observed dimensions;
selected painted pins use screen rectangles to avoid the actual controls. This
never changes geographic coordinates or generated geometry.

Browser acceptance covers touch gestures, marker/keyboard selection, editor
closure, move/delete/reorder and history, topology/order, local named-place
search, candidate inspection and exact selected GPX export. It includes 320,
372, 412, landscape and desktop widths, French/English and 200% text. The full
bundled-app driver uses real regional worker code with explicitly synthetic
native routing, terrain and model replies; it is not physical-device evidence.

Screenshots, measurements, APK audits and delivery receipts live outside Git in
`/home/pompote/sugarglider-ai-mobile-2026-10-26/map-minimalism`. The retained
Fairphone screenshot from build 8265c59 is the visual baseline. Installing a new
staging APK and validating real Fairphone gestures/offline generation require
separate installation authorization and fresh full-state preservation checks.
No cleanup, production or regional-data operation belongs to this UI change.
