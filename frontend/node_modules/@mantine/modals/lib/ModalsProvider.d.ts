import { ConfirmLabels, ContextModalProps, ModalSettings } from './context';
export interface ModalsProviderProps {
    /** Your app */
    children?: React.ReactNode;
    /** Predefined modals */
    modals?: Record<string, React.FC<ContextModalProps<any>>>;
    /** Shared Modal component props, applied for every modal */
    modalProps?: ModalSettings;
    /** Confirm modal labels */
    labels?: ConfirmLabels;
}
export declare function ModalsProvider({ children, modalProps, labels, modals }: ModalsProviderProps): import("react/jsx-runtime").JSX.Element;
