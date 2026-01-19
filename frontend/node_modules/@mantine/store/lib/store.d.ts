export type MantineStoreSubscriber<Value> = (value: Value) => void;
type SetStateCallback<Value> = (value: Value) => Value;
export interface MantineStore<Value> {
    getState: () => Value;
    setState: (value: Value | SetStateCallback<Value>) => void;
    updateState: (value: Value | SetStateCallback<Value>) => void;
    initialize: (value: Value) => void;
    subscribe: (callback: MantineStoreSubscriber<Value>) => () => void;
}
export type MantineStoreValue<Store extends MantineStore<any>> = ReturnType<Store['getState']>;
export declare function createStore<Value extends Record<string, any>>(initialState: Value): MantineStore<Value>;
export declare function useStore<Store extends MantineStore<any>>(store: Store): ReturnType<Store["getState"]>;
export {};
