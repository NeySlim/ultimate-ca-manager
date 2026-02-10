/**
 * HelpModal - Contextual help modal with rich formatted content
 * Uses global Modal patterns (modal-enhanced, visual-section-header)
 */
import * as Dialog from '@radix-ui/react-dialog'
import { X, BookOpen, Lightbulb, Warning, ArrowRight, Sparkle, Info, Link as LinkIcon } from '@phosphor-icons/react'
import { cn } from '../../lib/utils'
import { helpContent } from '../../data/helpContent'
import { useTranslation } from 'react-i18next'

export function HelpModal({ isOpen, onClose, pageKey }) {
  const { t } = useTranslation()
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
            "fixed inset-0 z-50",
            "sm:inset-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2",
            "w-full h-full sm:h-auto sm:mx-4 sm:max-w-2xl sm:max-h-[85vh]",
            "bg-bg-primary sm:modal-enhanced",
            "flex flex-col overflow-hidden",
            "sm:data-[state=open]:animate-in sm:data-[state=closed]:animate-out",
            "sm:data-[state=closed]:fade-out-0 sm:data-[state=open]:fade-in-0",
            "sm:data-[state=closed]:zoom-out-95 sm:data-[state=open]:zoom-in-95",
            "sm:data-[state=closed]:slide-out-to-left-1/2 sm:data-[state=closed]:slide-out-to-top-[48%]",
            "sm:data-[state=open]:slide-in-from-left-1/2 sm:data-[state=open]:slide-in-from-top-[48%]"
          )}
        >
          {/* Header — accent gradient banner */}
          <div className="relative shrink-0 help-modal-header">
            {/* Accent top line */}
            <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl" style={{ background: 'var(--gradient-primary)', opacity: 0.8 }} />
            
            <div className="px-5 sm:px-6 py-5 sm:py-6">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3.5">
                  <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-xl help-modal-icon-bg flex items-center justify-center">
                    <BookOpen size={22} weight="duotone" className="text-white sm:w-6 sm:h-6" />
                  </div>
                  <div>
                    <Dialog.Title className="text-lg sm:text-xl font-bold text-text-primary">
                      {content.title}
                    </Dialog.Title>
                    <Dialog.Description className="text-sm text-text-secondary mt-0.5">
                      {content.subtitle}
                    </Dialog.Description>
                  </div>
                </div>
                <Dialog.Close className="w-9 h-9 rounded-xl flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-all focus-ring">
                  <X size={18} weight="bold" />
                </Dialog.Close>
              </div>
            </div>
          </div>

          {/* Content — scrollable */}
          <div className="flex-1 overflow-y-auto px-5 sm:px-6 py-5 space-y-4">
            {/* Overview */}
            {content.overview && (
              <div className="p-4 rounded-xl bg-bg-tertiary/50 border border-border">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-accent-25 flex items-center justify-center shrink-0">
                    <Info size={16} weight="duotone" className="text-accent-primary" />
                  </div>
                  <p className="text-sm text-text-secondary leading-relaxed pt-1">
                    {content.overview}
                  </p>
                </div>
              </div>
            )}

            {/* Sections — using visual-section-header pattern */}
            {content.sections?.map((section, idx) => (
              <Section key={idx} section={section} />
            ))}

            {/* Tips */}
            {content.tips && content.tips.length > 0 && (
              <div className="rounded-xl overflow-hidden border border-border">
                <div className="visual-section-header !py-2.5">
                  <div className="w-7 h-7 rounded-lg icon-bg-amber flex items-center justify-center">
                    <Lightbulb size={14} weight="fill" />
                  </div>
                  {t('help.proTips', 'Pro Tips')}
                </div>
                <div className="visual-section-body">
                  <ul className="space-y-2.5">
                    {content.tips.map((tip, idx) => (
                      <li key={idx} className="flex items-start gap-2.5 text-sm text-text-secondary">
                        <Sparkle size={14} weight="fill" className="text-status-warning mt-0.5 shrink-0" />
                        <span>{tip}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Warnings */}
            {content.warnings && content.warnings.length > 0 && (
              <div className="rounded-xl overflow-hidden border border-status-danger/30">
                <div className="visual-section-header !py-2.5" style={{ background: 'color-mix(in srgb, var(--status-danger) 10%, var(--bg-tertiary))' }}>
                  <div className="w-7 h-7 rounded-lg icon-bg-red flex items-center justify-center">
                    <Warning size={14} weight="fill" />
                  </div>
                  <span className="text-status-danger">{t('common.warnings', 'Important')}</span>
                </div>
                <div className="visual-section-body">
                  <ul className="space-y-2.5">
                    {content.warnings.map((warning, idx) => (
                      <li key={idx} className="flex items-start gap-2.5 text-sm text-text-secondary">
                        <span className="w-1.5 h-1.5 rounded-full bg-status-danger mt-2 shrink-0" />
                        <span>{warning}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Related */}
            {content.related && content.related.length > 0 && (
              <div className="pt-4 border-t border-border">
                <h3 className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                  <LinkIcon size={12} weight="bold" />
                  {t('help.seeAlso', 'See Also')}
                </h3>
                <div className="flex flex-wrap gap-2">
                  {content.related.map((item, idx) => (
                    <span
                      key={idx}
                      className="px-3 py-1.5 rounded-lg bg-bg-tertiary hover:bg-bg-hover text-xs font-medium text-text-secondary transition-colors cursor-default border border-border"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-5 sm:px-6 py-4 border-t border-border shrink-0 flex justify-end">
            <Dialog.Close asChild>
              <button className="help-modal-btn text-sm px-6 py-2.5 rounded-xl font-semibold transition-all">
                {t('common.gotIt', 'Got it')}
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
    <div className="rounded-xl overflow-hidden border border-border">
      {/* Section header — uses visual-section-header global pattern */}
      <div className="visual-section-header !py-2.5">
        {IconComponent && (
          <span className="w-7 h-7 rounded-lg bg-accent-25 flex items-center justify-center">
            <IconComponent size={14} weight="duotone" className="text-accent-primary" />
          </span>
        )}
        {section.title}
      </div>

      {/* Section body — uses visual-section-body global pattern */}
      <div className="visual-section-body">
        {section.content && (
          <p className="text-sm text-text-secondary leading-relaxed mb-3">
            {section.content}
          </p>
        )}

        {/* List items */}
        {section.items && (
          <ul className="space-y-2">
            {section.items.map((item, idx) => (
              <li key={idx} className="flex items-start gap-2.5 text-sm">
                <ArrowRight size={13} weight="bold" className="text-accent-primary mt-1 shrink-0" />
                <div>
                  {typeof item === 'object' && item.label && (
                    <span className="font-semibold text-text-primary">{item.label}: </span>
                  )}
                  <span className="text-text-secondary">{typeof item === 'object' ? item.text : item}</span>
                </div>
              </li>
            ))}
          </ul>
        )}

        {/* Definitions */}
        {section.definitions && (
          <dl className="space-y-2">
            {section.definitions.map((def, idx) => (
              <div key={idx} className="flex items-baseline gap-3 text-sm">
                <dt className="font-semibold text-text-primary min-w-[110px] shrink-0">{def.term}</dt>
                <dd className="text-text-secondary">{def.description}</dd>
              </div>
            ))}
          </dl>
        )}

        {/* Code/example */}
        {section.example && (
          <div className="mt-3 p-3 rounded-lg bg-bg-tertiary border border-border font-mono text-xs text-text-secondary overflow-x-auto">
            {section.example}
          </div>
        )}
      </div>
    </div>
  )
}

export default HelpModal
