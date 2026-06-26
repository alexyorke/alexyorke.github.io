---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> represents an effectful computation as a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

`IO<T>` lets you compose effectful computations by representing them as deferred computations that can be run later.

Calling a function may do more than calculate a value: it may invoke an API, query a database, send an email, write a file, or observe time or randomness. These observable interactions are called effects. A pure function depends only on its declared inputs: the same inputs produce the same result, and evaluating it does not read from or modify the outside world.

Pure functions are easier to compose because you can recompute, delay, repeat, or discard their results without changing anything outside the calculation. Effectful functions are different. Order, timing, delays, retries, and repetition can matter, and some effects cannot simply be undone. A request may need rate limiting, a retry may affect later work, and an email should not be sent twice by accident.

That is where the trouble starts. `List.Map`, `Maybe.Map`, and `Result.Map` already decide when the supplied function runs. That is fine for pure code, but if the function performs effects directly, those invocation rules become the execution policy for the effect. Returning `IO<T>` changes the arrangement: the function now returns a suspended effectful computation instead of performing the effect immediately, so the surrounding program can compose those computations first and decide later how the larger whole should run.

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

In Part 1, `List.Map` visits each element now and builds a new list. Because `CalculateLineTotal` is pure, that execution policy does not change what each input means. The same inputs still determine the same result, discarding the resulting list leaves nothing else changed, and replacing `CalculateLineTotal(quantity, 19.99m, 0.13m)` with its resulting `decimal` does not change the program's meaning.

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

`List.Map` is still just applying the supplied function according to the list's traversal policy. The difference is that invoking `FetchCurrentPrice` now sends a request. If traversal is eager, the requests happen eagerly, and if one request throws, later product IDs are not reached. The method still looks like an ordinary function returning `decimal`, but calling it sends a request and observes external state not fully described by its arguments. A later call may observe a new price, consume quota, fail transiently, or be throttled, so replacing `FetchCurrentPrice(remotePriceApi, productId)` with a returned `decimal` is no longer harmless in the same way. Repeating, reordering, or stopping invocation partway through can change what happens, even when later steps do not explicitly take earlier results as inputs.

Although these types all provide a map-shaped operation, `Map` does not imply one universal execution strategy. `List.Map` invokes the function immediately for each element in list order, `Maybe<T>.Map` invokes it zero or one time, `Result<TSuccess, TError>.Map` invokes it only on the success path, and the `IO<T>.Map` in this article defers it until the resulting `IO` is run. `Map` is the functor operation; `Pure` and `FlatMap` provide the monadic structure, but neither set of laws requires eager or deferred evaluation. The implementation and host language determine when and how often the function runs. For pure functions, different invocation policies usually change work rather than meaning; with effectful functions, they change which effects occur and what remains completed after a failure.

`IO<T>` addresses this by representing the operation as a suspended computation that is itself a pure value, so the program can compose it before any effect happens and decide later how it runs.

## From an immediate result to a suspended computation

The effectful price lookup is still a function we want to compose with other steps. The difficulty is that a function returning `decimal` can produce that value only after sending the request. By the time a larger program receives the result, the effect has already happened, so the surrounding code cannot still choose how to combine, traverse, or delay that work. Returning `IO<decimal>` keeps the work suspended long enough to compose first and run later.

To compose the operation before performing it, the function can instead return a suspended computation:

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

Calling `FetchCurrentPriceIO` sends no request. It returns a pure `IO<decimal>` value representing deferred work. The surrounding program can keep assigning, passing around, and composing that value before any request happens.

Here, `Delay` means **defer evaluation**. It does not pause a thread, wait for a duration, or behave like `Task.Delay`.

```csharp
IO<decimal> request =
    FetchCurrentPriceIO(remotePriceApi, productId);
// No request yet.

decimal price = request.Run();
// The request is sent here.
```

In this teaching model, each call to `Run()` performs the computation again.

`Run()` makes the execution boundary explicit. The point of `IO<T>` is not that we can immediately call `Run()`; doing so would merely reproduce the original function call. The point is that returning `IO<T>` keeps the effect as a composable value until the larger program decides to run it.

The following examples use C#'s `from` and `select` syntax over `IO<T>`. Assume that `Select` and `SelectMany` delegate to `Map` and `FlatMap`. No `IEnumerable<T>` or enumeration is involved; the compiler translates this syntax into method calls on `IO<T>`.

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

Suspension does not itself choose an execution policy. It keeps the effect unperformed while the program is assembled. Here, `FlatMap` establishes sequential order, while other combinators can later express policies such as retries, pacing, or collection traversal before the final program is run.

