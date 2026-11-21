/**
 * Notification Context - Toast notifications + Confirmation dialogs
 */
import { createContext, useContext, useState, useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Warning } from '@phosphor-icons/react'
import { Icon } from '../components/atelier/Icon'
import { AtelierDialog } from '../components/atelier/AtelierDialog'
import { Button } from '../components/Button'
import { Input } from '../components/Input'
import { ListDialog } from '../components/list/ListDialog'
import { useTranslation } from 'react-i18next'

const NotificationContext = createContext()
// A message that stays takes the mockup's failure toast; its icon and rule follow its type (extensions.css)
const TOAST_TONES = { success: ['check', 'good'], error: ['warning', 'bad'], warning: ['warning', 'warn'], info: ['bell', 'accent'] }

// A question asked from a dialog still drawn by Radix (outside the converted zones) stays in a Radix
// layer: Radix holds the pointer and the focus inside its own layers, a native <dialog> would get neither.
const radixDialogOpen = () => !!document.querySelector('.lv-dialog[data-state="open"]')

function AskDialog({ legacy, title, testId, onClose, children }) {
  if (legacy) {
    return (
      <ListDialog open onOpenChange={(open) => !open && onClose()} title={title} className="ui-modal" testId={testId}>
        {children}
      </ListDialog>
    )
  }
  return <AtelierDialog title={title} size="narrow" onClose={onClose} testId={testId}>{children}</AtelierDialog>
}

// A destructive action is announced in the mockup's warning notice; the safe action takes the focus
function ConfirmBody({ dialog, legacy, t, onAnswer }) {
  const danger = dialog.variant === 'danger'
  const cancel = dialog.cancelText !== null && (dialog.cancelText || t('common.cancel'))
  const confirm = dialog.confirmText || t('common.confirm')
  if (legacy) {
    return (
      <>
        {danger ? (
          <div className="ui-notice is-warn ui-dialog-notice">
            <Warning aria-hidden="true" />
            <p className="ui-notice-body">{dialog.message}</p>
          </div>
        ) : <p className="ui-dialog-message">{dialog.message}</p>}
        <div className="ui-dialog-actions">
          {cancel && <Button type="button" variant="secondary" onClick={() => onAnswer(false)} data-autofocus>{cancel}</Button>}
          <Button type="button" variant={danger ? 'danger' : 'primary'} onClick={() => onAnswer(true)} data-autofocus={cancel ? undefined : true}>{confirm}</Button>
        </div>
      </>
    )
  }
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
function PromptBody({ dialog, legacy, t, value, onValue, onAnswer }) {
  const cancel = dialog.cancelText || t('common.cancel')
  const ok = dialog.confirmText || t('common.ok')
  const submit = (e) => { e.preventDefault(); onAnswer(true) }
  if (legacy) {
    return (
      <form onSubmit={submit}>
        {dialog.message && <p className="ui-dialog-message">{dialog.message}</p>}
        <Input type={dialog.type || 'text'} value={value} onChange={(e) => onValue(e.target.value)} placeholder={dialog.placeholder}
          aria-label={dialog.message || dialog.title} autoFocus />
        <div className="ui-dialog-actions">
          <Button type="button" variant="secondary" onClick={() => onAnswer(false)}>{cancel}</Button>
          <Button type="submit">{ok}</Button>
        </div>
      </form>
    )
  }
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

  // options: a duration in ms (0 keeps the toast until it is closed) or { duration, action: { label, onClick } };
  // a toast that carries an action stays until it is used or closed, as the mockup's failure toast
  const addToast = useCallback((type, message, options) => {
    const opts = options !== null && typeof options === 'object' ? options : { duration: options }
    const action = opts.action && opts.action.label && typeof opts.action.onClick === 'function' ? opts.action : null
    const duration = opts.duration ?? (action ? 0 : 5000)
    const id = Date.now() + Math.random() // unique even when called in a tight loop
    setToasts(prev => [...prev, { id, type, message, duration, action }])

    if (duration > 0) {
      const entry = { handle: null, remaining: duration, started: 0 }
      timers.current.set(id, entry)
      if (!pauses.current.size) runTimer(id, entry)
    }
  }, [runTimer])

  const showSuccess = useCallback((message, options) => addToast('success', message, options), [addToast])
  const showError = useCallback((message, options) => addToast('error', message, options), [addToast])
  const showWarning = useCallback((message, options) => addToast('warning', message, options), [addToast])
  const showInfo = useCallback((message, options) => addToast('info', message, options), [addToast])

  // Confirmation dialog
  const showConfirm = useCallback((message, options = {}) => {
    return new Promise((resolve) => {
      setConfirmDialog({
        legacy: radixDialogOpen(),
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
        legacy: radixDialogOpen(),
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
      <ToastLine toast={toasts[toasts.length - 1]} onClose={removeToast} onPause={setPause} closeLabel={t('common.closeMessage')} />

      {/* Confirmation and prompt: the mockup's narrow modal(); inside a dialog still drawn by Radix, its own layer */}
      {confirmDialog && (
        <AskDialog legacy={confirmDialog.legacy} title={confirmDialog.title || t('common.confirm')} testId="confirm-dialog" onClose={() => handleConfirm(false)}>
          <ConfirmBody dialog={confirmDialog} legacy={confirmDialog.legacy} t={t} onAnswer={handleConfirm} />
        </AskDialog>
      )}

      {promptDialog && (
        <AskDialog legacy={promptDialog.legacy} title={promptDialog.title || t('common.inputRequired')} testId="prompt-dialog" onClose={() => handlePrompt(false)}>
          <PromptBody dialog={promptDialog} legacy={promptDialog.legacy} t={t} value={promptValue} onValue={setPromptValue} onAnswer={handlePrompt} />
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
    const host = silencingDialog(el)
    const shown = current.current
    if (host) setAnnounce({ id, host, text: [shown.message, shown.action?.label].filter(Boolean).join(' '), assertive: shown.type === 'error' })
  }, [id, onPause])

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
  return (
    <div className="atl atl-island">
      <div id="toast" ref={ref} role="status" aria-live={toast?.type === 'error' ? 'assertive' : 'polite'} className={cls}
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
