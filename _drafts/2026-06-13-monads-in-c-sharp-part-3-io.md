---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> represents an effectful computation as a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

A function is no longer "just a calculation" if calling it can call an HTTP API, read from or write to a database, write a file, print to the console, or observe time or randomness. Here, *effect* just means that kind of observable interaction. A *pure* function, by contrast, returns the same result for the same inputs and does not change anything outside itself.

As in the earlier parts, the types in this article are deliberately small teaching models. The goal is to make the common structure of `Pure`, `Map`, and `FlatMap` visible, and here to examine how that structure interacts with effects. They are not presented as replacements for .NET collections, LINQ, `Task`, or ordinary procedural code.

As in Part 1, I will write the list examples with `Map` in C#-ish pseudocode. The point is to keep the shared monadic shape visible. In that Part 1 model, the list is eager and materialized: `Map` traverses now, once per element, in list order.

## When timing matters

As a quick refresher, consider a pure price calculation:

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

List<decimal> totals =
    quantities.Map(quantity =>
        CalculateLineTotal(quantity, 19.99m, 0.13m));
```

Here the list's eagerness is usually unremarkable. `Map` runs now, but the same inputs still determine the same totals.

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
List<decimal> prices =
    productIds.Map(productId =>
        FetchCurrentPrice(remotePriceApi, productId));
```

Its type still looks like an ordinary value-producing function:

```text
(IRemotePriceApi, string) -> decimal
```

But calling it does more than calculate a value. It sends a request and observes the current state of another system. Because the Part 1 list traverses immediately, those requests happen now, in list order. If one request throws, later product IDs are never reached.

The same `IRemotePriceApi` reference and product ID do not describe the remote service's complete state. A later invocation may observe a newer price, consume additional quota, fail transiently, or be throttled because of earlier requests.

We can see the same shape with `Maybe` and `Result`:

```csharp
var maybePrice =
    maybeProductId.Map(productId =>
        FetchCurrentPrice(remotePriceApi, productId));

var resultPrice =
    validatedProductId.Map(productId =>
        FetchCurrentPrice(remotePriceApi, productId));
```

Although these types all provide a map-shaped operation, `Map` does not imply one universal execution strategy. Each type determines whether, when, and how often the supplied function is invoked.

* In the Part 1 list, `Map` runs once per element, immediately, in list order.
* In `Maybe<T>`, `Map` runs zero or one times.
* In `Result<T>`, `Map` runs only on the success path.
* In `IO<T>`, `Map` runs only when the resulting `IO` is run.

For pure functions, those differences may be easy to ignore. For effectful functions, they become part of the program's observable behavior.

<details markdown="1">
<summary markdown="span">A related example with deferred LINQ</summary>

The list from Part 1 maps eagerly. LINQ's `Enumerable.Select` has a different policy: it returns a deferred `IEnumerable<T>` whose selector runs during enumeration.

```csharp
IEnumerable<decimal> pricesQuery = productIds
    .Select(productId => FetchCurrentPrice(remotePriceApi, productId));

// No requests yet.

List<decimal> firstPrices = pricesQuery.ToList();   // Requests happen.
List<decimal> secondPrices = pricesQuery.ToList();  // Requests happen again.
```

That is not the execution behavior of the list from Part 1. It is another example of a host abstraction imposing its own invocation policy.

</details>

## From an immediate result to a suspended computation

`FetchCurrentPrice` is still a function we want to compose with other steps. The problem is not that the Part 1 list is behaving incorrectly. It is still invoking its function now, once per element, in list order. The problem is that invoking this particular function performs the remote request immediately.

One way to do that is to change what the function returns:

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

```csharp
List<IO<decimal>> requests =
    productIds.Map(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId));
```

The list still traverses now. The difference is that invoking `FetchCurrentPriceIO` does not send the request; it constructs an `IO<decimal>`.

