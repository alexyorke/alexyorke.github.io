---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> turns effectful work into a cold value. FlatMap composes those values, while UnsafeRun() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

The first two parts used the same small pattern in different contexts. We lifted a value, then used `FlatMap` to compose a dependent step while `List`, `Maybe`, or `Result` decided what flowed onward.

Some functions do more than calculate a value. They read or write files, ask for input, call APIs, draw to the screen, or change shared state. Calling one of these functions interacts with the world. We will call that interaction an **effect** and the function an **effectful function**.

In ordinary procedural C#, statement order already gives effects an obvious sequence:

```csharp
File.WriteAllText(path, "first");
File.AppendAllText(path, "second");
```

The first write runs before the second. Reversing, repeating, or skipping either statement changes the file. C# does not need a monad to tell it which statement comes first.

But C# already sequences those writes. So what is `IO` buying us?

The useful change is not that `IO<T>` teaches C# how to execute statements. It turns **work that could happen later into a value we can return, store, and compose now**. `FlatMap` combines those values in dependency order, and one explicit call performs the resulting program.

That is the idea for this article: construct the effectful computation first, run it later.

## When calling a function does something

Let us start with the kind of function we passed to `Map` in Part 1. This price calculation is pure: its explicit inputs determine its result, and calling it changes nothing outside the function.

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

As in Part 1, I will use `Map` as C#-ish shorthand for an eager list transformation. In normal C#, `Select(...).ToList()` is the closest built-in spelling:

```csharp
var quantities = new List<int> { 1, 2, 3 };

List<decimal> totals =
    quantities.Map(quantity =>
        CalculateLineTotal(
            quantity,
            unitPrice: 19.99m,
            taxRate: 0.13m));
```

The list invokes the function once for each quantity and collects the three results. Nothing surprising happens if the list performs those calculations immediately.

Now give `Map` a function that calls a remote price service:

```csharp
public static decimal FetchCurrentPrice(
    IRemotePriceApi remotePriceApi,
    string productId)
{
    return remotePriceApi.GetCurrentPrice(productId);
}
```

```csharp
var productIds =
    new List<string> { "A-100", "B-200", "C-300" };

List<decimal> prices =
    productIds.Map(productId =>
        FetchCurrentPrice(remotePriceApi, productId));
```

The shape looks almost identical, but mapping now sends three requests. The list still invokes the supplied function immediately, once per element, in list order. If the second request throws, the third product is never reached.

The same product ID can also produce a different price on a later call. The remote service may have changed, the request may consume quota, or an earlier call may affect throttling. When the function is effectful, **when and how often `Map` calls it becomes part of the program's meaning**.

The list is not doing anything wrong. It owns the rule for invoking its function:

* The eager list from Part 1 invokes it once per element.
* `Maybe<T>` invokes it zero or one times.
* `Result<TSuccess, TError>` invokes it only on the success path.
* The `IO<T>` in this article invokes it only when the resulting `IO` is run.

Pure functions are easy to move between those contexts because invoking them has no outside consequence. With an effectful function, the context's invocation rule becomes observable.

## From an immediate result to a suspended computation

`FetchCurrentPrice` has to send its request before it can return a `decimal`. To separate constructing the request from performing it, change the return type:

```text
(IRemotePriceApi, string) -> decimal
(IRemotePriceApi, string) -> IO<decimal>
```

```csharp
public static IO<decimal> FetchCurrentPriceIO(
    IRemotePriceApi remotePriceApi,
    string productId)
{
    ArgumentNullException.ThrowIfNull(remotePriceApi);
    ArgumentNullException.ThrowIfNull(productId);

    return IO<decimal>.Delay(
        () => remotePriceApi.GetCurrentPrice(productId));
}
```

Calling `FetchCurrentPriceIO` does not send a request. It stores the request-producing function inside an `IO<decimal>`.

Now the eager list can map over the same product IDs:

```csharp
List<IO<decimal>> requests =
    productIds.Map(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId));
```

The list still maps immediately. It calls `FetchCurrentPriceIO` three times and creates three `IO<decimal>` values, but none of the stored API calls has run. We changed what the function returns, not how the list works.

Do not overcomplicate `IO<T>` yet. At this point it is a deliberately named wrapper around a `Func<T>`:

* `Pure` lifts a value that is already available.
* `Delay` stores work that should happen later.
* `Map` transforms the eventual result.
* `FlatMap` uses one eventual result to choose the next `IO`.
* `UnsafeRun` performs the stored and composed work.

