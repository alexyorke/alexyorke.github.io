---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> represents an effectful computation as a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

Calling a function may do more than calculate a value: it may invoke an API, query a database, send an email, write a file, or observe time or randomness. These observable interactions are effects. A pure function, by contrast, returns the same result for the same inputs and changes nothing outside itself.

Pure functions compose smoothly because they can be recomputed, delayed, repeated, or discarded without changing their meaning. Effectful functions cannot always be treated this way. Order, timing, repetition, delays, and retries may matter, and some effects cannot be undone. A request may require rate limiting, a retry may affect later work, and an email should not be sent twice by accident. Even if a result is discarded, the world may already have changed.

This creates a conflict: `List.Map`, `Maybe.Map`, and `Result.Map` each impose their own rule for invoking the supplied function. That works for pure code but may be the wrong execution policy for effects, and we do not want a special list, maybe, or result type for every possible policy.

`IO<T>` separates composition from execution. Instead of performing an effect immediately, a function returns a suspended computation. Other abstractions can compose it, while explicit combinators determine how the work runs before the final program is executed at the application boundary.

As before, these small teaching models show how `Pure`, `Map`, and `FlatMap` interact with effects; they are not replacements for .NET collections, LINQ, `Task`, or ordinary procedural code.

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

`Enumerable.Select` is deferred. Calling it creates a query; `CalculateLineTotal` runs only when the query is enumerated, such as by `foreach` or `ToList()`. Each `ToList()` enumerates it again. ([Microsoft Learn][1])

Because the function is pure, this repeats work without changing anything outside the calculation. The same inputs produce the same totals, and discarded results leave no trace. The caller may enumerate quickly or slowly, stop early, or enumerate again. Those choices change when and how much work occurs, not the value produced for any evaluated element.

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
// No requests yet.

List<decimal> firstPrices = pricesQuery.ToList();   // Sends the requests.
List<decimal> secondPrices = pricesQuery.ToList();  // Sends them again.
```

Creating `pricesQuery` also sends no requests. Enumeration performs the external work.

The LINQ mechanics are unchanged; only the function passed to `Select` differs. With the pure function, enumeration controls when calculation occurs. With the effectful function, the same rules control external work.

The caller may consume one value or all of them, pause between values, add more deferred operators, or enumerate again. Those choices determine which requests are sent, when they are sent, and how often.

`IEnumerable<decimal>` represents a sequence of values, not a contract for rate limits, delays, retries, partial failures, or repeated requests. A custom iterator could enforce a policy, but the type alone would not communicate it.

The function’s signature still looks ordinary:

```text
(IRemotePriceApi, string) -> decimal
```

Calling it, however, sends a request and observes external state not fully described by its arguments. A later call may observe a new price, consume quota, fail transiently, or be throttled. If one request throws, later product IDs are not reached, while completed requests remain completed.

A useful mental model exposes the hidden dependency:

```text
(World, string) -> (decimal, World)
```

This is a model, not a literal C# signature. `World` represents the relevant external state: each call observes or changes it, so a later call may occur in a different world.

Repeating a pure calculation may waste work. Repeating a command such as sending an email or charging a card may duplicate an action that cannot simply be undone.

The earlier `Maybe` and `Result` implementations map eagerly, while `Enumerable.Select` is deferred. Other types and languages make different choices. `Map` is the functor operation; `Pure` and `FlatMap` provide the monadic structure. Neither set of laws requires eager or deferred evaluation. The implementation and host language determine when and how often the function runs. ([Scala Documentation][2])

For pure functions, these choices usually affect work rather than meaning. They may change performance or termination, but whenever a calculation completes, the same inputs produce the same value without changing anything outside it.

With an effectful function, the evaluation strategy becomes observable:

* `Enumerable.Select` invokes the function as elements are requested during each enumeration. Stopping early or enumerating again changes how often it runs.
* The earlier `Maybe<T>.Map` invokes it immediately when a value exists and not at all when it does not.
* The earlier `Result<TSuccess, TError>.Map` invokes it immediately on success and not on error.
* The `IO<T>.Map` in this article defers it until the resulting `IO` is run and invokes it again on each run.

These rules determine whether, when, how often, and for which values an effect occurs. They can determine how many requests are sent, whether rate limits are exceeded, and what remains completed after a failure.

`Select` is behaving as designed. The problem is that a function returning a plain `decimal` hides the external operation, so passing it to `Select` or `Map` silently turns the abstraction’s invocation rules into the effect’s execution policy.

`IO<T>` addresses this by representing the operation as a suspended value. The program can compose it first, then use explicit combinators to decide how and when it runs. ([Haskell][3])

## From an immediate result to a suspended computation

The effectful price lookup is still a function we want to compose. The problem is that a function returning `decimal` can produce that value only after sending the request. By the time the caller receives the result, the effect has already occurred.

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

Calling `FetchCurrentPriceIO` sends no request. It constructs an `IO<decimal>` containing the work to perform later.

Here, `Delay` means **defer evaluation**. It does not pause a thread, wait for a duration, or behave like `Task.Delay`.

```csharp
IO<decimal> request =
    FetchCurrentPriceIO(remotePriceApi, productId);
