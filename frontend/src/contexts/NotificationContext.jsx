/**
 * Notification Context - Toast notifications + Confirmation dialogs
 */
import { createContext, useContext, useState, useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Icon } from '../components/atelier/Icon'
import { AtelierDialog } from '../components/atelier/AtelierDialog'
import { useTranslation } from 'react-i18next'

const NotificationContext = createContext()
// How long a sending waits for its answer: the client cannot tie a request to the sending that
// launched it, so a delay bounds it, long enough for a slow write, short for a background message
export const SENDING_MS = 10000
// A message that stays takes the mockup's failure toast; its icon and rule follow its type (extensions.css)
const TOAST_TONES = { success: ['check', 'good'], error: ['warning', 'bad'], warning: ['warning', 'warn'], info: ['bell', 'accent'] }

function AskDialog({ title, testId, onClose, children }) {
  return <AtelierDialog title={title} size="narrow" onClose={onClose} testId={testId}>{children}</AtelierDialog>
}

// A destructive action is announced in the mockup's warning notice; the safe action takes the focus
function ConfirmBody({ dialog, t, onAnswer }) {
  const danger = dialog.variant === 'danger'
  const cancel = dialog.cancelText !== null && (dialog.cancelText || t('common.cancel'))
  const confirm = dialog.confirmText || t('common.confirm')
  return (
    <>
      {danger
        ? <div className="notice warn"><Icon name="warning" /><span>{dialog.message}</span></div>
        : <p className="event-detail">{dialog.message}</p>}
      <div className="modal-actions">
        {cancel && <button type="button" className="btn" data-action="close-modal" data-autofocus="" onClick={() => onAnswer(false)}>{cancel}</button>}
        <button type="button" className={danger ? 'btn danger' : 'btn primary'} data-write="" data-autofocus={cancel ? undefined : ''}
          onClick={() => onAnswer(true)}>{confirm}</button>
      </div>
    </>
  )
}

// The answer typed in the mockup's field: its label is the question, Entrée sends it
function PromptBody({ dialog, t, value, onValue, onAnswer }) {
  const cancel = dialog.cancelText || t('common.cancel')
  const ok = dialog.confirmText || t('common.ok')
  const submit = (e) => { e.preventDefault(); onAnswer(true) }
  return (
    <form onSubmit={submit} noValidate>
      <div className="form-fields">
        <div className="field full">
          <label htmlFor="prompt-answer">{dialog.message || dialog.title}</label>
          <input id="prompt-answer" type={dialog.type || 'text'} value={value} placeholder={dialog.placeholder} autoComplete="off" spellCheck={false}
            data-autofocus="" onChange={(e) => onValue(e.target.value)} />
        </div>
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={() => onAnswer(false)}>{cancel}</button>
        <button type="submit" className="btn primary">{ok}</button>
      </div>
    </form>
  )
}

