/**
 * Intelligent Button Variant Mapping
 * Returns appropriate button variant based on action type
 * 
 * Principle: "Form Follows Function"
 * Button colors are assigned based on action semantics
 */

const BUTTON_MAPPING = {
  // Primary Actions (main CTA)
  'create': 'primary',
  'save': 'primary',
  'apply': 'primary',
  'submit': 'primary',
  'add': 'primary',
  'new': 'primary',
  
  // Positive Actions
  'approve': 'success',
  'activate': 'success',
  'enable': 'success',
  'validate': 'success',
  'confirm': 'success',
  'accept': 'success',
  
  // Destructive Actions
  'delete': 'danger',
  'remove': 'danger',
  'revoke': 'danger',
  'reject': 'danger',
  'disable': 'danger',
  'reset': 'danger',
  'deactivate': 'danger',
  
  // Neutral Actions
  'cancel': 'default',
  'close': 'default',
  'back': 'default',
  'view': 'default',
  'edit': 'default',
  'download': 'default',
  'export': 'default',
  'import': 'default',
  'refresh': 'default',
};

/**
 * Get button variant based on action type
 * 
 * @param {string} action - Action type (e.g., 'create', 'delete', 'cancel')
 * @returns {string} Button variant ('primary', 'success', 'danger', 'default')
 */
export function getButtonVariant(action) {
  const variant = BUTTON_MAPPING[action?.toLowerCase()];
  
  if (!variant) {
    console.warn(`Unknown button action: ${action}`);
    return 'default'; // Default fallback
  }
  
  return variant;
}

export default getButtonVariant;
