---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> represents an effectful computation as a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

A function is no longer "just a calculation" when calling it can invoke an HTTP API, read from or write to a database, write a file, print to the console, or observe time or randomness. Here, an *effect* means that kind of observable interaction. A *pure* function, by contrast, returns the same result for the same inputs and does not change anything outside itself.

The earlier parts used monadic types to delegate control flow. It is useful shorthand to say that `Map` or `FlatMap` decides "how the next function runs," but that shorthand needs some precision. The monad laws do not prescribe wall-clock scheduling, retries, parallelism, or the business reason for running an operation. A concrete `Map` or `FlatMap` implementation does determine whether the supplied function is invoked, how many times it is invoked, which branch invokes it, and sometimes whether invocation is immediate or deferred.

For a pure callback, the host still determines the surrounding structure and control flow, but each invocation's result is determined by its explicit input. When the callback performs an effect, the host's invocation rule also determines whether an API request, file write, or other operation occurs, and in what order or how often.

That is the tension explored here. The host abstraction may be behaving exactly as designed, while its invocation rule may still be the wrong execution policy for a particular effect. We want to preserve composition without performing the effect merely because some outer `List`, `Maybe`, or `Result` chose to invoke a callback.

The move is to return an `IO<T>` rather than a `T`. The callback then constructs a suspended computation instead of performing the operation. Other abstractions can compose that inert value, and a later combinator or application boundary can decide how to execute it.

As in the earlier parts, the types in this article are deliberately small teaching models. The goal is to make the common structure of `Pure`, `Map`, and `FlatMap` visible, and here to examine how that structure interacts with effects. They are not presented as replacements for .NET collections, LINQ, `Task`, or ordinary procedural code.

## When invocation becomes observable

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
```

```csharp
var quantities = new List<int> { 1, 2, 3 };

IEnumerable<decimal> totalsQuery = quantities
    .Select(quantity =>
        CalculateLineTotal(quantity, 19.99m, 0.13m));

List<decimal> firstTotals = totalsQuery.ToList();
List<decimal> secondTotals = totalsQuery.ToList();
```

[`Enumerable.Select`](https://learn.microsoft.com/en-us/dotnet/api/system.linq.enumerable.select) is deferred: constructing `totalsQuery` stores the selector, while enumeration invokes it. Each call to `ToList()` enumerates the query again. The calculation is repeated, but the same inputs still produce the same totals.

Now consider an effectful price lookup:

```csharp
public static decimal FetchCurrentPrice(
    IRemotePriceApi remotePriceApi,
    string productId)
{
    return remotePriceApi.GetCurrentPrice(productId);
}
```

```csharp
IEnumerable<decimal> pricesQuery = productIds
    .Select(productId =>
        FetchCurrentPrice(remotePriceApi, productId));

List<decimal> firstPrices = pricesQuery.ToList();   // Sends the requests.
List<decimal> secondPrices = pricesQuery.ToList();  // Sends them all again.
```

Its type still looks like an ordinary value-producing function:

```text
(IRemotePriceApi, string) -> decimal
```

Calling it, however, sends a request and observes another system. The same `IRemotePriceApi` reference and product ID do not describe that system's complete state. A later invocation may observe a newer price, consume more quota, fail transiently, or be throttled because of earlier requests. If one request throws during `ToList()`, later product IDs are not reached, but requests that already completed are not undone.

One useful mental model is that an effectful function also threads an implicit state of the world:

```text
(World, string) -> (decimal, World)
```

This is not a literal C# signature, and adding a mutable `World` parameter would not make the function pure. It is a way to expose the hidden dependency: each call observes or changes the world, and the next call occurs in the world left by the previous one. An object-oriented reader may recognize the same issue when calls through a service object depend on mutable or external state.

The effect is even clearer for a command such as sending an email or charging a card. Repeating a pure calculation may waste work; repeating a non-idempotent command can duplicate an irreversible action.

We can see different invocation rules with the other types from this series:

```csharp
var maybePrice =
    maybeProductId.Map(productId =>
        FetchCurrentPrice(remotePriceApi, productId));