export function NotificationProvider({ children }) {
  const { t } = useTranslation()
  const [toasts, setToasts] = useState([])
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [promptDialog, setPromptDialog] = useState(null)
  const [promptValue, setPromptValue] = useState('')

  // id -> { handle, remaining, started }: each running delay, stopped and resumed together
  const timers = useRef(new Map())
  // What holds the delays: 'hover', 'focus' (in the message), 'window' (in the background)
  const pauses = useRef(new Set())

  const removeToast = useCallback((id) => {
    clearTimeout(timers.current.get(id)?.handle)
    timers.current.delete(id)
    setToasts(prev => prev.filter(toast => toast.id !== id))
  }, [])

  const runTimer = useCallback((id, entry) => {
    entry.started = Date.now()
    entry.handle = setTimeout(() => removeToast(id), entry.remaining)
  }, [removeToast])

  const setPause = useCallback((source, on) => {
    const was = pauses.current.size > 0
    if (on) pauses.current.add(source)
    else pauses.current.delete(source)
    const now = pauses.current.size > 0
    if (was === now) return
    for (const [id, entry] of timers.current) {
      if (!now) { runTimer(id, entry); continue }
      clearTimeout(entry.handle)
      entry.remaining -= Date.now() - entry.started
    }
  }, [runTimer])

  useEffect(() => {
    // blur and focus do not bubble: these hear the window's own, not an element's
    const blur = () => setPause('window', true)
    const focus = () => setPause('window', false)
    const running = timers.current
    window.addEventListener('blur', blur)
    window.addEventListener('focus', focus)
    return () => {
      window.removeEventListener('blur', blur)
      window.removeEventListener('focus', focus)
      for (const entry of running.values()) clearTimeout(entry.handle)
    }
  }, [setPause])

  // The answer to a form dialog's sending (an error or a warning): shown in it, above its buttons
  const [dialogNotice, setDialogNotice] = useState(null)
  const clearNotice = useCallback(() => setDialogNotice(null), [])
  // Dialogs sent (submit, or a click on the primary button) and not answered yet, with the delay that
  // ends their sending: an error or a warning raised meanwhile is theirs; the sending also ends at its
  // first answer or success (once the task that raised it is over) and at any other use of the dialog
  const sending = useRef(new Map())
  const disarm = useCallback((dialog) => {
    clearTimeout(sending.current.get(dialog))
    sending.current.delete(dialog)
  }, [])
  useEffect(() => {
    const armed = sending.current
    const arm = (dialog) => {
      if (!dialog?.hasAttribute('open')) return
      for (const held of armed.keys()) if (!held.isConnected) disarm(held)
      clearTimeout(armed.get(dialog))
      armed.set(dialog, setTimeout(() => armed.delete(dialog), SENDING_MS))
      setDialogNotice((current) => (current?.dialog === dialog ? null : current))
    }
    const onSubmit = (e) => arm(e.target?.closest?.('dialog'))
    const onClick = (e) => {
      const button = e.target?.closest?.(PRIMARY)
      if (button && !button.disabled) arm(button.closest('dialog'))
    }
    // Typing, or pointing at another control of the dialog: a later message no longer answers the
    // sending; a pointer on its text or padding (a scroll on a phone) is no use of it
    const onUse = (e) => {
      if (e.target?.closest?.(PRIMARY)) return
      if (e.type === 'pointerdown' && !e.target?.closest?.(CONTROLS)) return
      const dialog = e.target?.closest?.('dialog')
      if (dialog && armed.has(dialog)) disarm(dialog)
    }
    const used = ['input', 'pointerdown', 'keydown']
    document.addEventListener('submit', onSubmit, true)
    document.addEventListener('click', onClick, true)
    for (const type of used) document.addEventListener(type, onUse, true)
    return () => {
      document.removeEventListener('submit', onSubmit, true)
      document.removeEventListener('click', onClick, true)
      for (const type of used) document.removeEventListener(type, onUse, true)
      for (const handle of armed.values()) clearTimeout(handle)
      armed.clear()
    }
  }, [disarm])
  const answered = useCallback(() => {
    const dialog = typeof document === 'undefined' ? null : topModal()
    if (!dialog || !sending.current.has(dialog)) return null
    setTimeout(() => disarm(dialog), 0)
    return dialog
  }, [disarm])

  const pushToast = useCallback((type, message, duration, action) => {
    const id = Date.now() + Math.random() // unique even when called in a tight loop
    setToasts(prev => [...prev, { id, type, message, duration, action }])
    if (duration > 0) {
      const entry = { handle: null, remaining: duration, started: 0 }
      timers.current.set(id, entry)
      if (!pauses.current.size) runTimer(id, entry)
    }
  }, [runTimer])

  // options: a duration in ms (0 keeps the toast until it is closed) or { duration, action: { label, onClick } };
  // a toast that carries an action stays until it is used or closed, as the mockup's failure toast
  const addToast = useCallback((type, message, options) => {
    const opts = options !== null && typeof options === 'object' ? options : { duration: options }
    const action = opts.action && opts.action.label && typeof opts.action.onClick === 'function' ? opts.action : null
    // Only an error or a warning without action answers the sending; a success ends it with its task,
    // an information leaves it armed
    const sent = (type === 'error' || type === 'warning') && !action ? answered() : null
    if (type === 'success') answered()
    const form = sent ? formDialogBar(sent) : null
    if (form) {
      setDialogNotice({ id: Date.now() + Math.random(), type, message, duration: opts.duration, ...form })
      return
    }
    pushToast(type, message, opts.duration ?? (action ? 0 : 5000), action)
  }, [pushToast, answered])

  // A notice whose dialog closed before it was painted would be lost: it is shown as a toast
  const noticeLost = useCallback((notice) => {
    setDialogNotice((current) => (current === notice ? null : current))
    pushToast(notice.type, notice.message, notice.duration ?? 5000, null)
  }, [pushToast])

  const showSuccess = useCallback((message, options) => addToast('success', message, options), [addToast])
  const showError = useCallback((message, options) => addToast('error', message, options), [addToast])
  const showWarning = useCallback((message, options) => addToast('warning', message, options), [addToast])
  const showInfo = useCallback((message, options) => addToast('info', message, options), [addToast])

  // Confirmation dialog
  const showConfirm = useCallback((message, options = {}) => {
    return new Promise((resolve) => {
      setConfirmDialog({
        message,
        title: options.title,
        confirmText: options.confirmText,
        // An explicit `null` hides Cancel (acknowledge-only dialog); any other
        // empty value shows the translated default at render time.
        cancelText: options.cancelText,
        variant: options.variant || 'primary', // 'primary' | 'danger'
        resolve
      })
    })
  }, [])

  const handleConfirm = (result) => {
    if (confirmDialog) {
      confirmDialog.resolve(result)
      setConfirmDialog(null)
    }
  }

  // Prompt dialog
  const showPrompt = useCallback((message, options = {}) => {
    return new Promise((resolve) => {
      setPromptValue(options.defaultValue || '')
      setPromptDialog({
        message,
        title: options.title,
        placeholder: options.placeholder || '',
        type: options.type || 'text',
        confirmText: options.confirmText,
        cancelText: options.cancelText,
        resolve
      })
    })
  }, [])

  const handlePrompt = (result) => {
    if (promptDialog) {
      promptDialog.resolve(result ? promptValue : null)
      setPromptDialog(null)
      setPromptValue('')
    }
  }

  const value = useMemo(() => ({
    showSuccess,
    showError,
    showWarning,
    showInfo,
    showConfirm,
    showPrompt,
  }), [showSuccess, showError, showWarning, showInfo, showConfirm, showPrompt])

  return (
    <NotificationContext.Provider value={value}>
      {children}
      {dialogNotice && <DialogNotice notice={dialogNotice} onClose={clearNotice} onLost={noticeLost} closeLabel={t('common.closeMessage')} />}
      <ToastLine toast={toasts[toasts.length - 1]} onClose={removeToast} onPause={setPause} closeLabel={t('common.closeMessage')} />

      {/* Confirmation and prompt: the mockup's narrow modal(); inside a dialog still drawn by Radix, its own layer */}
      {confirmDialog && (
        <AskDialog title={confirmDialog.title || t('common.confirm')} testId="confirm-dialog" onClose={() => handleConfirm(false)}>
          <ConfirmBody dialog={confirmDialog} t={t} onAnswer={handleConfirm} />
        </AskDialog>
      )}

      {promptDialog && (
        <AskDialog title={promptDialog.title || t('common.inputRequired')} testId="prompt-dialog" onClose={() => handlePrompt(false)}>
          <PromptBody dialog={promptDialog} t={t} value={promptValue} onValue={setPromptValue} onAnswer={handlePrompt} />
        </AskDialog>
      )}
    </NotificationContext.Provider>
  )
}

