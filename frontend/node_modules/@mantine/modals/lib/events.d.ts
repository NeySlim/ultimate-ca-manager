import { MantineModal, MantineModals, ModalSettings, OpenConfirmModal, OpenContextModal } from './context';
type ModalsEvents = {
    openModal: (payload: ModalSettings) => string;
    openConfirmModal: (payload: OpenConfirmModal) => string;
    openContextModal: <TKey extends MantineModal>(payload: OpenContextModal<Parameters<MantineModals[TKey]>[0]['innerProps']> & {
        modal: TKey;
    }) => string;
    closeModal: (id: string) => void;
    closeContextModal: <TKey extends MantineModal>(id: TKey) => void;
    closeAllModals: () => void;
    updateModal: (payload: {
        modalId: string;
    } & Partial<ModalSettings>) => void;
    updateContextModal: (payload: {
        modalId: string;
    } & Partial<OpenContextModal<any>>) => void;
};
export declare const useModalsEvents: (events: ModalsEvents) => void, createEvent: <EventKey extends keyof ModalsEvents>(event: EventKey) => (...payload: Parameters<ModalsEvents[EventKey]>[0] extends undefined ? [undefined?] : [Parameters<ModalsEvents[EventKey]>[0]]) => void;
export declare const openModal: ModalsEvents['openModal'];
export declare const openConfirmModal: ModalsEvents['openConfirmModal'];
export declare const openContextModal: ModalsEvents['openContextModal'];
export declare const closeModal: (payload_0: string) => void;
export declare const closeContextModal: ModalsEvents['closeContextModal'];
export declare const closeAllModals: (payload_0?: undefined) => void;
export declare const updateModal: (payload: {
    modalId: string;
} & Partial<ModalSettings>) => void;
export declare const updateContextModal: (payload: {
    modalId: string;
} & Partial<OpenContextModal<any>>) => void;
export declare const modals: {
    open: ModalsEvents['openModal'];
    close: ModalsEvents['closeModal'];
    closeAll: ModalsEvents['closeAllModals'];
    openConfirmModal: ModalsEvents['openConfirmModal'];
    openContextModal: ModalsEvents['openContextModal'];
    updateModal: ModalsEvents['updateModal'];
    updateContextModal: ModalsEvents['updateContextModal'];
};
export {};