`Delay` means "defer evaluation." It is unrelated to `Task.Delay` and does not put anything on another thread.

There is one easy mistake to make here. Passing an effectful call to `Pure` is already too late:

```csharp
IO<decimal> notSuspended =
    IO<decimal>.Pure(
        remotePriceApi.GetCurrentPrice(productId));
// GetCurrentPrice ran before Pure received the decimal.
```

C# evaluates method arguments before calling the method. `Pure` can wrap the resulting price, but it cannot undo the request that produced it. Use `Delay` when producing the value is itself the work you want to postpone.

## A small `IO<T>`

Here is the complete core used in the main article:

```csharp
using System;

public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}

public sealed class IO<T>
{
    private readonly Func<T> operation;

    private IO(Func<T> operation)
    {
        this.operation = operation;
    }

    public static IO<T> Pure(T value) =>
        new(() => value);

    public static IO<T> Delay(Func<T> operation)
    {
        ArgumentNullException.ThrowIfNull(operation);
        return new IO<T>(operation);
    }

    public IO<TResult> Map<TResult>(
        Func<T, TResult> transform)
    {
        ArgumentNullException.ThrowIfNull(transform);

        return FlatMap(value =>
            IO<TResult>.Pure(transform(value)));
    }

    public IO<TResult> FlatMap<TResult>(
        Func<T, IO<TResult>> next)
    {
        ArgumentNullException.ThrowIfNull(next);

        return new IO<TResult>(() =>
        {
            T value = UnsafeRun();
            IO<TResult> nextComputation = next(value);

            if (nextComputation is null)
            {
                throw new InvalidOperationException(
                    "FlatMap continuation returned null.");
            }

            return nextComputation.UnsafeRun();
        });
    }

    public T UnsafeRun() =>
        operation();
}
```

Part 1 used the name `Unit` for the operation that lifts a value into a monadic context. This implementation follows another common convention and calls that operation `Pure`.

The `Unit` *type* above is a different idea. It is a one-value stand-in for `void`, useful when an effect such as writing a file has no interesting result beyond successful completion. `IO<Unit>` means "a computation that may perform effects and, if it completes, returns the only `Unit` value."

Notice that `Map` is defined using `FlatMap` and `Pure`. The transform produces an ordinary value, `Pure` lifts it back into `IO`, and `FlatMap` handles the sequencing.

There are calls to `UnsafeRun` inside `FlatMap`, but both sit inside the delegate stored by the newly returned `IO<TResult>`. Calling `Map` or `FlatMap` only constructs another cold value. The inner calls happen later, when somebody runs the outer computation.

This wrapper does not memoize. Each `UnsafeRun()` invokes the stored delegate again, so both its effects and its result may differ on every run.

## Compose first, run later

Suppose we need to read an order, fetch the product's current price, calculate its total, render a report, and write that report to disk. Ordinary procedural C# expresses the sequence clearly:

```csharp
public static void LoadOrderAndWriteReportNow(
    IRemotePriceApi remotePriceApi,
    string orderPath,
    string reportPath)
{
    string contents = File.ReadAllText(orderPath);
    Order order = ParseOrder(contents);
    decimal unitPrice =
        remotePriceApi.GetCurrentPrice(order.ProductId);
    decimal total = CalculateLineTotal(
        order.Quantity,
        unitPrice,
        order.TaxRate);
    string report =
        RenderReport(order, unitPrice, total);

    File.WriteAllText(reportPath, report);
}
```

There is nothing inherently wrong with this version. For many C# programs it is the clearest code. It performs the whole workflow as soon as the method is called.

To make construction separate from execution, first give the file operations the same delayed shape as the price request:

```csharp
public static IO<string> ReadAllTextIO(string path)
{
    ArgumentNullException.ThrowIfNull(path);
    return IO<string>.Delay(
        () => File.ReadAllText(path));
}

public static IO<Unit> WriteAllTextIO(
    string path,
    string contents)
{
    ArgumentNullException.ThrowIfNull(path);
    ArgumentNullException.ThrowIfNull(contents);

    return IO<Unit>.Delay(() =>
    {
        File.WriteAllText(path, contents);
        return Unit.Value;
    });
}
```

Now the workflow itself can return one larger `IO<Unit>`:

