# A document stands full height

Today a document opens as a 720 × 738 card with 32 px above it and 153 px below.

## Behaviour

- A document's window runs the window's full height, half a pixel from the top and the bottom edges (one device pixel on a Retina screen), 720 px wide, its 24 px corners kept.
- The field stands over its foot on a white fade.
- Other open windows keep their 200 px at the sides, stepped back as today (`WindowStack.tsx`).

## Done when

A UI test measures the window: 0.5 px from the top and the bottom, 720 px wide, corners kept, neighbours at the sides. Before and after pictures.