var resultPrice =
    validatedProductId.Map(productId =>
        FetchCurrentPrice(remotePriceApi, productId));
```

Although these types all provide a map-shaped operation, `Map` does not imply one universal invocation strategy:

* `Enumerable.Select` invokes the selector for each source element requested during each enumeration. A consumer may stop early, and another enumeration invokes it again.
* The `Maybe<T>` from Part 1 invokes the function zero or one times, depending on whether a value exists.
* The `Result<TSuccess, TError>` from Part 2 invokes the function only on the success path.
* The `IO<T>` in this article invokes the function only when the resulting `IO` is run, and invokes it again on every subsequent run.

Those are properties of the concrete implementations, not one timing rule supplied by the word *monad*. For a pure function, the differences may not appear in its returned value. For an effectful function, they become part of the program's observable behavior.

The problem is therefore not that `IEnumerable`, `Maybe`, or `Result` has an invocation rule. Composition requires such rules. The problem is that a function returning a plain `decimal` hides the fact that invoking it also performs an external operation. Passing that function to `Map` silently makes the host abstraction's invocation semantics the execution policy for the effect.

## From an immediate result to a suspended computation

`FetchCurrentPrice` is still a function we want to compose. Instead of returning the result of a request immediately, it can return a suspended computation:

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

Calling `FetchCurrentPriceIO` does not send a request. It captures the work in an `IO<decimal>`.

```csharp
List<IO<decimal>> requests = productIds
    .Select(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId))
    .ToList();
```

`ToList()` still invokes the selector now, but the selector only constructs suspended computations. The collection's behavior has not changed; what the callback produces has changed.

The same move preserves the invocation rules of `Maybe` and `Result` without performing the request:

```csharp
var maybeRequest =
    maybeProductId.Map(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId));
// Maybe<IO<decimal>>

var validatedRequest =
    validatedProductId.Map(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId));
// Result<IO<decimal>, Error>
```

The outer type still decides whether a request recipe is constructed. It no longer performs the request as a consequence of that decision.

```text
List<IO<decimal>>  // Many suspended price requests.
IO<List<decimal>>  // One suspended program that will produce a list.
```

Returning `IO<T>` does not make arbitrary monads combine automatically. Mapping produces a `List<IO<decimal>>`, not an `IO<List<decimal>>`. A later `Sequence` or `Traverse` operation must exchange those layers, and that operation is where a concrete execution policy can be chosen.

The central operations are:

* `Delay` suspends a computation.
* `Pure` wraps an already available value.
* `Map` transforms the eventual value.
* `FlatMap` makes a later suspended computation depend on an earlier result.
* `Run` performs the composed computation.

> **`IO<T>` does not make an effect pure. It makes the decision to perform the effect separate and explicit.**

A `Func<T>` can already suspend work, and extension methods could give it `Map` and `FlatMap`. The `IO<T>` wrapper is useful because it gives effectful thunks a distinct type, names `Run()` as the execution boundary, and provides a focused composition API.

```text
Pure    : T -> IO<T>
Delay   : (() -> T) -> IO<T>
Map     : IO<T> -> (T -> TResult) -> IO<TResult>
FlatMap : IO<T> -> (T -> IO<TResult>) -> IO<TResult>
```

`Delay` is what makes this type useful for suspended effects; `Pure` and `FlatMap` provide its monadic composition.

This implementation stores an opaque delegate rather than an inspectable effect tree. A caller can wrap or compose the `IO` values it has been given, but `Run()` cannot discover internal operations or retroactively insert retries, cancellation, parallelism, cleanup, or rate limiting between them.

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

    public IO<TResult> Map<TResult>(Func<T, TResult> map)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();
            return map(value);
        });
    }

    public IO<TResult> FlatMap<TResult>(Func<T, IO<TResult>> next)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();
            IO<TResult> nextOperation = next(value);

            return nextOperation.Run();
        });
    }

    public T Run()
    {
        return operation();
    }
}
```