```csharp
public static IO<Unit> LoadOrderAndWriteReport(
    IRemotePriceApi remotePriceApi,
    string orderPath,
    string reportPath)
{
    return ReadAllTextIO(orderPath)
        .Map(ParseOrder)
        .FlatMap(order =>
            FetchCurrentPriceIO(
                remotePriceApi,
                order.ProductId)
            .Map(unitPrice =>
            {
                decimal total = CalculateLineTotal(
                    order.Quantity,
                    unitPrice,
                    order.TaxRate);

                return RenderReport(
                    order,
                    unitPrice,
                    total);
            }))
        .FlatMap(report =>
            WriteAllTextIO(reportPath, report));
}
```

`Map(ParseOrder)` is appropriate because parsing is intended to be a pure transformation from text to an order. The inner `Map` calculates and renders another ordinary value. The two `FlatMap` calls are where a result determines the next effectful computation.

Constructing this pipeline reads no file, sends no request, and writes no report. It creates one value that describes the dependency order:

```text
read -> parse -> fetch price -> calculate -> render -> write
```

If the composed value is run, `FlatMap` performs those steps from left to right. The read must produce text before parsing can happen, and the price request must produce a price before the total can be calculated.

## How do you run the damn thing?

Part 1 asked how to get values out of monads. With this tiny `IO<T>`, `UnsafeRun()` is the answer, but you normally want to postpone that answer until the edge of the application.

First construct the program:

```csharp
IO<Unit> program = LoadOrderAndWriteReport(
    remotePriceApi,
    "order.json",
    "report.txt");
// Nothing inside the IO has run.
```

Then run it from the top-level code that has decided the effects should happen:

```csharp
Unit completion = program.UnsafeRun();
```

That one call reads the order, fetches the price, calculates and renders the report, and writes the file in the sequence encoded by `FlatMap`.

Call `UnsafeRun()` a second time and the whole workflow runs a second time. It re-reads the file, re-fetches the price, and rewrites the report. An `IO<T>` is not a cached result; it is repeatable work.

The name `UnsafeRun` does not mean memory-unsafe. It is a warning label: this is the point where the program stops merely describing effects and starts making them observable. If an operation throws, the exception propagates, later steps do not run, and effects that already happened are not automatically undone.

If a helper calls `UnsafeRun()` in the middle of your call graph, it has already performed that part of the program before its caller can compose anything around it. Returning `IO<T>` keeps that choice with the outer caller.

## Monad Laws

`Pure` and `FlatMap` form the monadic core. Just like the `Maybe` laws in Part 1, three laws keep composition predictable:

1. **Left identity:** `IO<T>.Pure(x).FlatMap(f)` behaves the same as `f(x)`. Lifting a value and immediately passing it to the next computation should add no behavior.
2. **Right identity:** `m.FlatMap(x => IO<T>.Pure(x))` behaves the same as `m`. Passing a result through `Pure` should not change the computation.
3. **Associativity:** `m.FlatMap(f).FlatMap(g)` behaves the same as `m.FlatMap(x => f(x).FlatMap(g))`. Regrouping dependent steps should not change their result or effect order.

"Behaves the same" does not mean reference equality. Each side creates different wrapper and delegate objects. It means that running either side produces equal results and the same effects in the same order. The formal term is **observational equivalence under `UnsafeRun()`**.

There is an important C# caveat. These laws assume that `f` and `g` only *construct* non-null `IO` values without throwing or performing observable work. C# cannot stop a continuation from performing an effect immediately or calling `UnsafeRun()` itself. If a callback cheats, the reasoning guarantee disappears.

That is also why `Map` can be defined as:

```csharp
m.FlatMap(value =>
    IO<TResult>.Pure(transform(value)));
```

`FlatMap` supplies the sequencing, while `Pure` puts the transformed value back into the context.

## Conclusion

An effectful function that returns `T` has to perform its work to produce that `T`. A function that returns `IO<T>` can instead construct a cold value that describes how to produce it later.

`Delay` introduces the suspended work. `Map` transforms its eventual value. `FlatMap` composes dependent suspended steps. `UnsafeRun()` marks the point where the composed program actually interacts with the world.

This does not make the underlying file access or API request pure, and it does not mean normal procedural C# is wrong. It gives you a distinct value for "work that has not happened yet" and an explicit place to decide when that work runs.

Keep pure calculations as ordinary functions, return `IO<T>` from the effectful helpers you want to defer, compose without forcing those values, and call `UnsafeRun()` near the application boundary.

This implementation is a synchronous teaching model, not a replacement for the Task-based Asynchronous Pattern or normal C# application structure. The appendix collects the theory, conveniences, and limitations that are useful after the core idea makes sense.