/**
 * The mockup's toast(): one line at the bottom centre, a newer message in place of the one shown (an
 * older one still running comes back when it ends). A passing message is the inverted pill; one that
 * stays or carries an action is the framed failure line, its action and Fermer le message. The line
 * stays mounted, so each message is announced: an error assertively, the others politely.
 * Kept from Radix Toast: delays paused by pointer, focus or window blur; F8; swipe down; modal announcement.
 */
const SWIPE_CLOSE = 50
const HIDDEN = '[aria-hidden="true"], [inert], [hidden]'
const isModal = (node) => {
  if (node.getAttribute('aria-modal') === 'true') return true
  try { return node.matches(':modal') } catch { return false }
}

const canPopover = () => typeof HTMLElement !== 'undefined' && typeof HTMLElement.prototype.showPopover === 'function'

// The topmost open modal dialog: the toast is drawn in it, so it is neither under its backdrop nor inert
function topModal() {
  const open = [...document.querySelectorAll('dialog[open]')].filter(isModal)
  return open[open.length - 1] || null
}

// A dialog's primary button: a click on it sends the dialog as a submit would
const PRIMARY = 'dialog .modal-actions :is(.primary, .is-primary, .danger, [type="submit"])'
// The controls a pointer acts with in a dialog: a field, a select or a label is only focused by
// it (typing or picking a value is an input event), so pointing at one does not end the sending;
// a combobox or contenteditable is a field too (a Radix select trigger is a button)
const CONTROLS = 'button, a[href], summary, input:is([type="checkbox"], [type="radio"], [type="button"], [type="reset"], [type="image"]), [role="button"], [role="checkbox"], [role="radio"], [role="switch"], [role="tab"], [role="option"], [role="menuitem"], [role="slider"]'

// A form dialog (it has an action bar), with its last bar
function formDialogBar(dialog) {
  const bars = dialog.querySelectorAll('.modal-actions')
  return bars.length ? { dialog, bar: bars[bars.length - 1] } : null
}

/**
 * The answer to a form dialog's sending, in its action bar above its buttons (an alert). It goes
 * when the dialog closes, at the next sending, or with its own close button.
 */
