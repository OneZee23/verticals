## Reports from the app

A report is a document under reports/bugs/ that the app made when the person dropped pictures on the window and said what
happened. It holds their words, their pictures (inside the text), the app's version and the last lines of the app's and the
agent's logs. The app made a task with it, and the report is that task's first document.

- Never read a report with doc_get: its pictures are inside the text and would fill your context. The message that names a
  report names its task too. The task is where you work: read it with the goal tool.
- "Improve it" asks for a design. Write one document, in plain words: what went wrong, what the person expected, the cause
  if you could find it, the change you propose, and how it will be tested. {skills} Save it as design/<short-name>.md,
  link it to the report's task with doc_link, and answer in two short lines that you are waiting for their comments. If the
  task already has a design document, change that one; do not write a second.
- The person comments on the design and presses Check again; answer as you do for any document.
- Only once they agree, in a comment or in the chat, make the change. Work in the checkout named below, on a new branch.
  Write the tests first and see them fail, then make the change and see them pass, and run the repository's own checks
  (its README says how). Push the branch, open a pull request with gh, and put the pull request's address in the task's
  notes with update, so it joins the task's links.
- If there is no checkout, no git or gh, or this conversation does not let you run commands, say so in two short lines and
  stop. The task and its documents stay as they are; only the pull request waits.
