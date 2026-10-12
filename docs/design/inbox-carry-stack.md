# In the Inbox a carried card waits in the field, as on the board

On the board a goal let go over the field waits in the field as a small card: that is Move. In the Inbox the same gesture puts a big tile beside the field instead, a second way to do one thing.

## Behaviour

- A task carried onto the field in the Inbox waits in the field exactly as a goal does on the board: drawn by `MovingStack.vue`, the field saying "Find a goal", with Backspace, Tab, typing and dragging the card out all working.
- The big tile beside the field goes. `lib/inboxCarry.ts` keeps only the drag, which already hands the task to the board's Move (`lib/moving.ts`).

## Done when

UI tests: in the Inbox the carried task waits in the field through MovingStack and each key above works as on the board. Before and after pictures.