// No request yet.

decimal price = request.Run();
// The request is sent here.
```

In this teaching model, each call to `Run()` performs the computation again.

> **Teaching note:** `Run()` is called directly here to make the execution boundary visible. In a larger effect system, the application normally constructs one final `IO` and hands it to a runtime or interpreter at the application boundary.

Calling `Run()` immediately would merely reproduce the original function call. Suspension becomes useful when the computation is composed before it is run.

The following examples use C#’s `from` and `select` syntax over `IO<T>`. Assume that `Select` and `SelectMany` delegate to `Map` and `FlatMap`. No `IEnumerable<T>` or enumeration is involved; the compiler translates this syntax into method calls on `IO<T>`. ([Microsoft Learn][1])

```csharp
IO<decimal> totalProgram =
    from unitPrice in
        FetchCurrentPriceIO(remotePriceApi, productId)
    select
        CalculateLineTotal(quantity, unitPrice, taxRate);
// Still no request.
```

The computation describes what to do with the eventual price without obtaining it yet. Constructing `totalProgram` sends no request. Running it fetches the price and then calculates the total:

```csharp
decimal total = totalProgram.Run();
```

Several effectful steps can be composed in the same way:

```csharp
IO<decimal> basketTotalProgram =
    from firstPrice in
        FetchCurrentPriceIO(remotePriceApi, firstProductId)
    from secondPrice in
        FetchCurrentPriceIO(remotePriceApi, secondProductId)
    select
        firstPrice + secondPrice;
// Still no requests.
```

The steps are now encoded in `basketTotalProgram`: fetch the first price, fetch the second, and add them. Constructing the program performs none of those steps. `Run()` executes them in that order.

```csharp
decimal basketTotal = basketTotalProgram.Run();
```

Suspension does not itself choose an execution policy. It keeps the effect unperformed while the program is assembled. Here, `FlatMap` establishes sequential order. Other combinators can later express policies such as retries, pacing, or collection traversal before the final program is run.

> **`IO<T>` does not remove the effect or decide how it should run. It makes the effectful computation explicit and keeps it suspended while those decisions are composed.**

The same approach works with the eager `Maybe` and `Result` implementations:

```csharp
Maybe<IO<decimal>> maybeRequest =
    from productId in maybeProductId
    select FetchCurrentPriceIO(remotePriceApi, productId);

Result<IO<decimal>, Error> validatedRequest =
    from productId in validatedProductId
    select FetchCurrentPriceIO(remotePriceApi, productId);
```

When `maybeProductId` contains a value, its `Select` immediately constructs an `IO<decimal>`; when it is empty, no `IO` is constructed. Likewise, `validatedProductId` constructs an `IO` only on the success path. In every case, constructing the outer value sends no request.

The teaching model has five central operations:

```text
Pure    : T -> IO<T>
Delay   : (() -> T) -> IO<T>
Map     : IO<T> -> (T -> TResult) -> IO<TResult>
FlatMap : IO<T> -> (T -> IO<TResult>) -> IO<TResult>
Run     : IO<T> -> T
```

* `Pure` wraps an already available value.
* `Delay` suspends a computation.
* `Map` transforms its eventual result while preserving suspension.
* `FlatMap` composes a later computation that depends on an earlier result.
* `Run` performs the composed computation.

`Pure` is the operation sometimes called `return` or the monadic unit. This article uses `Pure` because `Unit` already names the type used when a computation has no meaningful result, while `return` has an unrelated control-flow meaning in C#. `Pure` and `FlatMap` provide the monadic structure. ([Typelevel][2])

The distinction between `Pure` and `Delay` is important:

```csharp
decimal cachedPrice = 19.99m;

IO<decimal> availablePrice =
    IO<decimal>.Pure(cachedPrice);

IO<decimal> currentPrice =
    IO<decimal>.Delay(
        () => FetchCurrentPrice(remotePriceApi, productId));
