---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> represents an effectful computation as a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

`IO<T>` lets you compose effectful computations by representing them as deferred computations that can be run later.

This article is not advocating an `IO<T>` style as idiomatic C#. The goal is to make the separation between constructing and running effectful work visible, not to eliminate effects. Effects are what let a program interact with the outside world and do useful work at all.

Calling a function may do more than calculate a value: it may invoke an API, query a database, send an email, write a file, or observe time or randomness. These observable interactions are called effects. A pure function depends only on its declared inputs: the same inputs produce the same result, and evaluating it does not read from or modify the outside world.

Pure functions are easier to compose because recomputing, delaying, repeating, or discarding them does not change anything outside the calculation. Effects are different because invocation itself can matter. Once timing, order, and repetition matter, an ordinary host abstraction can accidentally become the execution policy for the effect. `List.Map`, `Maybe.Map`, and `Result.Map` already decide when the supplied function runs. That is fine for pure code, but if the function performs effects directly, those invocation rules become the execution policy. Returning `IO<T>` changes the arrangement: the function now returns a suspended effectful computation instead of performing the effect immediately, so the surrounding program can compose those computations first and decide later how the larger whole should run.

## When Execution Policy Matters

Consider a pure price calculation:

```csharp
public static decimal CalculateLineTotal(
    int quantity,
    decimal unitPrice,
    decimal taxRate)
{
    decimal subtotal = quantity * unitPrice;
    return subtotal + subtotal * taxRate;
}

var quantities = new List<int> { 1, 2, 3 };

var totals =
    quantities.Map(quantity =>
        CalculateLineTotal(quantity, 19.99m, 0.13m));
// `Map` is pseudocode here, following Part 1.
```

In Part 1, `List.Map` visits each element now and builds a new list. Because `CalculateLineTotal` is pure, that changes work, not meaning: the same inputs still determine the same result, and replacing `CalculateLineTotal(quantity, 19.99m, 0.13m)` with its resulting `decimal` does not change the program.

Now consider an effectful price lookup:

```csharp
public static decimal FetchCurrentPrice(
    IRemotePriceApi remotePriceApi,
    string productId)
{
    return remotePriceApi.GetCurrentPrice(productId);
}

var productIds = new List<string> { "A-100", "B-200", "C-300" };

var prices =
    productIds.Map(productId =>
        FetchCurrentPrice(remotePriceApi, productId));
// `Map` is pseudocode here, following Part 1.
// Requests are sent while Map traverses the list.
```

`List.Map` is still just applying the supplied function according to the list's traversal policy. The difference is that invoking `FetchCurrentPrice` sends a request, so eager traversal sends requests eagerly and a thrown exception stops later product IDs.

The method still looks like an ordinary function returning `decimal`, but invoking it sends a request and observes external state not fully described by its arguments. A later call may observe a new price, consume quota, fail transiently, or be throttled. Replacing `FetchCurrentPrice(remotePriceApi, productId)` with a returned `decimal` therefore hides work that already happened, which is why the host abstraction's invocation rule becomes significant.

These types all provide a map-shaped operation, but `Map` does not imply one execution strategy. `List.Map` runs immediately for each element, `Maybe<T>.Map` runs zero or one time, `Result<TSuccess, TError>.Map` runs only on the success path, and this article's `IO<T>.Map` defers execution until the resulting `IO` runs. For pure functions those policies mostly change work; for effectful ones they change which effects occur.

That is why `IO<T>` helps: it represents the operation as a pure, first-class suspended computation that can be composed before any effect happens.

## From an immediate result to a suspended computation

The effectful price lookup is still a function we want to compose with other steps. The problem is that a function returning `decimal` can produce that value only after sending the request, so by the time a larger program receives the result the effect has already happened. `IO<T>` is a value representing a computation that may perform effects and eventually return a `T`. Returning `IO<decimal>` keeps the work suspended long enough to compose first and run later.

So the signature changes:

```text
(IRemotePriceApi, string) -> decimal
(IRemotePriceApi, string) -> IO<decimal>
```

```csharp
public static IO<decimal> FetchCurrentPriceIO(
    IRemotePriceApi remotePriceApi,
    string productId)
{
    return IO<decimal>.Delay(
        () => FetchCurrentPrice(remotePriceApi, productId));
}
```

Calling `FetchCurrentPriceIO` sends no request. It returns a pure `IO<decimal>` value representing deferred work. Constructing that value still sends no request; `Run()` executes the wrapped work. That lets the surrounding program compose it before any request happens.

Here, `Delay` means **defer evaluation**. It does not pause a thread, wait for a duration, or behave like `Task.Delay`.

