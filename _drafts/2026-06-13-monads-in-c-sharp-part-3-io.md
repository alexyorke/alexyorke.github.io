---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> represents a computation with effects as a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

Some functions do more than calculate a value: they may call an API, query a database, send an email, write a file, or observe time or randomness. Those interactions are usually called side effects; here I will shorten that to effects. A pure function, by contrast, depends only on its declared inputs: the same inputs produce the same result, evaluating it produces no effects, and a call can be replaced with its result without changing the program.

Effects make composition harder because calling the function is no longer just asking for a value; it also decides that the outside-world interaction should happen now.

`IO<T>` represents effectful work as a cold computation value, so larger programs can compose it before crossing the execution boundary.

> Note: This is a teaching model, not idiomatic C# advice. The goal is not to eliminate effects; useful programs need effects. The goal is to make the separation between constructing and running effectful work visible.

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

In Part 1, `List.Map` visits each element now and builds a new list. Because `CalculateLineTotal` is pure, that policy changes work, not meaning: the same inputs still determine the same result. You can recompute it, delay it, discard it, or plug it into another map-shaped context, and nothing outside the calculation changes.

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

`List.Map` is still just applying the supplied function according to the list's traversal policy. The problem is that `FetchCurrentPrice` is not just a calculation. Invoking it already sends a request, so you cannot treat it like a value you can freely throw away and recompute. If this API needs pacing, retries, short-circuiting after failure, or simply to happen at a particular time, something has to own that policy.

If you wrote the same thing procedurally, that policy would be explicit in the loop:

```csharp
var pricesProcedural = new List<decimal>();

foreach (string productId in productIds)
{
    decimal price =
        FetchCurrentPrice(remotePriceApi, productId);

    pricesProcedural.Add(price);

    // This is where you would add delays,
    // retries, or error handling.
}
```

This loop owns the policy explicitly: it runs immediately, in list order, and stops on an exception unless the loop handles that case. Delays, retries, and error handling go directly in the loop. That direct control is useful, but it is less composable because the traversal policy is fused into the loop. A different caller with a different policy needs a different loop or helper.

With `Map`, the type providing `Map` owns the traversal policy instead. `List.Map` may run once per element, `Maybe.Map` zero or one time, `Result.Map` only on the success path, and `IO.Map` later when an `IO` runs. For pure functions those differences mostly change work. For effects like API calls, printing, or sending email, they change what happens in the outside world.

The method still looks like an ordinary function returning `decimal`, but invoking it sends a request and observes external state not fully described by its arguments. A later call may observe a new price, consume quota, fail transiently, or be throttled. Replacing `FetchCurrentPrice(remotePriceApi, productId)` with a returned `decimal` therefore hides the fact that the request already happened. `IO<T>` instead returns a pure, first-class suspended computation that can be composed before any effect happens.

## From an immediate result to a suspended computation

The effectful price lookup is still a function we want to compose with other steps. But `(IRemotePriceApi, string) -> decimal` means the request has already run by the time any larger program receives the value. `IO<T>` is a value representing a computation that may perform effects and eventually return a `T` when run. Returning `IO<decimal>` keeps construction separate from execution with `Run()`.

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

Calling `FetchCurrentPriceIO` sends no request. It returns a pure `IO<decimal>` value that larger compositions can keep building on before execution begins. The point is not wrapping for its own sake: evaluating the expression that creates the value is one thing, and executing the wrapped work with `Run()` is another.

Here, `Delay` means **defer evaluation**. It does not pause a thread, wait for a duration, or behave like `Task.Delay`.

```csharp
IO<decimal> request =
    FetchCurrentPriceIO(remotePriceApi, productId);
// No request yet.

decimal price = request.Run();
// The request is sent here.
```

Constructing the `IO<decimal>` value is not the same thing as running it: the first evaluates to a value, while the second executes the wrapped computation and performs its effects. In this teaching model, each call to `Run()` performs the computation again.

`Run()` makes the execution boundary explicit. The point of returning `IO<T>` is that the larger program can transform, combine, traverse, store, and pass around the work before crossing that boundary. In a fuller effect system, application code would usually return the final `IO` and let a runtime or interpreter execute it instead of calling `Run()` manually. In this small teaching model, `Run()` stands in for that boundary.

```csharp
IO<decimal> totalProgram =
    FetchCurrentPriceIO(remotePriceApi, productId)
        .Map(unitPrice =>
            CalculateLineTotal(
                quantity,
                unitPrice,
                taxRate));
// Still no request.
```

Constructing `totalProgram` sends no request. Running it fetches the price and then calculates the total:

```csharp
decimal total = totalProgram.Run();
```

Suspension does not itself choose an execution policy. It keeps the effect unperformed while the program is assembled. Here, `Map` keeps the pure calculation inside the suspended program; `FlatMap` establishes sequential order when the next step returns another `IO`. Other combinators can later express policies such as retries, pacing, or collection traversal.

> **`IO<T>` does not remove the effect or decide how it should run. The indirection is the point: it makes the effectful computation explicit and keeps it suspended while those decisions are composed.**

Once effects are represented as values, these operations become the small vocabulary that says how the larger computation proceeds.

The teaching model has five central operations:

```text
Pure    : T -> IO<T>
Delay   : (() -> T) -> IO<T>
Map     : IO<T> -> (T -> TResult) -> IO<TResult>
FlatMap : IO<T> -> (T -> IO<TResult>) -> IO<TResult>
Run     : IO<T> -> T
```

`Pure` wraps an already available value; `Delay` suspends a computation; `Map` transforms an eventual result; `FlatMap` sequences the next effectful step based on the previous result; and `Run` performs the computation. Together they give a small vocabulary for describing how a larger effectful computation proceeds while the work is still suspended.

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

The following uses C# query syntax over `IO<T>` as sugar for `Select` and `SelectMany`, which delegate to `Map` and `FlatMap`. The appendix shows those adapter methods.

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

`TraverseSequential` returns one suspended program that visits the product IDs in order, runs one request at a time, and collects the results. If the `IO` values already exist, the same idea is often called sequence. Both produce one suspended computation for the entire batch:

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

This `IO<T>` is a tiny teaching model, not a recommendation for idiomatic C# application structure. It is synchronous, cold, opaque, and non-memoized: nothing happens until `Run()`, and each call to `Run()` starts the computation again on the current thread. Exceptions propagate normally, captured mutable state is observed at run time, and C# does not enforce purity. It is also not stack-safe for very deep chains and provides no built-in cancellation, resource safety, retry, rollback, or async execution; normal .NET async I/O uses `Task` or `Task<T>`, and TAP methods generally return already-started work unlike this cold teaching type.

## Conclusion

Returning `IO<T>` changes the function from "perform an effect and return `T`" to "construct a suspended computation that can later produce `T`." `FlatMap` composes dependent suspended operations, `TraverseSequential` or `SequenceSequential` chooses how a batch is executed, and `Run()` marks the boundary where execution begins.

Keep pure transformations as ordinary functions, return `IO<T>` from effectful helpers, compose those values without forcing them, and call `Run()` near the application boundary.

## Appendix

<details markdown="1">
<summary markdown="span">Open the appendix for query syntax support</summary>

### C# query syntax support

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
