---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> represents a computation with effects as a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

So far, this series has composed functions that mostly behave like calculations. This article is about what changes when those functions perform observable work beyond returning a value.

A side effect is any observable thing a function does besides return its result. Mutating shared state is a side effect even if no file, socket, database, or API is involved. I/O is one common kind of side effect: it communicates with something outside the function, such as a file, socket, database, API, console, system clock, or randomness source. Side effects are the broader category; this article mostly focuses on the I/O and outside-world subset.

So the final returned value is no longer the whole meaning of the program. The interaction history matters.

With effects, the semantic shape becomes more like:

program : World/Input/State -> Value plus World/Output/State

For example:

read     : InputState -> (Number, NewInputState)
write(n) : OutputState -> (Unit, NewOutputState)

* Pure computation = producing a value.
* Effectful computation = producing a value + an observable effect.

Pure computations are deterministic in the functional sense: the same inputs produce the same value, and evaluating them does not interact with anything else. I/O is non-deterministic from the program's point of view because the value may come from outside the program. If a function asks the user for input, its result is not knowable until the user types something, and the user can type anything. The same idea applies to API responses, file contents, the current time, or any other outside-world value observed when the computation runs.

A useful metaphor is that an effectful function runs against the current world and leaves a changed or newly observed world behind: world in, value plus world-prime out. C# does not pass a world value around, but the metaphor explains why execution cannot be treated as just another calculation. If effectful computations run wherever they happen to appear, a program may read from or write to the world at the wrong time.

Functional programming leans on this kind of reasoning: expressions should be easy to transform, refactor, and substitute while preserving the program's meaning. Raw I/O disrupts that style because moving a call can change when it reads from or writes to the world, how often it runs, or what value it observes.

`IO<T>` is one way to preserve some of that algebraic style around effectful code. It changes what gets composed: instead of handing `Map` or `FlatMap` a function that performs the effect immediately, it represents the effectful work as a cold value first. You can think of that value as a recipe or set of instructions for work that may happen later.

Building and transforming the recipe does not perform the effect, so that part can still be reasoned about like ordinary value manipulation. Running the recipe is different: that is when the program actually reads, writes, mutates, sends, retries, or observes whatever the recipe describes. Evaluating the `IO<T>` value does not run the work, so the program can compose it safely before choosing the order, timing, retry strategy, or number of executions.

> Note: This is a teaching model, not idiomatic C# advice. The goal is to make construction vs execution visible.

## When Composition Controls Execution

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

`List.Map` visits each element now and builds a new list. Because `CalculateLineTotal` is pure, that policy affects only when the calculation happens. The same inputs still determine the same result, and nothing outside the calculation changes.

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
// Map owns the traversal policy here: requests are
// sent now, as fast as this Map traverses.
```

`List.Map` is still applying the supplied function according to the list's traversal policy. With `FetchCurrentPrice`, that policy now controls real requests, not just calculation. Re-running it may consume quota, trigger rate limits, observe changed remote state, or duplicate a command such as an email. Other map-shaped contexts can choose different policies: `Maybe.Map` may skip the function, `Result.Map` may invoke it only on success, and another monad could do something else. Handing the effectful function directly to `Map` gives that context control over the effect.

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

This loop owns the policy explicitly: order, delay, retry, and stop-on-error behavior all live here. That direct control is useful, but less composable because the traversal policy is fused into the loop instead of returned as a value. A different caller with a different policy needs a different loop or helper.

With a plain return value, composition inherits either the manual loop policy or the caller's `Map` policy. `IO<T>` gives composition a suspended computation instead, so the policy can be chosen around a value that has not run yet.

## From an immediate result to a suspended computation

The solution is a signature change:

```text
(IRemotePriceApi, string) -> decimal
(IRemotePriceApi, string) -> IO<decimal>
```

The first form can produce a `decimal` only by running the request. The second returns a cold `IO<decimal>`: a value representing the request before it has run. Returning `IO<decimal>` keeps construction separate from execution with `Run()`.

```csharp
public static IO<decimal> FetchCurrentPriceIO(
    IRemotePriceApi remotePriceApi,
    string productId)
{
    return IO<decimal>.Delay(
        () => FetchCurrentPrice(remotePriceApi, productId));
}
```

Calling `FetchCurrentPriceIO` sends no request. It returns an `IO<decimal>` value that larger compositions can build on before execution begins. That is the point of the wrapper: creating the value is separate from executing the wrapped work with `Run()`.

Here, `Delay` means **defer evaluation**. It does not pause a thread, wait for a duration, or behave like `Task.Delay`.

```csharp
IO<decimal> request =
    FetchCurrentPriceIO(remotePriceApi, productId);
// No request yet.

decimal price = request.Run();
// The request is sent here.
```

Constructing the `IO<decimal>` value is not the same thing as running it. The first creates a value; the second executes the wrapped computation and performs its effects. In this teaching model, each call to `Run()` performs the computation again.

`Run()` makes the execution boundary explicit. Returning `IO<T>` lets the larger program transform, combine, traverse, store, and pass around the work before crossing that boundary. In a fuller effect system, application code would usually return the final `IO` and let a runtime or interpreter execute it instead of calling `Run()` manually. In this small teaching model, `Run()` stands in for that boundary.

This is where the usual functional programming phrase **referential transparency** fits. The expression that builds an `IO<T>` can be treated like a value and moved around or substituted without performing the effect; only `Run()` crosses into observable execution. C# does not enforce that discipline, but the wrapper makes the intended boundary visible.

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

`Unit` is roughly `void` represented as a value. It is useful when an effect has no meaningful success value, but `IO<T>` is not limited to `Unit`: reading a file can return `IO<string>`, fetching a price can return `IO<decimal>`, and a larger program can return whatever value its caller needs.

Errors are still part of execution. In this tiny model, exceptions propagate when `Run()` is called. If a program wants failures as ordinary values instead, it can return something like `IO<Result<T>>` and compose that value while the I/O remains suspended. A fuller API could also add recovery or retry combinators, but those policies would still be composed before execution.

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
