---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> turns effectful work into a cold value. FlatMap composes those values, while UnsafeRun() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

The first two parts lifted values, then used `Map` and `FlatMap`—called `Bind` in Part 2—to compose dependent steps while `List`, `Maybe`, or `Result` decided what flowed onward.

Some functions also read files, ask for input, call APIs, draw to the screen, or change shared state. We call that interaction with the world an **effect**, and a function that performs one an **effectful function**.

An effect matters even when its return value is discarded. `Console.WriteLine(...)` returns no useful value, but displaying the text is still part of the program. A successful file write likewise remains after the program exits. An HTTP request may update a database; discarding its result does not undo that work.

Useful programs need effects; without output, storage, or communication, they are just black boxes that get warm while computing.

A pure calculation is different. Evaluating and discarding `1 + 1` changes no external state. Repeating or skipping it likewise changes nothing outside the calculation. With an effect, **whether, how often, and in what order** it runs can change the program's meaning.

The IO monad is one way to sequence and compose effectful computations. It represents them as recipes we can compose now and run later. What problem does that solve in C#?

## Why do we need this IO monad?

In ordinary procedural C#, statement order already gives effects an obvious sequence:

```csharp
File.AppendAllText(path, "first");
File.AppendAllText(path, "second");
```

Assuming both calls succeed, the first append runs before the second. Reversing or skipping either call changes the file. Although they return `void`, the calls run for their effects; the next statement answers "what happens next?"

Functional programming often reasons about expressions more like algebra. Consider:

```text
x = 2
y = x + 4
z = x + y + 1
```

Replacing `x` with `2`, or `y` with `x + 4`, leaves `z` unchanged. This is **referential transparency**: replacing an expression with its value preserves meaning. It supports **equational reasoning**, where equal expressions can be substituted as in algebra.

If we only need `y`, calculating `z` would be wasted work.

In Haskell,

```
import Debug.Trace (trace)

main :: IO ()
main = do
    let x = trace "calculating x" 2
        y = trace "calculating y" (x + 4)
        z = trace "calculating z" (x + y + 1)

    print y
```
It prints:

```
calculating y
calculating x
6
```

`z` is never evaluated. With an effectful expression, however, evaluation itself changes the world.

Eager C# behaves differently:

```
using System;

static int Calculate(string name, int value)
{
    Console.WriteLine($"calculating {name}");
    return value;
}

int x = Calculate("x", 2);
int y = Calculate("y", x + 4);
int z = Calculate("z", x + y + 1);

Console.WriteLine(y);
```

It prints:

```
calculating x
calculating y
calculating z
6
```

Although `z` is unused, its initializer still runs—and prints—because C# evaluates the statement eagerly. The result is discarded, but the effect remains.

Effectful functions also resist substitution:

```
x = ReadFile(...)
y = ReadFile(...)
z = x + y
```

Effects make substitution observable: two file reads may return different values, so replacing `x + y` with `2 * x` can change the program. In non-strict Haskell, demand determines whether and when expressions run; C# is eager, so this tiny `IO<T>` is not fixing its evaluation order.

Instead, `IO<T>` represents effectful work as a deferred recipe. `FlatMap` composes recipes in dependency order, and the outer caller starts it. The operations remain effectful; only their execution is postponed.

## When calling a function does something

Let us start with the kind of function we passed to `Map` in Part 1. This price calculation is intended to be pure: its explicit inputs determine its outcome, and calling it changes no state outside the function.

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

As in Part 1, I will use `Map` as C#-ish shorthand for an eager list transformation; one familiar built-in spelling is `Select(...).ToList()`:

```csharp
var quantities = new List<int> { 1, 2, 3 };

List<decimal> totals =
    quantities.Map(quantity =>
        CalculateLineTotal(
            quantity,
            unitPrice: 19.99m,
            taxRate: 0.13m));
```

This eager mapping invokes the function once for each quantity and collects the results.

Because the calculation is pure, that invocation policy has no outside consequence.

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

This sequential `Map` calls `FetchCurrentPrice` three times immediately, in order. If the second call throws, the third is never reached.

Both mappings accept a function and return a list, but the second function hides an interaction with the world behind its `decimal` result. Its return type says nothing about when the request occurs. Changing invocation frequency does not add external effects to the first mapping, but it can materially change the second.

The context owns the invocation rule: `List` invokes once per element, the earlier `Maybe<T>` zero or one times, the earlier `Result<TSuccess, TError>` only on success, and `IO<T>` only when run. With an effectful function, that rule determines whether it runs, how often, and where failure stops the computation.

The return type is now the problem. `FetchCurrentPrice` cannot produce a `decimal` until it sends the request, and `decimal` cannot represent a request that has not happened yet. To compose that work before performing it, the helper must return a description of the request instead.

## Return the work instead of doing it

In this example, `FetchCurrentPrice` calls the API before it can return a `decimal`. To separate construction from execution, return an `IO<decimal>` instead:

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

Calling `FetchCurrentPriceIO` validates its arguments but sends no request. It stores the request-producing function inside an `IO<decimal>`, so the return type signals deferred work rather than an available price.

