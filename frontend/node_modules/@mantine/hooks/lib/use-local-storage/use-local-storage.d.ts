import { StorageProperties } from './create-storage';
export declare function useLocalStorage<T = string>(props: StorageProperties<T>): [T, (val: T | ((prevState: T) => T)) => void, () => void];
export declare const readLocalStorageValue: <T>({ key, defaultValue, deserialize, }: StorageProperties<T>) => T;
