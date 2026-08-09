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

Why does that matter beyond avoiding a surprise API bill? A pure expression is **referentially transparent**: you can replace it with its result without changing what the program means. If `CalculateLineTotal(2, 19.99m, 0.13m)` returns the same value every time, a caller may evaluate it early, evaluate it later, or reuse the value. Those choices do not change the outside world.

Now consider a tiny stateful function:

```csharp
private static int count = 0;

public static int Next()
{
    count++;
    return count;
}
```

Starting from zero, `Next() + Next()` produces `1 + 2`, or `3`. If we make what looks like an ordinary algebraic simplification and write `2 * Next()`, the result is `2` and the counter changes only once. Repeating or rearranging the call changed both the returned value and the state of the program.

A remote request has the same problem, even when it is less obvious. Calling it twice may consume twice the quota; moving it may send the request before validation; skipping it may mean an audit record is never written. Effectful functions are not defective functions, but you cannot reason about their calls as though they were ordinary substitutions. Their timing and order matter.

`IO<T>` does not make `Next`, file access, or network access pure. Instead, it moves the actual call behind a value. Constructing an `IO<T>` says, "Here is how to perform this operation later." If construction itself remains free of effects, that description can be passed around and combined without changing the world. `FlatMap` then records which description depends on the result of another. Nothing runs merely because you connected the pieces.

This distinction is especially useful in non-strict functional languages such as Haskell, where an unused expression may never be evaluated and independent pure expressions may be evaluated when convenient. Haskell represents `IO` actions as values and gives the final action to `main`, where the runtime performs it. C# is eager and already defines evaluation order, so our small `IO<T>` is not fixing C#'s execution rules. We are borrowing the useful separation between describing work and performing it.

The practical shift is small: instead of asking a helper to perform an effect and return its result, ask it to return a value describing that effect. We can then build the whole workflow one operation at a time.

## Return the work instead of doing it

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

Nothing mystical is happening here. At this point, `IO<T>` is a deliberately named wrapper around a `Func<T>`:

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

Here is the complete implementation used in this article:

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

This is a synchronous teaching model: C# does not enforce pure construction, and the type is not a replacement for the Task-based Asynchronous Pattern or normal C# application structure.

Exercise for the reader: open your IDE and implement `IO<T>` from scratch without AI assistance. Use a counter to prove that construction, `Map`, and `FlatMap` do nothing immediately, then prove that every call to `UnsafeRun()` increments the counter again.