```text
List<string>
    -> Map(string -> IO<decimal>)
    -> List<IO<decimal>>
```

You have not changed the list's execution policy. You have changed what the function produces. The list is still eager, but it now produces suspended computations that can be combined before any wrapped work is performed.

That separation is the central idea:

* `Delay` suspends a computation.
* `Map` transforms its eventual value.
* `FlatMap` makes a later suspended computation depend on an earlier result.
* `Run` performs the composed computation.

> **`IO<T>` does not make an effect pure. It makes the decision to perform the effect separate and explicit.**

A `Func<T>` can already suspend work, and it could also be given `Map` and `FlatMap` extension methods. The `IO<T>` wrapper is useful because it gives effectful thunks a distinct type, names `Run()` as the execution boundary, and provides a focused API for composing them. You can hard-code delays or retries inside the effectful function, but then every caller receives that policy. Returning `IO<T>` instead gives callers a value that explicit policy combinators can wrap or traverse before execution. This small `IO<T>` does not make those policies automatic; the sequential traversal below is one concrete example.

```text
Pure    : T -> IO<T>
FlatMap : IO<T> -> (T -> IO<TResult>) -> IO<TResult>
```

This implementation stores an opaque delegate, not an inspectable effect tree. `Run()` can execute it, but it cannot discover individual operations or retroactively add retries, cancellation, parallelism, cleanup, or resource management.

Calling `FlatMap` builds another `IO`; it does not run the first operation or the next deferred step. Those things happen only when the resulting computation is run.

This article implements that model as a small synchronous wrapper around `Func<T>`. The wrapper gives the thunk a meaningful type, an explicit execution boundary, and composition operations.

## A small `IO<T>`

To support this style of composition, the type needs two basic operations: one to wrap an existing value as `IO<T>`, and one to chain functions that themselves return `IO<...>`. Here those operations are named `Pure` and `FlatMap`. `Delay` serves a separate purpose: it suspends a computation.

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

Although `Map` and `FlatMap` contain calls to `Run()`, those calls are inside the delegate stored by the newly returned `IO`. Calling `Map` or `FlatMap` therefore constructs another suspended computation; the inner calls occur only when that outer computation is run.

`Pure` wraps an existing value. `Delay` suspends a computation.

For an effect whose only interesting result is that it completed, use a one-value `Unit` type:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}
```

This `Unit` is roughly `void` as a value. It is not the value-lifting operation that Part 1 called `Unit`; that operation is named `Pure` here.

By convention, `Map` is used for pure transformations that return plain values. `FlatMap` is used when the next step returns another `IO`. C# cannot enforce that a function passed to `Map` is pure.

## Compose first, run later

Suppose `ParseOrder` returns an order with `ProductId`, `Quantity`, and `TaxRate`, and we want to read an order from disk, fetch the current product price, calculate the total, render a report, and write that report to disk:

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
                    decimal total =
                        CalculateLineTotal(order.Quantity, unitPrice, order.TaxRate);

                    return RenderReport(order, unitPrice, total);
                }))
        .FlatMap(report =>
            WriteAllTextIO(reportPath, report));
}
```

`Map(ParseOrder)` keeps the pure parsing step inside the suspended computation. The inner `Map` turns the fetched price into a rendered report without leaving `IO`. Each `FlatMap` adds the next effectful step, and the whole pipeline remains deferred.

If you prefer C# query syntax, the appendix shows the equivalent `Select` / `SelectMany` support and the same pipeline written with `from` and `let`.

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

That call attempts the file read, price request, total calculation, report rendering, and file write in dependency order. A second `Run()` re-reads the order, re-fetches the price, re-calculates the total, re-renders the report, and rewrites the file.

In this style, you usually push calls to `Run()` outward toward the application boundary, while `IO<T>` values can remain in the call graph. Control is lost when an inner helper calls `Run()` prematurely and turns part of the suspended computation into an already performed effect. This toy `Run()` only executes the stored delegate; it cannot retroactively add policy.

