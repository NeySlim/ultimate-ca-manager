export declare function useClipboard({ timeout }?: {
    timeout?: number | undefined;
}): {
    copy: (valueToCopy: any) => void;
    reset: () => void;
    error: Error | null;
    copied: boolean;
};
