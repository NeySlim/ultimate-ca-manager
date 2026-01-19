import { SetStateAction } from 'react';
export declare function useDebouncedState<T = any>(defaultValue: T, wait: number, options?: {
    leading: boolean;
}): readonly [T, (newValue: SetStateAction<T>) => void];