Exercise for the reader: open your IDE and implement `IO<T>` from scratch without AI assistance. Use a counter to prove that construction, `Map`, and `FlatMap` do nothing immediately, then prove that every call to `UnsafeRun()` increments the counter again.

## Appendix

<details markdown="1">
<summary markdown="span">Why functional programming talks about IO</summary>

### Referential transparency and evaluation order

Pure functional programming starts from a reasoning model that resembles algebra:

```text
x = 5 + 1
y = 4 + 9 - 2
w = y + x
z = y + y + x
```

It does not matter whether `x` or `y` is evaluated first. Because `w` does not contribute to `z`, it need not be evaluated at all. Once we know `y` is `11`, we can replace either occurrence of `y` with `11` or rewrite `z` as `2y + x` without changing the answer.

This is **referential transparency**: replacing an expression with its value preserves the program's meaning. It supports **equational reasoning**, where ordinary algebraic transformations remain safe.

A stateful counter breaks that rule:

```csharp
private static int count = 0;

public static int Next()
{
    count++;
    return count;
}
```

Starting from zero, `Next() + Next()` produces `1 + 2`, or `3`. Rewriting it as `2 * Next()` invokes the counter once and produces `2`. A harmless algebraic rewrite changed both the answer and the number of state changes.

Lazy evaluation makes the issue especially visible. In a non-strict language such as Haskell, an expression is evaluated only when its value is needed:

```haskell
main = print result
  where
    a = 10
    unused = undefined
    b = 20
    result = a + b
```

Evaluating `undefined` would fail, but `unused` is never demanded, so this program prints `30`. Skipping an unused pure expression only saves work. If an unused expression silently contained a file write, skipping it would change the world.

Haskell's `IO` represents actions as values and exposes the final action as `main`, which the runtime performs. `FlatMap`-style composition adds the required data dependency and effect order without performing the actions during construction. Simon Peyton Jones and Philip Wadler describe this approach in [*Imperative functional programming*](https://www.microsoft.com/en-us/research/publication/imperative-functional-programming/).

C# is already eager and specifies expression-evaluation order. The tiny `IO<T>` in this article is therefore not repairing C#'s evaluation semantics. It borrows the separation between describing and performing work so effectful operations can be named, stored, returned, and composed before execution.

</details>

<details markdown="1">
<summary markdown="span">A related example with deferred LINQ</summary>

### `IEnumerable.Select` has its own execution policy

The main article uses the eager `List.Map` model from Part 1. Real LINQ-to-Objects `Enumerable.Select` is deferred:

```csharp
IEnumerable<decimal> prices =
    productIds.Select(productId =>
        remotePriceApi.GetCurrentPrice(productId));

// Select has sent no requests yet.

List<decimal> firstRead = prices.ToList();
// Three requests.

List<decimal> secondRead = prices.ToList();
// The same three calls run again.
```

If nobody enumerates the sequence, no request is sent. Enumerating it twice sends the requests twice. A lazy or mutable source may even provide different product IDs on the second enumeration.

`IEnumerable<T>` defers a many-value traversal. It does not mark one explicit effect boundary or promise exactly one result. This is another example of the host abstraction deciding whether, when, and how often it invokes the supplied function.

</details>

<details markdown="1">
<summary markdown="span">Optional C# query syntax</summary>

### Adding `Select` and `SelectMany`

C# query syntax works through methods rather than a required interface. Add these methods to `IO<T>`:

```csharp
public IO<TResult> Select<TResult>(
    Func<T, TResult> selector) =>
    Map(selector);

public IO<TResult> SelectMany<TNext, TResult>(
    Func<T, IO<TNext>> next,
    Func<T, TNext, TResult> project)
{
    ArgumentNullException.ThrowIfNull(next);
    ArgumentNullException.ThrowIfNull(project);

    return FlatMap(value =>
    {
        IO<TNext> nextComputation = next(value);

        if (nextComputation is null)
        {
            throw new InvalidOperationException(
                "SelectMany selector returned null.");
        }

        return nextComputation.Map(
            nextValue => project(value, nextValue));
    });
}
```

The order-report workflow can then be written as a query expression:

```csharp
public static IO<Unit> LoadOrderAndWriteReportQuery(
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

The [C# specification](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/language-specification/expressions#12233-query-expression-translation) translates `from` to `SelectMany` and `let` to `Select`. Query syntax does not make a computation cold by itself; the behavior comes from these particular methods returning delayed `IO` values.

</details>

<details markdown="1">
<summary markdown="span">Additional combinators, expected failures, and resources</summary>

### Building beyond the monadic core

The following optional methods give a few common policies names. `Then` sequences an independent next computation, `Zip` retains both results, and `Flatten` removes one nested `IO` layer:

```csharp
// Add these instance methods to IO<T>.

