import { ModalSettings, ModalState } from './context';
interface ModalsState {
    modals: ModalState[];
    /**
     * Modal that is currently open or was the last open one.
     * Keeping the last one is necessary for providing a clean exit transition.
     */
    current: ModalState | null;
}
interface OpenAction {
    type: 'OPEN';
    modal: ModalState;
}
interface CloseAction {
    type: 'CLOSE';
    modalId: string;
    canceled?: boolean;
}
interface CloseAllAction {
    type: 'CLOSE_ALL';
    canceled?: boolean;
}
interface UpdateAction {
    type: 'UPDATE';
    modalId: string;
    newProps: Partial<ModalSettings>;
}
export declare function modalsReducer(state: ModalsState, action: OpenAction | CloseAction | CloseAllAction | UpdateAction): ModalsState;
export {};