function DialogNotice({ notice, onClose, onLost, closeLabel }) {
  const { dialog, bar } = notice
  // Checked after the commit: a dialog closed before the notice was painted hands it back as a toast
  useLayoutEffect(() => {
    const alive = () => bar.isConnected && dialog.isConnected && dialog.hasAttribute('open')
    let painted = false
    let lost = false
    const check = () => {
      if (lost || alive()) return
      lost = true
      if (painted) onClose()
      else onLost(notice)
    }
    check()
    if (lost) return undefined
    let frame = requestAnimationFrame(() => { frame = requestAnimationFrame(() => { painted = true }) })
    const watch = new MutationObserver(check)
    watch.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open'] })
    dialog.addEventListener('close', check)
    return () => {
      cancelAnimationFrame(frame)
      watch.disconnect()
      dialog.removeEventListener('close', check)
    }
  }, [notice, dialog, bar, onClose, onLost])
  if (!bar.isConnected) return null
  return createPortal(
    <div key={notice.id} className={`notice ${notice.type === 'warning' ? 'warn' : 'bad'} dialog-notice`} role="alert">
      <Icon name="warning" /><span>{notice.message}</span>
      <button type="button" className="icon-btn quiet" aria-label={closeLabel} onClick={onClose}><Icon name="close" /></button>
    </div>,
    bar,
  )
}

// The dialog that hides the line from screen readers (a modal one, or the layer that set aria-hidden on it)
function silencingDialog(line) {
  const shown = [...document.querySelectorAll('dialog, [role="dialog"], [role="alertdialog"], [aria-modal="true"]')]
    .filter((node) => !node.contains(line) && !node.closest(HIDDEN) && (node.tagName !== 'DIALOG' || node.open))
  const modals = shown.filter(isModal)
  if (modals.length) return modals[modals.length - 1]
  return line.closest(HIDDEN) ? shown[shown.length - 1] || null : null
}

// A live region set in the dialog, filled two frames later so it is announced, then removed after a second
function Announce({ host, text, assertive, onDone }) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let second = 0
    const first = requestAnimationFrame(() => { second = requestAnimationFrame(() => setReady(true)) })
    const done = setTimeout(onDone, 1000)
    return () => { cancelAnimationFrame(first); cancelAnimationFrame(second); clearTimeout(done) }
  }, [onDone])
  return createPortal(
    <div className="sr-only" role="status" aria-live={assertive ? 'assertive' : 'polite'}>{ready ? text : ''}</div>,
    host,
  )
}

