/**
 * HelpModal - Contextual help modal with rich formatted content
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
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-[50%] top-[50%] z-50 w-full max-w-2xl translate-x-[-50%] translate-y-[-50%] rounded-xl bg-bg-secondary border border-border shadow-2xl duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-bg-tertiary/50 rounded-t-xl">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-accent-primary to-accent-primary/70 flex items-center justify-center">
                <BookOpen size={20} weight="bold" className="text-white" />
              </div>
              <div>
                <Dialog.Title className="text-lg font-semibold text-text-primary">
                  {content.title}
                </Dialog.Title>
                <Dialog.Description className="text-sm text-text-secondary">
                  {content.subtitle}
                </Dialog.Description>
              </div>
            </div>
            <Dialog.Close asChild>
              <button className="p-2 rounded-lg hover:bg-bg-hover text-text-secondary hover:text-text-primary transition-colors">
                <X size={20} />
              </button>
            </Dialog.Close>
          </div>

          {/* Content */}
          <div className="px-6 py-5 max-h-[70vh] overflow-y-auto space-y-6">
            {/* Overview */}
            {content.overview && (
              <section>
                <p className="text-text-secondary leading-relaxed">
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
              <section className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Lightbulb size={18} weight="fill" className="text-amber-500" />
                  <h3 className="font-medium text-amber-500">Tips</h3>
                </div>
                <ul className="space-y-2">
                  {content.tips.map((tip, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-text-secondary">
                      <ArrowRight size={14} className="text-amber-500 mt-0.5 shrink-0" />
                      <span>{tip}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Warnings */}
            {content.warnings && content.warnings.length > 0 && (
              <section className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Warning size={18} weight="fill" className="text-red-500" />
                  <h3 className="font-medium text-red-500">Important</h3>
                </div>
                <ul className="space-y-2">
                  {content.warnings.map((warning, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-text-secondary">
                      <span className="text-red-500 shrink-0">•</span>
                      <span>{warning}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Related pages */}
            {content.related && content.related.length > 0 && (
              <section className="pt-4 border-t border-border">
                <h3 className="text-sm font-medium text-text-secondary mb-2">Related</h3>
                <div className="flex flex-wrap gap-2">
                  {content.related.map((item, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded-md bg-bg-tertiary text-sm text-text-secondary"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-3 border-t border-border bg-bg-tertiary/30 rounded-b-xl flex justify-end">
            <Dialog.Close asChild>
              <button className="px-4 py-2 rounded-lg bg-accent-primary hover:bg-accent-primary/90 text-white text-sm font-medium transition-colors">
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
      <h3 className="text-base font-semibold text-text-primary mb-2 flex items-center gap-2">
        {IconComponent && <IconComponent size={18} className="text-accent-primary" />}
        {section.title}
      </h3>
      
      {section.content && (
        <p className="text-sm text-text-secondary leading-relaxed mb-3">
          {section.content}
        </p>
      )}

      {/* List items */}
      {section.items && (
        <ul className="space-y-2 ml-1">
          {section.items.map((item, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm">
              <span className="text-accent-primary mt-1 shrink-0">•</span>
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
        <dl className="space-y-2 mt-2">
          {section.definitions.map((def, idx) => (
            <div key={idx} className="flex gap-2 text-sm">
              <dt className="font-medium text-text-primary min-w-[120px] shrink-0">{def.term}</dt>
              <dd className="text-text-secondary">{def.description}</dd>
            </div>
          ))}
        </dl>
      )}

      {/* Code/example block */}
      {section.example && (
        <div className="mt-3 p-3 rounded-lg bg-bg-tertiary border border-border font-mono text-xs text-text-secondary overflow-x-auto">
          {section.example}
        </div>
      )}
    </section>
  )
}

export default HelpModal
