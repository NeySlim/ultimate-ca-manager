import { StorageProperties } from '../use-local-storage/create-storage';
export declare function useSessionStorage<T = string>(props: StorageProperties<T>): [T, (val: T | ((prevState: T) => T)) => void, () => void];
export declare const readSessionStorageValue: <T>({ key, defaultValue, deserialize, }: StorageProperties<T>) => T;