Although `Map` and `FlatMap` contain calls to `Run()`, those calls are inside the delegate stored by the newly returned `IO`. Calling `Map` or `FlatMap` therefore constructs another suspended computation. The inner calls occur only when that outer computation is run.

`Pure` and `Delay` are not interchangeable. `Pure` wraps a value that has already been produced; it does not delay evaluation of the expression passed to it:

```csharp
IO<decimal> alreadyFetched = IO<decimal>.Pure(
    FetchCurrentPrice(remotePriceApi, productId)); // Request happens first.

IO<decimal> deferredFetch = IO<decimal>.Delay(
    () => FetchCurrentPrice(remotePriceApi, productId)); // Request happens on Run().
```

For an effect whose only interesting result is successful completion, use a one-value `Unit` type:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}
```

This `Unit` is roughly `void` as a value. It is not the value-lifting operation that Part 1 called `Unit`; that operation is named `Pure` here.

By convention, `Map` is used for pure transformations that return plain values. `FlatMap` is used when the next step returns another `IO`. C# cannot enforce that a function passed to `Map` is pure, or that a helper returning `IO<T>` performs no work before returning it.

## Compose first, run later

Suppose `ParseOrder` returns an order with `ProductId`, `Quantity`, and `TaxRate`. We want to read an order from disk, fetch the current product price, calculate the total, render a report, and write that report to disk:

```csharp
public static IO<string> ReadAllTextIO(string path)
{
    return IO<string>.Delay(() => File.ReadAllText(path));
}

public static IO<Unit> WriteAllTextIO(string path, string contents)
{
    return IO<Unit>.Delay(() =>
    {
        File.WriteAllText(path, contents);
        return Unit.Value;
    });
}
```

```csharp
public static IO<Unit> LoadOrderAndWriteReport(
    IRemotePriceApi remotePriceApi,
    string orderPath,
    string reportPath)
{
    return ReadAllTextIO(orderPath)
        .Map(ParseOrder)
        .FlatMap(order =>
            FetchCurrentPriceIO(remotePriceApi, order.ProductId)
                .Map(unitPrice =>
                {
                    decimal total = CalculateLineTotal(
                        order.Quantity,
                        unitPrice,
                        order.TaxRate);

                    return RenderReport(order, unitPrice, total);
                }))
        .FlatMap(report =>
            WriteAllTextIO(reportPath, report));
}
```

`Map(ParseOrder)` keeps parsing inside the suspended computation. The inner `Map` calculates the total and renders the report after the price has been fetched. Each `FlatMap` adds an effectful step that depends on an earlier result. The return value is still an `IO<Unit>`, so the whole pipeline remains deferred.

If you prefer C# query syntax, the appendix shows the equivalent `Select` and `SelectMany` support and the same pipeline written with `from` and `let`.

## The execution boundary

Constructing the program performs none of the wrapped effects:

```csharp
IO<Unit> program = LoadOrderAndWriteReport(
    remotePriceApi,
    "order.json",
    "report.txt");
```

At that point, the caller holds one larger suspended computation.

Calling `Run()` crosses the execution boundary:

```csharp
program.Run();
```

That call attempts the file read, price request, total calculation, report rendering, and file write in dependency order. A second `Run()` repeats the entire sequence.

Pushing `Run()` outward does not guarantee exactly-once execution. It makes execution visible at a small number of boundary call sites, where a caller can decide whether and under what surrounding policy to run the program. Preventing duplicate emails, charges, or other commands requires domain or infrastructure support beyond this wrapper.

Application code should therefore avoid forcing an `IO` inside an inner helper. Once a helper calls `Run()` and returns an ordinary value, its caller can no longer include that operation in a larger deferred program. Combinator implementations such as `Map`, `FlatMap`, and the traversal below use `Run()` internally only inside another suspended delegate, preserving the outer boundary.

## Traversal is an execution policy

The earlier example produced a list of suspended requests:

```csharp
List<IO<decimal>> requests = productIds
    .Select(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId))
    .ToList();