```csharp
IO<decimal> request =
    FetchCurrentPriceIO(remotePriceApi, productId);
// No request yet.

decimal price = request.Run();
// The request is sent here.
```

Constructing the `IO<decimal>` value is not the same thing as running it: the first just produces a value, while the second executes the wrapped computation and performs its effects. In this teaching model, each call to `Run()` performs the computation again.

`Run()` makes the execution boundary explicit. The point of returning `IO<T>` is that the larger program can transform, combine, traverse, store, and pass around the work before crossing that boundary. In a fuller effect system, application code would usually return the final `IO` and let a runtime or interpreter execute it instead of calling `Run()` manually. In this small teaching model, `Run()` stands in for that boundary.

The following examples use C#'s `from` and `select` syntax over `IO<T>`. Assume that `Select` and `SelectMany` delegate to `Map` and `FlatMap`. No `IEnumerable<T>` or sequence enumeration is involved; the compiler translates this syntax into method calls on `IO<T>`.

```csharp
IO<decimal> totalProgram =
    from unitPrice in
        FetchCurrentPriceIO(remotePriceApi, productId)
    select
        CalculateLineTotal(quantity, unitPrice, taxRate);
// Still no request.
```

Constructing `totalProgram` sends no request. Running it fetches the price and then calculates the total:

```csharp
decimal total = totalProgram.Run();
```

Suspension does not itself choose an execution policy. It keeps the effect unperformed while the program is assembled. Here, `FlatMap` establishes sequential order, while other combinators can later express policies such as retries, pacing, or collection traversal.

> **`IO<T>` does not remove the effect or decide how it should run. The indirection is the point: it makes the effectful computation explicit and keeps it suspended while those decisions are composed.**

Once effects are represented as values, these operations form a small language for assembling larger effectful programs.

The teaching model has five central operations:

```text
Pure    : T -> IO<T>
Delay   : (() -> T) -> IO<T>
Map     : IO<T> -> (T -> TResult) -> IO<TResult>
FlatMap : IO<T> -> (T -> IO<TResult>) -> IO<TResult>
Run     : IO<T> -> T
```

`Pure` wraps an already available value; `Delay` suspends a computation; `Map` transforms an eventual result; `FlatMap` composes a dependent `IO`; and `Run` performs the computation. Here, `Delay` is being used to postpone an effect.

Passing an effectful call to `Pure` would be too late:

```csharp
IO<decimal> notSuspended =
    IO<decimal>.Pure(
        FetchCurrentPrice(remotePriceApi, productId));
// FetchCurrentPrice runs before Pure is called.
```

A `Func<T>` can also postpone work. The difference is the contract: a bare `Func<T>` only says some code can be invoked later, while `IO<T>` gives that deferred work a specific semantic type and an explicit `Run()` boundary.

## A small `IO<T>`

```csharp
public sealed class IO<T>
{
    private readonly Func<T> operation;

    private IO(Func<T> operation)
    {
        this.operation = operation;
    }

    public static IO<T> Pure(T value)
    {
        // `Pure` lifts an existing value into `IO<T>`.
        // The `Unit` type used later is the void-like result value.
        return new IO<T>(() => value);
    }

    public static IO<T> Delay(Func<T> operation)
    {
        return new IO<T>(operation);
    }

    public IO<TResult> Map<TResult>(
        Func<T, TResult> transform)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();
            return transform(value);
        });
    }

    public IO<TResult> FlatMap<TResult>(
        Func<T, IO<TResult>> next)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();
            IO<TResult> nextComputation = next(value);

            return nextComputation.Run();
        });
    }

    public T Run()
    {
        return operation();
    }
}
```

`IO<T>` stores a parameterless operation and provides ways to suspend, compose, and run it. `Pure` is the value-lifting operation; `Delay` receives a computation and stores it without invoking it.

`Map` and `FlatMap` call `Run()` only inside the delegate stored by the returned `IO`, so calling either method builds another suspended computation. The inner calls occur only when that returned `IO` runs.

In this model, use `Map` for a pure transformation that returns a plain value. Use `FlatMap` when the next step returns another `IO`; mapping such a function directly would produce `IO<IO<TResult>>`. `FlatMap` combines those nested computations into one `IO<TResult>` while preserving suspension, but C# cannot enforce those conventions.

## Compose first, run later

Suppose `ParseOrder` returns an order with `ProductId`, `Quantity`, and `TaxRate`. We want to read an order, fetch its current price, calculate the total, render a report, and write it to disk. Writing a file has no meaningful result beyond successful completion, so the wrapper returns `IO<Unit>`:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}
```

`Unit` is roughly `void` represented as a value; `Pure` is the operation that lifts an existing value into `IO<T>`.

```csharp
public static IO<string> ReadAllTextIO(string path)
{
    return IO<string>.Delay(
        () => File.ReadAllText(path));
}

