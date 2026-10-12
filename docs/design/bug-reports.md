# A report from pictures, its task, and the PR with the change

Something is wrong, or could be better: the person drops pictures on the field and says what they see and what they want. The report comes first, then, if asked, a design and a PR, all inside one task.

## Behaviour

- **Pictures stack above the field,** as a moved task does (`MovingStack.vue`), and the field widens to them. Past a few they overlap, so many still fit, and the one under the pointer lifts out, bigger. There is no fixed cap.
- **The report comes first:** a document with the pictures, what the person did and expected, the app's version, and the last lines of the app's and the agent's logs. Its task is made with it, and the report is the task's first document. The answer shows both as chips (`agent-chips.md`).
- Above the field: **Send to developers** and **Improve it**.
- **Send to developers** opens a prefilled GitHub issue in the browser with exactly what goes, and the person submits it; without GitHub, an email draft does the same. Nothing from the board goes but the report itself.
- **Improve it:** the agent writes a design document in the same task with the shaping skills, and says it's waiting. The person comments and presses Check again (`doc-comments-inline.md`).
- **Once agreed,** the agent makes the change in the task's session, with its tests, and opens a PR that joins the task's links. Without git, the task and its documents still come; only the PR waits.

## Done when

UI tests: pictures stack and lift under the pointer; the report and its task come at once; Send to developers builds the issue link with the report only; Improve it adds the design document to the same task. Before and after pictures.