```

A `List<IO<decimal>>` says which operations exist, but it does not by itself say how to run the batch. `SequenceSequential` can turn those operations into one suspended program with a specific policy:

```csharp
IO<List<decimal>> program = requests.SequenceSequential();
```

Here is one small implementation:

```csharp
public static class IOExtensions
{
    public static IO<List<TResult>> TraverseSequential<TSource, TResult>(
        this IReadOnlyList<TSource> source,
        Func<TSource, IO<TResult>> action)
    {
        return IO<List<TResult>>.Delay(() =>
        {
            var results = new List<TResult>(source.Count);

            foreach (TSource item in source)
            {
                IO<TResult> operation = action(item);
                TResult result = operation.Run();
                results.Add(result);
            }

            return results;
        });
    }

    public static IO<List<T>> SequenceSequential<T>(
        this IReadOnlyList<IO<T>> source)
    {
        return source.TraverseSequential(
            static operation => operation);
    }
}
```

`SequenceSequential` still does not start the requests. Work begins only when the outer program is run:

```csharp
List<decimal> prices = program.Run();
```

This traversal contributes the following policy:

* source traversal and `action` invocation are deferred until `Run()`;
* items are handled in list order;
* one `IO` completes before the next begins;
* results are stored in the same order;
* an exception stops later items but does not undo effects already performed;
* every outer `Run()` traverses the source and executes the operations again.

The nested `Run()` calls are implementation details of the suspended traversal. They occur only after the outer `Run()` begins.

A different traversal could reverse the order, pause between requests, continue after selected failures, or apply a retry policy. An asynchronous version could also bound concurrency. Those policies are not automatically safe: retrying a read may be acceptable, while retrying a non-idempotent command may duplicate it. `IO<T>` makes the operation available to policy combinators; it cannot determine the correct domain policy on its own.

## Runtime semantics and limitations

This `IO<T>` is intentionally small: it is synchronous, cold, non-memoized, and opaque. Nothing happens until `Run()`. `Run()` executes on the current thread, every call starts the computation again, exceptions propagate normally, and captured mutable state is observed at run time.

C# does not enforce purity or effect discipline. The type cannot prevent a supposedly pure `Map` function from performing I/O, or prevent an `IO`-returning helper from doing work before it constructs the `IO`. The implementation is not stack-safe for very deep composition chains and provides no built-in cancellation, asynchronous execution, resource safety, retry, memoization, rollback, or exactly-once guarantee.

Production .NET I/O is commonly asynchronous and represented by `Task` or `Task<T>`, but those types have different execution semantics. Under the [Task-based Asynchronous Pattern](https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/task-based-asynchronous-pattern-tap), methods return active tasks rather than cold tasks waiting for an explicit `Run()`. A cold asynchronous analogue of this teaching type would defer creation of the task, for example behind a `Func<CancellationToken, Task<T>>`, and would need additional design for cancellation and resource management.

## Conclusion

Monadic composition delegates part of the control flow to the host type. With a pure callback, each invocation's result is still determined by its input. With an effectful callback, the host's invocation rule also controls an observable operation.

Returning `IO<T>` changes the callback from "perform an effect and return `T`" to "construct a suspended computation that can later produce `T`." `FlatMap` composes dependent suspended operations, `Sequence` or `Traverse` chooses how a batch is executed, and `Run()` marks the boundary where execution begins.

This does not make effects pure, safe to retry, or exactly once. It makes their construction, composition, and execution boundary explicit.

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
