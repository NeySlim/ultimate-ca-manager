/**
 * HelpModal - Contextual help modal with rich formatted content
 * Consistent with Modal.jsx design (full-screen on mobile)
 * 
 * Usage:
 * <HelpModal 
 *   isOpen={showHelp} 
 *   onClose={() => setShowHelp(false)}
 *   pageKey="certificates"
 * />
 */
import * as Dialog from '@radix-ui/react-dialog'
import { X, BookOpen, Lightbulb, Warning, ArrowRight } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { helpContent } from '../../data/helpContent'

export function HelpModal({ isOpen, onClose, pageKey }) {
  const content = helpContent[pageKey]
  
  if (!content) {
    return null
  }

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop fixed inset-0 z-40 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content 
          className={cn(
            // Mobile: full screen
            "fixed inset-0 z-50",
            "sm:inset-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2",
            "w-full h-full sm:h-auto sm:mx-4 sm:max-w-2xl",
            "bg-bg-primary sm:modal-enhanced sm:rounded-xl",
            "flex flex-col",
            // Animations (desktop only)
            "sm:data-[state=open]:animate-in sm:data-[state=closed]:animate-out",
            "sm:data-[state=closed]:fade-out-0 sm:data-[state=open]:fade-in-0",
            "sm:data-[state=closed]:zoom-out-95 sm:data-[state=open]:zoom-in-95",
            "sm:data-[state=closed]:slide-out-to-left-1/2 sm:data-[state=closed]:slide-out-to-top-[48%]",
            "sm:data-[state=open]:slide-in-from-left-1/2 sm:data-[state=open]:slide-in-from-top-[48%]"
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/50 shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-accent-primary/10 flex items-center justify-center">
                <BookOpen size={18} weight="bold" className="text-accent-primary" />
              </div>
              <div>
                <Dialog.Title className="text-sm font-semibold text-text-primary">
                  {content.title}
                </Dialog.Title>
                <Dialog.Description className="text-xs text-text-secondary">
                  {content.subtitle}
                </Dialog.Description>
              </div>
            </div>
            <Dialog.Close className="w-8 h-8 sm:w-7 sm:h-7 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-all focus-ring">
              <X size={18} className="sm:hidden" />
              <X size={16} className="hidden sm:block" />
            </Dialog.Close>
          </div>

          {/* Content - scrollable */}
          <div className="flex-1 overflow-y-auto sm:max-h-[70vh] px-4 py-4 space-y-5">
            {/* Overview */}
            {content.overview && (
              <section>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {content.overview}
                </p>
              </section>
            )}

            {/* Sections */}
            {content.sections?.map((section, idx) => (
              <Section key={idx} section={section} />
            ))}

            {/* Tips */}
            {content.tips && content.tips.length > 0 && (
              <section className="bg-status-warning/10 border border-status-warning/20 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Lightbulb size={16} weight="fill" className="text-status-warning" />
                  <h3 className="text-sm font-medium text-status-warning">Tips</h3>
                </div>
                <ul className="space-y-1.5">
                  {content.tips.map((tip, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-xs text-text-secondary">
                      <ArrowRight size={12} className="text-status-warning mt-0.5 shrink-0" />
                      <span>{tip}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Warnings */}
            {content.warnings && content.warnings.length > 0 && (
              <section className="bg-status-error/10 border border-status-error/20 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Warning size={16} weight="fill" className="text-status-error" />
                  <h3 className="text-sm font-medium text-status-error">Important</h3>
                </div>
                <ul className="space-y-1.5">
                  {content.warnings.map((warning, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-xs text-text-secondary">
                      <span className="text-status-error shrink-0">•</span>
                      <span>{warning}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Related pages */}
            {content.related && content.related.length > 0 && (
              <section className="pt-3 border-t border-border/50">
                <h3 className="text-xs font-medium text-text-tertiary mb-2">Related</h3>
                <div className="flex flex-wrap gap-1.5">
                  {content.related.map((item, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded bg-bg-tertiary text-xs text-text-secondary"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-border/50 shrink-0 flex justify-end">
            <Dialog.Close asChild>
              <button className="btn-primary text-sm px-4 py-2">
                Got it
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function Section({ section }) {
  const IconComponent = section.icon
  
  return (
    <section>
      <h3 className="text-sm font-semibold text-text-primary mb-1.5 flex items-center gap-2">
        {IconComponent && <IconComponent size={16} className="text-accent-primary" />}
        {section.title}
      </h3>
      
      {section.content && (
        <p className="text-xs text-text-secondary leading-relaxed mb-2">
          {section.content}
        </p>
      )}

      {/* List items */}
      {section.items && (
        <ul className="space-y-1 ml-1">
          {section.items.map((item, idx) => (
            <li key={idx} className="flex items-start gap-2 text-xs">
              <span className="text-accent-primary mt-0.5 shrink-0">•</span>
              <div>
                {typeof item === 'object' && item.label && (
                  <span className="font-medium text-text-primary">{item.label}: </span>
                )}
                <span className="text-text-secondary">{typeof item === 'object' ? item.text : item}</span>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Key-value definitions */}
      {section.definitions && (
        <dl className="space-y-1.5 mt-2">
          {section.definitions.map((def, idx) => (
            <div key={idx} className="flex gap-2 text-xs">
              <dt className="font-medium text-text-primary min-w-[100px] shrink-0">{def.term}</dt>
              <dd className="text-text-secondary">{def.description}</dd>
            </div>
          ))}
        </dl>
      )}

      {/* Code/example block */}
      {section.example && (
        <div className="mt-2 p-2.5 rounded-lg bg-bg-tertiary border border-border/50 font-mono text-[11px] text-text-secondary overflow-x-auto">
          {section.example}
        </div>
      )}
    </section>
  )
}

export default HelpModal
