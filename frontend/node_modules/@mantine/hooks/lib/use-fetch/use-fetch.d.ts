export interface UseFetchOptions extends RequestInit {
    autoInvoke?: boolean;
}
export declare function useFetch<T>(url: string, { autoInvoke, ...options }?: UseFetchOptions): {
    data: T | null;
    loading: boolean;
    error: Error | null;
    refetch: () => Promise<any> | undefined;
    abort: () => void;
};
