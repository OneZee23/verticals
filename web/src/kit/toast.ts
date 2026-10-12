/* The kit's toast: a service that builds its own stack on document.body, so it needs no framework. */
export interface ToastOptions {
  action?: string
  onAction?: () => void
  duration?: number
}

function toastStackEl(): HTMLElement {
  const existing = document.querySelector<HTMLElement>('.toast-stack[data-toast-stack]')
  if (existing) return existing
  const stack = document.createElement('div')
  stack.className = 'toast-stack'
  stack.setAttribute('data-toast-stack', '')
  stack.setAttribute('aria-live', 'polite')
  stack.setAttribute('aria-atomic', 'false')
  document.body.appendChild(stack)
  return stack
}

function dismissToast(toastEl: HTMLDivElement): void {
  if (toastEl.getAttribute('data-state') === 'closed') return
  toastEl.setAttribute('data-state', 'closed')
  let removed = false
  function remove(): void {
    if (removed) return
    removed = true
    toastEl.parentNode?.removeChild(toastEl)
  }
  toastEl.addEventListener('transitionend', remove, { once: true })
  setTimeout(remove, 400)
}

export function toast(text: string, opts: ToastOptions = {}): HTMLDivElement | undefined {
  if (typeof document === 'undefined') return undefined
  const stack = toastStackEl()
  const toastEl = document.createElement('div')
  toastEl.className = 'toast'
  toastEl.setAttribute('role', 'status')
  toastEl.setAttribute('data-state', 'closed')
  const span = document.createElement('span')
  span.className = 'toast__text'
  span.textContent = text == null ? '' : String(text)
  toastEl.appendChild(span)
  if (opts.action) {
    const action = document.createElement('button')
    action.className = 'toast__action'
    action.type = 'button'
    action.textContent = String(opts.action)
    action.addEventListener('click', () => {
      if (typeof opts.onAction === 'function') opts.onAction()
      dismissToast(toastEl)
    })
    toastEl.appendChild(action)
  }
  const close = document.createElement('button')
  close.className = 'toast__close'
  close.type = 'button'
  close.setAttribute('aria-label', 'Dismiss')
  close.textContent = '×'
  close.addEventListener('click', () => dismissToast(toastEl))
  toastEl.appendChild(close)
  stack.appendChild(toastEl)
  void toastEl.offsetWidth
  toastEl.setAttribute('data-state', 'open')
  const duration = typeof opts.duration === 'number' ? opts.duration : 4e3
  if (duration > 0) setTimeout(() => dismissToast(toastEl), duration)
  return toastEl
}