Now the eager list can map over the same product IDs:

```csharp
List<IO<decimal>> requests =
    productIds.Map(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId));
```

The eager list still creates three `IO<decimal>` values, but their stored API calls do not run. We changed the function's return type, not the list. `IO<T>` wraps a `Func<T>`; `Delay` stores it without scheduling or changing threads.

There is one easy mistake to make here. Passing an effectful call to `Pure` is already too late:

```csharp
IO<decimal> notSuspended =
    IO<decimal>.Pure(
        remotePriceApi.GetCurrentPrice(productId));
// GetCurrentPrice is invoked before Pure can receive a decimal.
```

C# evaluates arguments first, so `Pure` can only wrap the price after the request; it cannot undo the work. Use `Delay` when producing the value is the work to postpone.

## A small `IO<T>`

Here is the complete implementation used in this article. It targets C# 10 and .NET 6 or later because it uses `record struct` and `ArgumentNullException.ThrowIfNull`:

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

Two details matter:

- Part 1 named the lifting operation `Unit`; here it follows another convention and is named `Pure`. These are separate ideas: the `Unit` *type* stands in for `void` when an effect's only result is completion.
- `FlatMap` is deferred because its `UnsafeRun()` calls remain inside the stored delegate, so composition performs none of the stored work. When run, it obtains the first result, constructs the dependent `IO`, and runs it.

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
    decimal unitPrice = remotePriceApi
        .GetCurrentPrice(order.ProductId);
    decimal total = CalculateLineTotal(
        order.Quantity, unitPrice, order.TaxRate);
    string report = RenderReport(order, unitPrice, total);

    File.WriteAllText(reportPath, report);
}
```

There is nothing inherently wrong with this version. It may be the clearest for many C# programs, but it starts the workflow as soon as the method is called.

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

The two `Map` calls treat parsing, calculation, and rendering as pure transformations. The two `FlatMap` calls handle points where a result determines the next effectful computation.

Constructing this pipeline performs no effects; it describes the dependency order:

```text
read -> parse -> fetch price -> calculate -> render -> write
```

When run, `FlatMap` follows those dependencies from left to right. The read must produce text before parsing, and the request must produce a price before calculation.

## How do you run the damn thing?

Part 1 asked how to get values out of monads. For this tiny `IO<T>`, `UnsafeRun()` is the answer, but normally only at the application's edge.

Construct the program, then run it at the application boundary:

```csharp
IO<Unit> program = LoadOrderAndWriteReport(
    remotePriceApi,
    "order.json",
    "report.txt");
// None of the stored operations has run.

Unit completion = program.UnsafeRun();
```

On a successful run, that one call reads the order, fetches the price, calculates and renders the report, and writes the file in the sequence encoded by `FlatMap`.

Calling `UnsafeRun()` again repeats the workflow: it re-reads the file, re-fetches the price, and rewrites the report. An `IO<T>` is repeatable work, not a cached result.

`UnsafeRun()` is a warning label, not memory-unsafe: effects become observable here. Exceptions propagate, later steps do not run, and completed effects are not undone.

Calling `UnsafeRun()` inside a helper performs work before its caller can compose around it. Returning `IO<T>` keeps that choice with the outer caller.

## Monad Laws

`Pure` and `FlatMap` form the monadic core. Just like the `Maybe` laws in Part 1, three laws keep composition predictable:

1. **Left identity:** `IO<T>.Pure(x).FlatMap(f)` behaves the same as `f(x)`. Lifting a value and immediately passing it to the next computation should add no behavior.
2. **Right identity:** `m.FlatMap(x => IO<T>.Pure(x))` behaves the same as `m`. Passing a result through `Pure` should not change the computation.
3. **Associativity:** `m.FlatMap(f).FlatMap(g)` behaves the same as `m.FlatMap(x => f(x).FlatMap(g))`. Regrouping dependent steps should not change their result or effect order.

"Behaves the same" is not wrapper reference equality: successful runs return equal results and perform the same effects in the same order. Runtime diagnostics, such as allocations and exception stack traces, are outside that observation.

These comparisons assume equivalent starting state and that `f` and `g` only construct non-null `IO` values without throwing, calling `UnsafeRun()`, or performing other observable work. C# does not enforce those restrictions, so violating them can break the equivalences.

## Conclusion

A function returning the `T` produced by an effect must perform it first; returning `IO<T>` can instead describe how to produce it later.

`Delay` suspends work, `Map` transforms its result, `FlatMap` composes dependent steps, and `UnsafeRun()` makes effects observable. This does not make file access or API requests pure. Keep pure calculations as ordinary functions, return `IO<T>` from effectful helpers you want to defer, and run the composed program near the application boundary.

This synchronous teaching model is not a replacement for the `Task`-based Asynchronous Pattern or normal C# application structure. As an exercise, implement it without AI assistance and use a counter to show that construction, `Map`, and `FlatMap` remain cold while every `UnsafeRun()` invokes the operation again.