public IO<TResult> Then<TResult>(
    IO<TResult> next)
{
    ArgumentNullException.ThrowIfNull(next);
    return FlatMap(_ => next);
}

public IO<(T First, TNext Second)> Zip<TNext>(
    IO<TNext> other)
{
    ArgumentNullException.ThrowIfNull(other);

    return FlatMap(first =>
        other.Map(second => (first, second)));
}

// C# permits generic and non-generic types to share a name.
public static class IO
{
    public static IO<T> Flatten<T>(IO<IO<T>> nested)
    {
        ArgumentNullException.ThrowIfNull(nested);
        return nested.FlatMap(inner => inner);
    }
}
```

Exceptions normally propagate from `UnsafeRun()`. Using the `Result<TSuccess, TError>` type from [Part 2](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/), `Attempt` can turn one selected, expected exception type into a value while keeping execution deferred:

```csharp
// Add this instance method to IO<T>.

public IO<Result<T, TException>> Attempt<TException>()
    where TException : Exception
{
    return IO<Result<T, TException>>.Delay(() =>
    {
        try
        {
            return Result<T, TException>.Ok(
                UnsafeRun());
        }
        catch (TException exception)
            when (exception is not OperationCanceledException)
        {
            return Result<T, TException>.Fail(
                exception);
        }
    });
}
```

Do not routinely catch `Exception` this way. Programming errors and cancellation should normally retain their usual semantics. Turning an exception into `Result` also cannot undo an external operation that partially succeeded before throwing.

Resource acquisition, use, and release must all remain inside the deferred lifetime. A small `Bracket` helper can keep them in one computation:

```csharp
// Add this method to the non-generic IO companion above.

public static IO<TResult> Bracket<TResource, TResult>(
    IO<TResource> acquire,
    Func<TResource, IO<TResult>> use,
    Func<TResource, IO<Unit>> release)
{
    ArgumentNullException.ThrowIfNull(acquire);
    ArgumentNullException.ThrowIfNull(use);
    ArgumentNullException.ThrowIfNull(release);

    return IO<TResult>.Delay(() =>
    {
        TResource resource = acquire.UnsafeRun();

        try
        {
            return use(resource).UnsafeRun();
        }
        finally
        {
            release(resource).UnsafeRun();
        }
    });
}
```

For example:

```csharp
IO<string> firstLine =
    IO.Bracket(
        acquire: IO<StreamReader>.Delay(
            () => File.OpenText(path)),
        use: reader => IO<string>.Delay(
            () => reader.ReadLine() ?? string.Empty),
        release: reader => IO<Unit>.Delay(() =>
        {
            reader.Dispose();
            return Unit.Value;
        }));
```

`release` runs if acquisition succeeded, even when `use` throws. This tiny version has simple failure behavior: if both `use` and `release` fail, the release exception replaces the earlier one. Production effect libraries preserve richer error information.

</details>

<details markdown="1">
<summary markdown="span">Runtime semantics and limitations</summary>

### What this teaching model does and does not provide

* It is **synchronous**. `UnsafeRun()` invokes the delegate on the caller's thread and performs no scheduling.
* It is **cold and non-memoized**. Each `UnsafeRun()` invokes the stored delegate again.
* C# does not enforce purity. A dishonest factory, `Map` transform, or `FlatMap` continuation can perform effects before the intended boundary.
* Deep chains are not stack-safe because nested delegates call through nested `UnsafeRun()` frames.
* The stored `Func<T>` is opaque. The wrapper cannot inspect, optimize, log, or reinterpret individual instructions.
* It provides no built-in asynchronous execution, cancellation, concurrency, backpressure, or thread safety. It is not a replacement for [.NET's Task-based Asynchronous Pattern](https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/task-based-asynchronous-pattern-tap).
* It provides no automatic retry, transaction, rollback, or general resource safety. Those require explicit policies with operation-specific semantics.
* Every combinator allocates an `IO` object and usually a closure. Captured services and data remain reachable as long as the suspended computation does.

A cold asynchronous analogue starts closer to `Func<CancellationToken, Task<T>>` than to an already-created `Task<T>`, but a useful async effect type also needs deliberate cancellation, scheduling, concurrency, and resource semantics.

</details>
