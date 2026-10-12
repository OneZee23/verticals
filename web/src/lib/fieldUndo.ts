// The field's own ⌘Z (docs/design/board-undo.md). Inside text the key is the text's own, and in the field the browser's undo
// takes one letter at a time: the board follows every letter, and a change made to the page while a letter is still being
// typed ends the browser's undo step for the typing. So the field keeps its own steps. A step is a run of typing: it ends when
// the typing changes kind (letters, then deleting), when it pauses for a second, and when the words are changed by something
// else (sent, cleared). ⌘Z puts back the words as they were before the last run and ⇧⌘Z plays it again.
//
// Pure state: the field hands it the words and a way to set them. It is for the field alone; every other place one types in
// keeps the browser's undo, which works there.

const PAUSE_MS = 1000

export interface FieldWords {
  get(): string
  set(text: string): void
}

type Kind = 'insert' | 'delete' | 'other' | ''

export function fieldUndo(words: FieldWords) {
  let undone: string[] = []
  let redone: string[] = []
  let kind: Kind = ''
  let lastAt = 0
  /** The words as typing and ⌘Z last left them: a change to anything else is not theirs. */
  let settled = words.get()

  const kindOf = (inputType: string): Kind => (inputType.startsWith('delete') ? 'delete' : /^insert(Composition)?Text$/.test(inputType) ? 'insert' : 'other')

  return {
    /** The person types: `before` is the words as they stood, `inputType` what the browser says is being done to them. */
    typing(before: string, inputType: string): void {
      const next = kindOf(inputType)
      const now = Date.now()
      if (next !== kind || next === 'other' || now - lastAt > PAUSE_MS) {
        undone.push(before)
        redone = []
      }
      kind = next
      lastAt = now
    },
    /** The words after typing, so a change made by something else can be told from it. */
    typed(after: string): void {
      settled = after
    },
    /** ⌘Z and ⇧⌘Z in the field. `false`: there was nothing to put back. */
    step(direction: 'undo' | 'redo'): boolean {
      const [from, to] = direction === 'undo' ? [undone, redone] : [redone, undone]
      const text = from.pop()
      if (text === undefined) return false
      to.push(words.get())
      kind = ''
      settled = text
      words.set(text)
      return true
    },
    /** A `beforeinput` event, from a menu: the browser's undo is taken for the field's own. A browser that does not let it be
     *  cancelled keeps it. (The keys never get this far: the browser has no redo to offer once its undo was not used, so the
     *  field reads the keys itself.) */
    history(event: InputEvent): void {
      if (!event.cancelable || (event.inputType !== 'historyUndo' && event.inputType !== 'historyRedo')) return
      event.preventDefault()
      this.step(event.inputType === 'historyUndo' ? 'undo' : 'redo')
    },
    /** The words changed some other way (sent, cleared, a letter that came from the board): the steps are about other words. */
    changed(now: string): void {
      if (now === settled) return
      undone = []
      redone = []
      kind = ''
      settled = now
    },
  }
}