## Runtime semantics and limitations

This `IO<T>` is intentionally small: it is synchronous, cold, non-memoized, and opaque. Nothing happens until `Run()`, `Run()` executes on the current thread, every `Run()` starts the computation again, exceptions propagate normally, and closures over mutable state are observed at run time. C# does not enforce purity here. It is not stack-safe for very deep composition chains and provides no built-in cancellation, resource safety, retry, or rollback mechanism. Production .NET I/O is usually asynchronous and represented with `Task` or `Task<T>`, but those types have different execution semantics: task-based asynchronous methods generally start before returning the `Task`. A cold asynchronous analogue of this teaching type would defer task creation, for example behind a `Func<CancellationToken, Task<T>>`.

## Traversal and policy

The previous example produced a list of suspended price requests:

```csharp
List<IO<decimal>> requests =
    productIds.Map(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId));
```

The list itself has already been built. The wrapped price requests are still deferred.

```text
List<IO<decimal>>  // Many suspended price requests.
IO<List<decimal>>  // One suspended program that will produce a list.
```

After `Map`, you still need a helper that combines those many deferred requests into one deferred batch. A helper such as `SequenceSequential` or `TraverseSequential` also fixes the policy for that batch. In this article, that policy is: run later, in list order, one at a time, and stop on exception.

This turns the list of request thunks into one batch thunk:

```csharp
IO<List<decimal>> program = requests.SequenceSequential();
```

Here is one simple implementation:

```csharp
public static class IOExtensions
{
    public static IO<List<TResult>> TraverseSequential<TSource, TResult>(
        this List<TSource> source,
        Func<TSource, IO<TResult>> action)
    {
        return IO<List<TResult>>.Delay(() =>
        {
            var results = new List<TResult>();

            foreach (TSource item in source)
            {
                IO<TResult> operation = action(item);
                TResult result = operation.Run();
                results.Add(result);
            }

            return results;
        });
    }

    public static IO<List<T>> SequenceSequential<T>(this List<IO<T>> source)
    {
        return source.TraverseSequential(static operation => operation);
    }
}
```

`SequenceSequential` still does not start the requests. The work begins only when the outer `Run()` executes the batch program:

```csharp
List<decimal> prices = program.Run();
```

`TraverseSequential` contributes the following policy:

* list traversal is deferred until `Run()`;
* `action` is invoked during that traversal;
* items are handled in list order;
* one `IO` completes before the next begins;
* results are stored in the same order;
* an exception stops later items, but it does not undo effects that earlier items already performed;
* every outer `Run()` traverses the list and executes the operations again.

The nested `Run()` calls inside `TraverseSequential` are part of that deferred traversal's implementation, so they happen only after the outer batch program begins. If you wanted pauses between items, retries around each request, reverse order, or some other rule, `Run()` would not invent that later. You would build it into each item `IO`, or write a different traversal helper with a different policy.

## Conclusion

The important distinction is not merely that effects exist. It is that constructing an effectful computation is different from running it.

This tiny `IO<T>` represents an effectful thunk as a cold value. `Delay` suspends it, `FlatMap` composes dependent steps without running them, and `Run()` marks the execution boundary.

Keep pure transformations as ordinary functions, return `IO<T>` from effectful helpers, compose those values without running them, and call `Run()` near the application boundary.

## Appendix

<details markdown="1">
<summary markdown="span">Open the appendix for optional query syntax support</summary>

### Optional C# query syntax support

If you want C# query syntax on `IO<T>`, add the standard `Select` and `SelectMany` methods:

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
        from unitPrice in FetchCurrentPriceIO(remotePriceApi, order.ProductId)
        let total = CalculateLineTotal(order.Quantity, unitPrice, order.TaxRate)
        let report = RenderReport(order, unitPrice, total)
        from result in WriteAllTextIO(reportPath, report)
        select result;
}
```

</details>