```

`Pure` receives a value that is already available. `Delay` receives a computation that will produce one later. `Delay` can suspend pure work, but here its purpose is to postpone an effect.

Passing an effectful call to `Pure` would be too late:

```csharp
IO<decimal> notSuspended =
    IO<decimal>.Pure(
        FetchCurrentPrice(remotePriceApi, productId));
// FetchCurrentPrice runs before Pure is called.
```

A `Func<T>` can also postpone work, and suitable extension methods could give it `Map`, `FlatMap`, and even collection-combining operations. `IO<T>` is not valuable because delegates are incapable of composition.

The difference is the contract expressed by the type. A bare `Func<T>` says only that some code can be invoked later; it may represent a pure calculation or an external effect. `IO<T>` specifically represents a potentially effectful computation, preserves suspension through its composition operations, and names `Run()` as the execution boundary. Defining the same conventions directly for `Func<T>` would effectively create an unnamed `IO`-like abstraction.

That common structure also lets operations such as `Sequence` and `Traverse` combine many suspended computations uniformly. A later section will use them to make the traversal itself part of one suspended program:

```text
List<IO<T>> -> IO<List<T>>
```

Instead of asking a caller to loop through the list and call `Run()` on each item, the program can first describe how the computations are combined and then expose one final execution boundary. `Sequence` combines existing effectful values, while `Traverse` performs the mapping and combination together. ([Typelevel][3])


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

`IO<T>` stores a parameterless operation and provides ways to suspend, compose, and run it.

`Map` and `FlatMap` call `Run()` only inside the delegate stored by the returned `IO`. Calling either method therefore builds another suspended computation; the inner calls occur only when that returned `IO` runs.

`Pure` receives an already available value. `Delay` receives a computation and stores it without invoking it.

In this model, use `Map` for a pure transformation that returns a plain value. Use `FlatMap` when the next step returns another `IO`; mapping such a function directly would produce `IO<IO<TResult>>`. `FlatMap` combines those nested computations into one `IO<TResult>` while preserving suspension.

C# cannot enforce that a function passed to `Map` is pure or that a helper returning `IO<T>` performs no work before returning. Those remain conventions of the model.

## Compose first, run later

Suppose `ParseOrder` returns an order with `ProductId`, `Quantity`, and `TaxRate`. We want to read an order, fetch its current price, calculate the total, render a report, and write it to disk.

Writing a file has no meaningful result beyond successful completion, so the wrapper returns an `IO<Unit>`:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}
```

`Unit` is roughly `void` represented as a value. It is not the value-lifting operation that Part 1 called `Unit`; that operation is named `Pure` here.

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

The program reads the file before parsing it, fetches the price after obtaining the product ID, and writes only after the report exists. Conceptually, the `let` clauses perform pure transformations through `Map`, while each dependent effectful step uses `FlatMap`.

The result remains a suspended `IO<Unit>`. Constructing it performs none of the wrapped effects.

## Traversal makes the batch policy explicit

`FlatMap` orders one dependent step after another. A collection raises a different question: how should the same effectful action be applied to many inputs?

A sequential traversal answers that explicitly:

```csharp
IO<List<decimal>> program =
    productIds.TraverseSequential(productId =>
        FetchCurrentPriceIO(
            remotePriceApi,
            productId));
// No requests yet.
```

`TraverseSequential` returns one suspended program that visits the product IDs in order, runs one request at a time, and collects the results.

The two related operations begin with different inputs:

```text
TraverseSequential :
    IReadOnlyList<TSource>
    -> (TSource -> IO<TResult>)
    -> IO<List<TResult>>

SequenceSequential :
    IReadOnlyList<IO<T>>
    -> IO<List<T>>
```

`TraverseSequential` constructs and combines computations. `SequenceSequential` combines `IO` values that already exist. Both produce one suspended computation for the entire batch.

```csharp
public static class IOExtensions
{
    public static IO<List<TResult>>
        TraverseSequential<TSource, TResult>(
            this IReadOnlyList<TSource> source,
            Func<TSource, IO<TResult>> action)
    {
        return IO<List<TResult>>.Delay(() =>
        {
            var results =
                new List<TResult>(source.Count);

            foreach (TSource item in source)
            {
                IO<TResult> operation = action(item);
                TResult result = operation.Run();

                results.Add(result);
            }

            return results;
        });
    }

    public static IO<List<T>>
        SequenceSequential<T>(
            this IReadOnlyList<IO<T>> source)
    {
        return source.TraverseSequential(
            static operation => operation);
    }
}
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

`IO<T>` cannot choose the correct policy. It makes effectful computations available as values so a combinator can encode that policy before execution.


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
