# Columns bounce at their ends again, and Reduce Motion lives in the View menu

## Behaviour

- A column scrolled past its top or bottom on a trackpad bounces back, the way macOS scrolls everything else. The CSS that turned this off for fine pointers (`overscroll-behavior: none` on `.period-slide`) goes.
- The desktop app's View menu gets **Reduce Motion**, a checkmark item between Reload and Enter Full Screen. It starts on when macOS's own Reduce motion is on; after the person changes it, their choice is kept.
- With it on, columns don't bounce and the board's movements stop, exactly as the web app already does under the system setting (`prefers-reduced-motion`): one switch that everything obeys, hover included.
- In a plain browser the system setting stays the only switch.

## Done when

A test shows the bounce is back (no `overscroll-behavior: none` on a column) and that the app's flag turns motion off the same way the system setting does. The menu item is built and persisted in the Swift app. Before and after pictures of the View menu.
