/* The one place Tabler enters the app: business components say <AppIcon name="tag" />,
   and the registry below keeps the bundle tree-shakeable. Decorative without a `label`: the svg is `aria-hidden` then.
   The svg carries every attribute it is given, `size="18"` included, and on a filled icon `stroke-width` as well. React's
   Tabler icon takes `size` and `stroke` for itself, so the svg is drawn here from the icon's own drawing (its kind's
   attributes, classes and paths) with those attributes on it, in a fixed order. */
import type { ReactElement, ReactNode, Ref as ReactRef } from 'react'
import '../lib/devIcons'
import {
  IconArrowLeft,
  IconArrowRight,
  IconArrowUpRight,
  IconCalendar,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconDotsVertical,
  IconFile,
  IconFolder,
  IconHierarchy,
  IconHistory,
  IconInbox,
  IconListDetails,
  IconMessageCircle,
  IconPlus,
  IconPointFilled,
  IconRotateClockwise,
  IconSearch,
  IconTag,
  IconTrash,
  IconWorld,
  IconX,
  IconCircleXFilled,
  type TablerIcon,
} from '@tabler/icons-react'
import { cx, fallthrough } from '../bind'
import './appIcon.css'

const REGISTRY = {
  'arrow-left': IconArrowLeft,
  'arrow-right': IconArrowRight,
  'arrow-up-right': IconArrowUpRight,
  calendar: IconCalendar,
  comment: IconMessageCircle,
  'chevron-down': IconChevronDown,
  'chevron-left': IconChevronLeft,
  'chevron-right': IconChevronRight,
  today: IconPointFilled,
  dots: IconDotsVertical,
  file: IconFile,
  folder: IconFolder,
  hierarchy: IconHierarchy,
  history: IconHistory,
  inbox: IconInbox,
  plus: IconPlus,
  repeat: IconRotateClockwise,
  search: IconSearch,
  subtask: IconListDetails,
  tag: IconTag,
  trash: IconTrash,
  world: IconWorld,
  x: IconX,
  'x-circle': IconCircleXFilled,
} as const

export type AppIconName = keyof typeof REGISTRY

const BASE_NAMES = new Set<AppIconName>([
  'calendar', 'comment', 'file', 'folder', 'hierarchy', 'history', 'inbox', 'plus', 'repeat', 'subtask', 'tag', 'trash',
])
const ARROW_NAMES = new Set<AppIconName>([
  'arrow-left', 'arrow-right', 'arrow-up-right', 'chevron-down', 'chevron-left', 'chevron-right', 'today',
])
function tuningClass(name: AppIconName): string | undefined {
  if (BASE_NAMES.has(name)) return 'app-icon--base'
  if (ARROW_NAMES.has(name)) return 'app-icon--arrows'
  if (name === 'search') return 'app-icon--search'
  if (name === 'dots') return 'app-icon--menu'
  return undefined
}

interface Drawing {
  attrs: Record<string, unknown>
  className: string
  paths: ReactNode
}
const drawings = new Map<TablerIcon, Drawing>()

/** The svg the icon's own component draws with no props, read once: `xmlns`, `viewBox` and its kind's fill and stroke,
 *  `tabler-icon tabler-icon-<name>`, and its paths. */
function drawingOf(icon: TablerIcon): Drawing {
  let drawing = drawings.get(icon)
  if (!drawing) {
    const svg = (icon as unknown as { render: (props: object, ref: null) => ReactElement<Record<string, unknown>> }).render({}, null)
    const { className, children, ...attrs } = svg.props
    delete attrs.ref
    drawing = { attrs, className: String(className).trim(), paths: children as ReactNode }
    drawings.set(icon, drawing)
  }
  return drawing
}

interface Props {
  name: AppIconName
  size?: number
  stroke?: number
  /** Accessible name. Omit for decorative icons: they render `aria-hidden`. */
  label?: string
  ref?: ReactRef<SVGSVGElement>
}

export function AppIcon({ name, size = 18, stroke = 2.2, label, ...attrs }: Props & Record<string, unknown>) {
  const drawing = drawingOf(REGISTRY[name])
  const own = {
    ...drawing.attrs,
    width: size,
    height: size,
    size,
    strokeWidth: stroke,
    className: cx(drawing.className, 'app-icon', tuningClass(name)),
    'aria-hidden': label ? undefined : 'true',
    'aria-label': label,
    role: label ? 'img' : undefined,
  }
  return <svg {...fallthrough(own, attrs)}>{drawing.paths}</svg>
}