function ToastLine({ toast, onClose, onPause, closeLabel }) {
  const ref = useRef(null)
  const origin = useRef(null)
  const focusIn = useRef(false)
  const swipe = useRef(null)
  const swallowClick = useRef(false)
  const [announce, setAnnounce] = useState(null)
  const endAnnounce = useCallback(() => setAnnounce(null), [])
  const id = toast?.id
  const current = useRef(toast)
  current.current = toast
  // Shown while a modal dialog is open, the line is drawn in it as a popover (the top layer, above
  // the dialog): outside it, it would sit under the backdrop and be inert
  const [host, setHost] = useState(null)
  useLayoutEffect(() => {
    if (!id) { setHost(null); return undefined }
    const follow = () => setHost(topModal())
    follow()
    const watch = new MutationObserver(follow)
    watch.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open'] })
    return () => watch.disconnect()
  }, [id])
  useLayoutEffect(() => {
    const el = ref.current
    if (!host || !id || typeof el?.showPopover !== 'function') return
    let shown = false
    try { shown = el.matches(':popover-open') } catch { /* an engine without the selector */ }
    if (!shown) try { el.showPopover() } catch { /* not in the document */ }
  }, [host, id])

  // Escape outside a dialog or a menu closes the message shown; one typed in a dialog stays the dialog's.
  // F8 takes the focus to the message shown.
  useEffect(() => {
    if (!toast) return undefined
    const onKey = (e) => {
      if (e.key === 'F8' || e.code === 'F8') { ref.current?.focus(); return }
      if (e.key !== 'Escape' || e.defaultPrevented || e.target?.closest?.('dialog, [role="dialog"], [role="alertdialog"], [role="menu"]')) return
      onClose(toast.id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toast, onClose])

  useLayoutEffect(() => {
    const el = ref.current
    swallowClick.current = false
    // A focus left on a removed button, or on the line now empty, goes back where it came from
    if (focusIn.current) {
      const active = document.activeElement
      if (!active || active === document.body || (!id && el.contains(active))) {
        if (id) el.focus()
        else {
          const back = origin.current
          focusIn.current = false
          origin.current = null
          onPause('focus', false)
          if (back?.isConnected && back !== document.body) back.focus()
          if (document.activeElement !== back) document.getElementById('main-title')?.focus()
        }
      }
    }
    if (!id) {
      onPause('hover', false)
      swipe.current = null
      el.removeAttribute('data-swipe')
      el.style.removeProperty('--toast-swipe-y')
      return
    }
    const into = el.closest('dialog') || silencingDialog(el)
    const shown = current.current
    if (into) setAnnounce({ id, host: into, text: [shown.message, shown.action?.label].filter(Boolean).join(' '), assertive: shown.type === 'error' })
  }, [id, onPause, host])

  const stopSwipe = () => {
    swipe.current = null
    ref.current.removeAttribute('data-swipe')
    ref.current.style.removeProperty('--toast-swipe-y')
  }
  const onPointerDown = (e) => {
    swallowClick.current = false
    if (e.button === 0) swipe.current = { x: e.clientX, y: e.clientY, moving: false }
  }
  // Radix's swipe down: it starts past 2 px (10 px by touch), a sideways move first cancels it
  const onPointerMove = (e) => {
    onPause('hover', true)
    const s = swipe.current
    if (!s) return
    const dx = e.clientX - s.x
    const dy = e.clientY - s.y
    const buffer = e.pointerType === 'touch' ? 10 : 2
    if (s.moving || dy > buffer) {
      if (!s.moving) {
        s.moving = true
        ref.current.setAttribute('data-swipe', 'move')
        try { e.target.setPointerCapture?.(e.pointerId) } catch { /* the pointer is gone */ }
      }
      ref.current.style.setProperty('--toast-swipe-y', `${Math.max(0, dy)}px`)
    } else if (Math.abs(dx) > buffer || Math.abs(dy) > buffer) swipe.current = null
  }
  const onPointerUp = (e) => {
    const s = swipe.current
    try { if (e.target.hasPointerCapture?.(e.pointerId)) e.target.releasePointerCapture(e.pointerId) } catch { /* released */ }
    if (!s?.moving) { swipe.current = null; return }
    stopSwipe()
    // the release of a swipe is not a press on the action under it
    swallowClick.current = true
    if (e.clientY - s.y > SWIPE_CLOSE) onClose(toast.id)
  }

  const held = !!toast && (toast.duration === 0 || !!toast.action)
  const [icon, tone] = TOAST_TONES[toast?.type] || TOAST_TONES.info
  const cls = toast ? `visible${held ? ` failure tone-${tone}` : ''}` : undefined
  // In a dialog the line is moved, so its own live region would be new: the announcement says it
  const line = (
      <div id="toast" ref={ref} role={host ? undefined : 'status'} aria-live={host ? 'off' : toast?.type === 'error' ? 'assertive' : 'polite'} className={cls}
        popover={host && canPopover() ? 'manual' : undefined}
        tabIndex={-1} aria-keyshortcuts="F8"
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={stopSwipe}
        onPointerLeave={() => onPause('hover', false)}
        onClickCapture={(e) => { if (swallowClick.current) { swallowClick.current = false; e.stopPropagation(); e.preventDefault() } }}
        onKeyDownCapture={() => { swallowClick.current = false }}
        onFocus={(e) => {
          if (!focusIn.current && e.relatedTarget && !ref.current.contains(e.relatedTarget)) origin.current = e.relatedTarget
          focusIn.current = true
          onPause('focus', true)
        }}
        onBlur={(e) => {
          if (ref.current.contains(e.relatedTarget)) return
          focusIn.current = false
          onPause('focus', false)
        }}>
        {toast && !held && toast.message}
        {toast && held && (
          <>
            <span className="toast-msg"><Icon name={icon} /><span className="toast-text">{toast.message}</span></span>
            {toast.action && (
              <button type="button" className="btn" id="toast-retry" data-write="false"
                onClick={() => { toast.action.onClick(); onClose(toast.id) }}>
                <Icon name="refresh" />{toast.action.label}
              </button>
            )}
            <button type="button" className="icon-btn" id="toast-close" aria-label={closeLabel} onClick={() => onClose(toast.id)}>
              <Icon name="close" />
            </button>
          </>
        )}
      </div>
  )
  return (
    <div className="atl atl-island">
      {host ? createPortal(line, host) : line}
      {announce && <Announce key={announce.id} host={announce.host} text={announce.text} assertive={announce.assertive} onDone={endAnnounce} />}
    </div>
  )
}

export function useNotification() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotification must be used within NotificationProvider')
  }
  return context
}
