interface Window {
    __MIKAZUKI__: any;
}

type Dict<T = any, K extends string = string> = {
    [key in K]: T;
};

declare const kSchema: unique symbol;

declare namespace Schemastery {
    type From<X> = X extends string | number | boolean ? SchemaI<X> : X extends SchemaI ? X : X extends typeof String ? SchemaI<string> : X extends typeof Number ? SchemaI<number> : X extends typeof Boolean ? SchemaI<boolean> : X extends typeof Function ? SchemaI<Function, (...args: any[]) => any> : X extends Constructor<infer S> ? SchemaI<S> : never;
    type TypeS1<X> = X extends SchemaI<infer S, unknown> ? S : never;
    type Inverse<X> = X extends SchemaI<any, infer Y> ? (arg: Y) => void : never;
    type TypeS<X> = TypeS1<From<X>>;
    type TypeT<X> = ReturnType<From<X>>;
    type Resolve = (data: any, schema: SchemaI, options?: Options, strict?: boolean) => [any, any?];
    type IntersectS<X> = From<X> extends SchemaI<infer S, unknown> ? S : never;
    type IntersectT<X> = Inverse<From<X>> extends ((arg: infer T) => void) ? T : never;
    type TupleS<X extends readonly any[]> = X extends readonly [infer L, ...infer R] ? [TypeS<L>?, ...TupleS<R>] : any[];
    type TupleT<X extends readonly any[]> = X extends readonly [infer L, ...infer R] ? [TypeT<L>?, ...TupleT<R>] : any[];
    type ObjectS<X extends Dict> = {
        [K in keyof X]?: TypeS<X[K]> | null;
    } & Dict;
    type ObjectT<X extends Dict> = {
        [K in keyof X]: TypeT<X[K]>;
    } & Dict;
    type Constructor<T = any> = new (...args: any[]) => T;
    interface Static {
        <T = any>(options: Partial<SchemaI<T>>): SchemaI<T>;
        new <T = any>(options: Partial<SchemaI<T>>): SchemaI<T>;
        prototype: SchemaI;
        resolve: Resolve;
        from<X = any>(source?: X): From<X>;
        extend(type: string, resolve: Resolve): void;
        any(): SchemaI<any>;
        never(): SchemaI<never>;
        const<const T>(value: T): SchemaI<T>;
        string(): SchemaI<string>;
        number(): SchemaI<number>;
        natural(): SchemaI<number>;
        percent(): SchemaI<number>;
        boolean(): SchemaI<boolean>;
        date(): SchemaI<string | Date, Date>;
        bitset<K extends string>(bits: Partial<Record<K, number>>): SchemaI<number | readonly K[], number>;
        function(): SchemaI<Function, (...args: any[]) => any>;
        is<T>(constructor: Constructor<T>): SchemaI<T>;
        array<X>(inner: X): SchemaI<TypeS<X>[], TypeT<X>[]>;
        dict<X, Y extends SchemaI<any, string> = SchemaI<string>>(inner: X, sKey?: Y): SchemaI<Dict<TypeS<X>, TypeS<Y>>, Dict<TypeT<X>, TypeT<Y>>>;
        tuple<const X extends readonly any[]>(list: X): SchemaI<TupleS<X>, TupleT<X>>;
        object<const X extends Dict>(dict: X): SchemaI<ObjectS<X>, ObjectT<X>>;
        union<const X>(list: readonly X[]): SchemaI<TypeS<X>, TypeT<X>>;
        intersect<const X>(list: readonly X[]): SchemaI<IntersectS<X>, IntersectT<X>>;
        transform<X, T>(inner: X, callback: (value: TypeS<X>) => T, preserve?: boolean): SchemaI<TypeS<X>, T>;
    }
    interface Options {
        autofix?: boolean;
    }
    interface Meta<T = any> {
        default?: T extends {} ? Partial<T> : T;
        required?: boolean;
        disabled?: boolean;
        collapse?: boolean;
        badges?: {
            text: string;
            type: string;
        }[];
        hidden?: boolean;
        loose?: boolean;
        role?: string;
        extra?: any;
        link?: string;
        description?: string | Dict<string>;
        comment?: string;
        pattern?: {
            source: string;
            flags?: string;
        };
        max?: number;
        min?: number;
        step?: number;
    }

    interface Schemastery<S = any, T = S> {
        (data?: S | null, options?: Schemastery.Options): T;
        new(data?: S | null, options?: Schemastery.Options): T;
        [kSchema]: true;
        uid: number;
        meta: Schemastery.Meta<T>;
        type: string;
        sKey?: SchemaI;
        inner?: SchemaI;
        list?: SchemaI[];
        dict?: Dict<SchemaI>;
        bits?: Dict<number>;
        callback?: Function;
        value?: T;
        refs?: Dict<SchemaI>;
        preserve?: boolean;
        toString(inline?: boolean): string;
        toJSON(): SchemaI<S, T>;
        required(value?: boolean): SchemaI<S, T>;
        hidden(value?: boolean): SchemaI<S, T>;
        loose(value?: boolean): SchemaI<S, T>;
        role(text: string, extra?: any): SchemaI<S, T>;
        link(link: string): SchemaI<S, T>;
        default(value: T): SchemaI<S, T>;
        comment(text: string): SchemaI<S, T>;
        description(text: string): SchemaI<S, T>;
        disabled(value?: boolean): SchemaI<S, T>;
        collapse(value?: boolean): SchemaI<S, T>;
        deprecated(): SchemaI<S, T>;
        experimental(): SchemaI<S, T>;
        pattern(regexp: RegExp): SchemaI<S, T>;
        max(value: number): SchemaI<S, T>;
        min(value: number): SchemaI<S, T>;
        step(value: number): SchemaI<S, T>;
        set(key: string, value: SchemaI): SchemaI<S, T>;
        push(value: SchemaI): SchemaI<S, T>;
        simplify(value?: any): any;
        i18n(messages: Dict): SchemaI<S, T>;
        extra<K extends keyof Schemastery.Meta>(key: K, value: Schemastery.Meta[K]): SchemaI<S, T>;
    }

}

type SchemaI<S = any, T = S> = Schemastery.Schemastery<S, T>;

declare const Schema: Schemastery.Static

declare const SHARED_SCHEMAS: Dict<any>

declare function UpdateSchema(origin: Record<string, any>, modify?: Record<string, any>, toDelete?: string[]): Record<string, any>;
