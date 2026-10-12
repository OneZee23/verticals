/* The children drawn into another element (`to`: a selector or an element). A teleported node is not
   inside the components around it in the DOM, so its events never reach them; React bubbles them along the component
   tree instead. Each top-level child stops them there for React handlers only, after its own handler: the browser's own
   bubbling to document and window goes on, as from a teleported node. */
import { Children, cloneElement, isValidElement, type ReactElement, type ReactNode, type SyntheticEvent } from 'react'
import { createPortal } from 'react-dom'

const BUBBLING = [
  'onAuxClick', 'onClick', 'onDoubleClick', 'onContextMenu', 'onMouseDown', 'onMouseUp', 'onMouseMove', 'onMouseOver',
  'onMouseOut', 'onPointerDown', 'onPointerUp', 'onPointerMove', 'onPointerCancel', 'onPointerOver', 'onPointerOut',
  'onKeyDown', 'onKeyUp', 'onKeyPress', 'onBeforeInput', 'onInput', 'onChange', 'onFocus', 'onBlur', 'onSubmit',
  'onWheel', 'onTouchStart', 'onTouchMove', 'onTouchEnd', 'onTouchCancel', 'onDragStart', 'onDrag', 'onDragEnd',
  'onDragEnter', 'onDragOver', 'onDragLeave', 'onDrop', 'onCopy', 'onCut', 'onPaste', 'onCompositionStart',
  'onCompositionUpdate', 'onCompositionEnd',
]

function staysHere(element: ReactElement): ReactElement {
  const props = element.props as Record<string, unknown>
  const handlers: Record<string, (event: SyntheticEvent) => void> = {}
  for (const name of BUBBLING) {
    const own = props[name] as ((event: SyntheticEvent) => void) | undefined
    handlers[name] = (event) => {
      own?.(event)
      event.isPropagationStopped = () => true
    }
  }
  return cloneElement(element, handlers)
}

export function Teleport({ to, disabled = false, children }: { to: string | Element; disabled?: boolean; children?: ReactNode }): ReactNode {
  if (disabled) return children
  const target = typeof to === 'string' ? document.querySelector(to) : to
  if (!target) return null
  return createPortal(Children.map(children, (child) => (isValidElement(child) && typeof child.type === 'string' ? staysHere(child) : child)), target)
}