> **`IO<T>` does not remove the effect or decide how it should run. It makes the effectful computation explicit and keeps it suspended while those decisions are composed.**

The teaching model has five central operations:

```text
Pure    : T -> IO<T>
Delay   : (() -> T) -> IO<T>
Map     : IO<T> -> (T -> TResult) -> IO<TResult>
FlatMap : IO<T> -> (T -> IO<TResult>) -> IO<TResult>
Run     : IO<T> -> T
```

`Pure` wraps an already available value, `Delay` suspends a computation, `Map` transforms an eventual result while preserving suspension, `FlatMap` composes a later computation that depends on an earlier result, and `Run` performs the composed computation. `Pure` receives a value that is already available; `Delay` receives a computation that will produce one later. `Delay` can suspend pure work, but here its purpose is to postpone an effect.

Passing an effectful call to `Pure` would be too late:

```csharp
IO<decimal> notSuspended =
    IO<decimal>.Pure(
        FetchCurrentPrice(remotePriceApi, productId));
// FetchCurrentPrice runs before Pure is called.
```

A `Func<T>` can also postpone work. The difference is the contract expressed by the type: a bare `Func<T>` says only that some code can be invoked later, while `IO<T>` specifically represents a potentially effectful computation, preserves suspension through its composition operations, and names `Run()` as the execution boundary. Defining the same conventions directly for `Func<T>` would effectively create an unnamed `IO`-like abstraction.

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

`IO<T>` stores a parameterless operation and provides ways to suspend, compose, and run it. `Pure` receives an already available value; `Delay` receives a computation and stores it without invoking it.

`Map` and `FlatMap` call `Run()` only inside the delegate stored by the returned `IO`, so calling either method builds another suspended computation. The inner calls occur only when that returned `IO` runs.

In this model, use `Map` for a pure transformation that returns a plain value. Use `FlatMap` when the next step returns another `IO`; mapping such a function directly would produce `IO<IO<TResult>>`. `FlatMap` combines those nested computations into one `IO<TResult>` while preserving suspension, but C# cannot enforce those conventions.

## Compose first, run later

Suppose `ParseOrder` returns an order with `ProductId`, `Quantity`, and `TaxRate`. We want to read an order, fetch its current price, calculate the total, render a report, and write it to disk. Writing a file has no meaningful result beyond successful completion, so the wrapper returns an `IO<Unit>`:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}
```

`Unit` is roughly `void` represented as a value. The value-lifting operation is named `Pure` here.

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

The following uses C# query syntax over `IO<T>`, not `IEnumerable<T>`. Assume `Select` and `SelectMany` delegate to `Map` and `FlatMap`. The syntax assembles a suspended dependency chain; it does not enumerate a sequence.

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

The result remains a suspended `IO<Unit>`. Constructing it performs none of the wrapped effects, and when it eventually runs it reads before parsing, fetches the price after obtaining the product ID, and writes only after the report exists. Conceptually, the `let` clauses perform pure transformations through `Map`, while each dependent effectful step uses `FlatMap`.

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

This `IO<T>` is intentionally small: it is synchronous, cold, non-memoized, and opaque. Nothing happens until `Run()`. `Run()` executes on the current thread, every call starts the computation again, exceptions propagate normally, and captured mutable state is observed at run time.

C# does not enforce purity or effect discipline. The type cannot prevent a supposedly pure `Map` function from performing I/O, or prevent an `IO`-returning helper from doing work before it constructs the `IO`. The implementation is not stack-safe for very deep composition chains and provides no built-in cancellation, asynchronous execution, resource safety, retry, memoization, rollback, or exactly-once guarantee.

Production .NET I/O is commonly asynchronous and represented by `Task` or `Task<T>`, but those types have different execution semantics. Under the [Task-based Asynchronous Pattern](https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/task-based-asynchronous-pattern-tap), methods return active tasks rather than cold tasks waiting for an explicit `Run()`. A cold asynchronous analogue of this teaching type would defer creation of the task, for example behind a `Func<CancellationToken, Task<T>>`, and would need additional design for cancellation and resource management.

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

With those methods in place, the same program can be written this way:

```csharp
public static IO<Unit> LoadOrderAndWriteReportQuery(
    IRemotePriceApi remotePriceApi,
    string orderPath,
    string reportPath)
{
    return
        from json in ReadAllTextIO(orderPath)
        let order = ParseOrder(json)
        from unitPrice in FetchCurrentPriceIO(
            remotePriceApi,
            order.ProductId)
        let total = CalculateLineTotal(
            order.Quantity,
            unitPrice,
            order.TaxRate)
        let report = RenderReport(order, unitPrice, total)
        from result in WriteAllTextIO(reportPath, report)
        select result;
}
```

</details>
