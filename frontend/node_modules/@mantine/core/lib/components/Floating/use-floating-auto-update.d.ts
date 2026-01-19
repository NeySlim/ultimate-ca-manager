import { FloatingPosition } from './types';
interface Payload {
    opened: boolean | undefined;
    floating: {
        update: () => void;
        refs: {
            floating: React.MutableRefObject<any>;
            reference: React.MutableRefObject<any>;
        };
    };
    positionDependencies: any[];
    position: FloatingPosition;
}
export declare function useFloatingAutoUpdate({ opened, floating, position, positionDependencies, }: Payload): void;
export {};
