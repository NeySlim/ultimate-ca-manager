export declare function useProps<T extends Record<string, any>, U extends Partial<T> = {}>(component: string, defaultProps: U, props: T): T & {
    [Key in Extract<keyof T, keyof U>]-?: U[Key] | NonNullable<T[Key]>;
};
