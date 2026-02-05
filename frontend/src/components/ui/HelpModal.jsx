/**
 * HelpModal - Contextual help modal with rich formatted content
 * Premium design with visual polish
 * 
 * Usage:
 * <HelpModal 
 *   isOpen={showHelp} 
 *   onClose={() => setShowHelp(false)}
 *   pageKey="certificates"
 * />
 */
import * as Dialog from '@radix-ui/react-dialog'
import { X, BookOpen, Lightbulb, Warning, ArrowRight, Sparkle, Info } from '@phosphor-icons/react'
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
            "w-full h-full sm:h-auto sm:mx-4 sm:max-w-lg",
            "bg-bg-primary sm:rounded-2xl sm:shadow-2xl",
            "flex flex-col overflow-hidden",
            // Animations (desktop only)
            "sm:data-[state=open]:animate-in sm:data-[state=closed]:animate-out",
            "sm:data-[state=closed]:fade-out-0 sm:data-[state=open]:fade-in-0",
            "sm:data-[state=closed]:zoom-out-95 sm:data-[state=open]:zoom-in-95",
            "sm:data-[state=closed]:slide-out-to-left-1/2 sm:data-[state=closed]:slide-out-to-top-[48%]",
            "sm:data-[state=open]:slide-in-from-left-1/2 sm:data-[state=open]:slide-in-from-top-[48%]"
          )}
        >
          {/* Header with gradient accent */}
          <div className="relative shrink-0">
            {/* Decorative gradient bar */}
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-accent-primary via-accent-secondary to-accent-primary opacity-80" />
            
            <div className="flex items-center justify-between px-4 sm:px-5 py-4 pt-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-gradient-to-br from-accent-primary/20 to-accent-primary/5 flex items-center justify-center shadow-sm ring-1 ring-accent-primary/10">
                  <BookOpen size={20} weight="duotone" className="text-accent-primary sm:w-6 sm:h-6" />
                </div>
                <div>
                  <Dialog.Title className="text-base sm:text-lg font-semibold text-text-primary">
                    {content.title}
                  </Dialog.Title>
                  <Dialog.Description className="text-xs sm:text-sm text-text-secondary">
                    {content.subtitle}
                  </Dialog.Description>
                </div>
              </div>
              <Dialog.Close className="w-9 h-9 rounded-xl flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-all focus-ring">
                <X size={20} weight="bold" />
              </Dialog.Close>
            </div>
          </div>

          {/* Content - scrollable */}
          <div className="flex-1 overflow-y-auto sm:max-h-[60vh] px-4 sm:px-5 py-4 space-y-4">
            {/* Overview card */}
            {content.overview && (
              <div className="p-3 sm:p-4 rounded-xl bg-gradient-to-br from-bg-secondary to-bg-tertiary/50 border border-border/50">
                <div className="flex items-start gap-2.5">
                  <Info size={18} weight="duotone" className="text-accent-primary mt-0.5 shrink-0" />
                  <p className="text-sm text-text-secondary leading-relaxed">
                    {content.overview}
                  </p>
                </div>
              </div>
            )}

            {/* Sections */}
            {content.sections?.map((section, idx) => (
              <Section key={idx} section={section} />
            ))}

            {/* Tips with premium styling */}
            {content.tips && content.tips.length > 0 && (
              <div className="rounded-xl p-3 sm:p-4 alert-bg-amber">
                <div className="flex items-center gap-2 mb-2.5">
                  <div className="w-7 h-7 rounded-lg icon-bg-amber flex items-center justify-center">
                    <Lightbulb size={16} weight="fill" />
                  </div>
                  <h3 className="text-sm font-semibold">Pro Tips</h3>
                </div>
                <ul className="space-y-2">
                  {content.tips.map((tip, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-xs sm:text-sm text-text-secondary">
                      <Sparkle size={12} weight="fill" className="text-amber-500 mt-1 shrink-0" />
                      <span>{tip}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Warnings with premium styling */}
            {content.warnings && content.warnings.length > 0 && (
              <div className="rounded-xl bg-gradient-to-br from-red-500/10 to-rose-500/5 border border-red-500/20 p-3 sm:p-4">
                <div className="flex items-center gap-2 mb-2.5">
                  <div className="w-7 h-7 rounded-lg bg-red-500/20 flex items-center justify-center">
                    <Warning size={16} weight="fill" className="text-red-500" />
                  </div>
                  <h3 className="text-sm font-semibold text-red-600 dark:text-red-400">Important</h3>
                </div>
                <ul className="space-y-2">
                  {content.warnings.map((warning, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-xs sm:text-sm text-text-secondary">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500 mt-1.5 shrink-0" />
                      <span>{warning}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Related pages */}
            {content.related && content.related.length > 0 && (
              <div className="pt-3 border-t border-border/50">
                <h3 className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-2">See Also</h3>
                <div className="flex flex-wrap gap-2">
                  {content.related.map((item, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded-lg bg-bg-tertiary hover:bg-bg-hover text-xs text-text-secondary transition-colors cursor-default"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Footer with premium button */}
          <div className="px-4 sm:px-5 py-4 border-t border-border/50 shrink-0 bg-bg-secondary/30">
            <Dialog.Close asChild>
              <button className="w-full sm:w-auto sm:ml-auto sm:flex btn-primary text-sm px-6 py-2.5 rounded-xl font-medium shadow-sm hover:shadow-md transition-all">
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
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
        {IconComponent && (
          <span className="w-6 h-6 rounded-lg bg-accent-primary/10 flex items-center justify-center">
            <IconComponent size={14} weight="duotone" className="text-accent-primary" />
          </span>
        )}
        {section.title}
      </h3>
      
      {section.content && (
        <p className="text-xs sm:text-sm text-text-secondary leading-relaxed pl-0.5">
          {section.content}
        </p>
      )}

      {/* List items */}
      {section.items && (
        <ul className="space-y-1.5 pl-0.5">
          {section.items.map((item, idx) => (
            <li key={idx} className="flex items-start gap-2 text-xs sm:text-sm">
              <ArrowRight size={12} weight="bold" className="text-accent-primary mt-1 shrink-0" />
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
        <dl className="space-y-2 mt-2 pl-0.5">
          {section.definitions.map((def, idx) => (
            <div key={idx} className="flex flex-col sm:flex-row sm:gap-3 text-xs sm:text-sm">
              <dt className="font-medium text-text-primary sm:min-w-[100px] sm:shrink-0">{def.term}</dt>
              <dd className="text-text-secondary">{def.description}</dd>
            </div>
          ))}
        </dl>
      )}

      {/* Code/example block */}
      {section.example && (
        <div className="mt-2 p-3 rounded-xl bg-bg-tertiary/70 border border-border/30 font-mono text-[11px] sm:text-xs text-text-secondary overflow-x-auto">
          {section.example}
        </div>
      )}
    </div>
  )
}

export default HelpModal