public static IO<Unit> WriteAllTextIO(
    string path,
    string contents)
{
    return IO<Unit>.Delay(() =>
    {
        File.WriteAllText(path, contents);
        return Unit.Value;
    });
}
```

The following uses C# query syntax over `IO<T>`. Assume `Select` and `SelectMany` delegate to `Map` and `FlatMap`.

```csharp
public static IO<Unit> LoadOrderAndWriteReport(
    IRemotePriceApi remotePriceApi,
    string orderPath,
    string reportPath)
{
    return
        from contents in ReadAllTextIO(orderPath)
        let order = ParseOrder(contents)
        from unitPrice in FetchCurrentPriceIO(
            remotePriceApi,
            order.ProductId)
        let total = CalculateLineTotal(
            order.Quantity,
            unitPrice,
            order.TaxRate)
        let report = RenderReport(
            order,
            unitPrice,
            total)
        from completion in WriteAllTextIO(
            reportPath,
            report)
        select completion;
}
```

The result remains a suspended `IO<Unit>`. Constructing it performs none of the wrapped effects; when it runs, the file is read before parsing, the price is fetched after the product ID is known, and the report is written last. The `let` clauses correspond to pure `Map` steps, and the effectful dependencies use `FlatMap`.

## Traversal makes the batch policy explicit

`FlatMap` orders one dependent step after another. A collection raises a different question: how should the same effectful action be applied to many inputs?

`IO<T>` cannot choose the correct policy. It makes effectful computations available as values so a combinator can encode that policy before execution.

A sequential traversal answers that explicitly:

```csharp
IO<List<decimal>> program =
    productIds.TraverseSequential(productId =>
        FetchCurrentPriceIO(
            remotePriceApi,
            productId));
// No requests yet.
```

`TraverseSequential` returns one suspended program that visits the product IDs in order, runs one request at a time, and collects the results. `TraverseSequential` starts from plain inputs and an effectful function, while `SequenceSequential` starts from `IO` values that already exist. Both produce one suspended computation for the entire batch:

```text
List<IO<T>> -> IO<List<T>>
```

Work begins only when the outer program runs:

```csharp
List<decimal> prices = program.Run();
```

This traversal defines a concrete policy:

* Traversal and `action` invocation wait until `Run()`.
* Items are processed in list order, one at a time.
* Results preserve the same order.
* An exception prevents later items from running but does not undo completed effects.
* Each outer `Run()` repeats the traversal and its effects.

The nested `Run()` calls are part of the suspended traversal and occur only after the outer program begins.

Other traversals could add pacing, selective retries, failure collection, or bounded concurrency. Such policies are not automatically safe: retrying a read may be acceptable, while retrying a non-idempotent command may duplicate it.

## Runtime semantics and limitations

This `IO<T>` is a tiny teaching model, not a recommendation for idiomatic C# application structure. It is synchronous, cold, opaque, and non-memoized: nothing happens until `Run()`, and each call to `Run()` starts the computation again on the current thread. Exceptions propagate normally, captured mutable state is observed at run time, and C# does not enforce purity. It is also not stack-safe for very deep chains and provides no built-in cancellation, resource safety, retry, rollback, or async execution; in normal .NET code, asynchronous I/O is usually represented with `Task` or `Task<T>`.

## Conclusion

Returning `IO<T>` changes the function from "perform an effect and return `T`" to "construct a suspended computation that can later produce `T`." `FlatMap` composes dependent suspended operations, `Sequence` or `Traverse` chooses how a batch is executed, and `Run()` marks the boundary where execution begins.

Keep pure transformations as ordinary functions, return `IO<T>` from effectful helpers, compose those values without forcing them, and call `Run()` near the application boundary.

## Appendix

<details markdown="1">
<summary markdown="span">Open the appendix for optional query syntax support</summary>

### Optional C# query syntax support

The C# compiler translates query expressions into method calls such as `Select` and `SelectMany`. To use query syntax with `IO<T>`, add these methods:

```csharp
public IO<TResult> Select<TResult>(Func<T, TResult> selector)
{
    return Map(selector);
}

public IO<TResult> SelectMany<TNext, TResult>(
    Func<T, IO<TNext>> next,
    Func<T, TNext, TResult> project)
{
    return FlatMap(value =>
        next(value).Map(nextValue =>
            project(value, nextValue)));
}
```

With those methods in place, the main-body query-syntax example works as written.

</details>
