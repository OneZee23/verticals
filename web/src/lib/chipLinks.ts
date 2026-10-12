// What an agent's message brings (docs/design/agent-chips.md; Inbox and Documents redesign, rounds 9–11): the chat links a
// goal it made or changed as [title](#goal/<id>) and a document as [title](#doc/<id>) (desktop/chat/prompt-intro.md).
// Under the message's words each link is a chip, one form for every kind of thing (DocChip.vue, GoalChip.vue), in the
// field's answer as in the agent's balloon; nothing else marks them.

export interface ChipLink { kind: 'goal' | 'doc'; id: string; label: string }

const link = () => /\[([^\]]*)\]\(#(goal|doc)\/([A-Za-z0-9_-]+)\)/g

/** The goals and documents a message links, in the order it links them, each once. */
export function chipLinks(text: string): ChipLink[] {
  const seen = new Set<string>()
  const out: ChipLink[] = []
  for (const match of String(text).matchAll(link())) {
    const kind = match[2] as ChipLink['kind']
    const id = match[3]!
    if (seen.has(`${kind}:${id}`)) continue
    seen.add(`${kind}:${id}`)
    out.push({ kind, id, label: match[1]!.trim() })
  }
  return out
}

/** The message's words without the lines that only link goals and documents, bulleted or numbered: the chips say those. A
 *  link inside a sentence stays. */
export function withoutChipLines(text: string): string {
  return String(text)
    .split('\n')
    .filter((line) => !(link().test(line) && !line.replace(link(), '').replace(/^\s*\d+[.)]\s/, '').replace(/[\s\-*•·,:;.()[\]]+/g, '')))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
