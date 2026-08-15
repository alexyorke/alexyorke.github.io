---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> turns effectful work into a cold value. FlatMap composes those values, while UnsafeRun() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

The first two parts used the same small pattern in different contexts. We lifted values, then used `Map` and `FlatMap`—called `Bind` in Part 2—to compose dependent steps while `List`, `Maybe`, or `Result` decided what flowed onward.

Some functions do more than calculate a value. They read or write files, ask for input, call APIs, draw to the screen, or change shared state. We will call that interaction with the world an **effect**, and a function that performs one an **effectful function**.

Performing an effect can matter even if its return value is discarded. An HTTP request may update a database; a successful file write can remain after the program exits. Effectful behavior can depend on **whether, how often, and in what order** operations run. Appending to a file twice is different from appending once, while evaluating the same pure arithmetic twice changes no external state.

Sometimes the effect is the whole reason for the call. `Console.WriteLine(...)` produces no useful value for the next calculation, but displaying the text is still part of the program. Optimizing away an unused calculation such as `1 + 1` changes no external state; omitting that console write skips the behavior we asked for.

That is especially awkward in a non-strict, purely functional language such as Haskell, where evaluation is closer to solving an equation than following a fixed script. Haskell constrains expression evaluation primarily through data dependencies, so independent expressions may be evaluated in a different order or never evaluated if their values are unnecessary. Those choices are unobservable when they preserve the program's denotation. Once an operation performs an effect, however, whether and when it runs can become visible program behavior.

In ordinary procedural C#, statement order already gives effects an obvious sequence:

```csharp
File.AppendAllText(path, "first");
File.AppendAllText(path, "second");
```

Assuming both calls succeed, the first append runs before the second. Reversing, repeating, or skipping either statement changes the resulting file contents. The calls run _because_ of their effects, even though they return `void`. C# already supplies this sequence; our synchronous `IO<T>` will not teach C# how to order statements. We will ignore asynchronous and multithreaded execution here.

Procedural code therefore gives us an easy answer to "what happens next?": look at the next statement. But that answer ties describing this workflow to executing it. A successful `File.AppendAllText` call performs the append before returning; in this direct form, the caller does not first receive the whole workflow as a value.

The difficulty comes when we want to reason about effectful calls like values. Pure functional programming relies on **referential transparency**: replacing an expression with another expression having the same denotation does not change the program's meaning. In a non-strict language, an unused pure expression may also remain unevaluated. Neither substitution nor omission is generally safe for an effectful expression, because running it again—or not at all—can change both its result and the outside world.

Referential transparency supports **equational reasoning**: we can replace equal pure expressions while preserving program meaning. A terminating pure expression's outcome does not depend on mutable external state, so evaluating it now, later, or more than once does not change externally observable behavior. An effectful call may depend on the state of the world, change that state, or both. Its invocation becomes part of the meaning, not merely an implementation detail.

This is not an argument that effects are bad. A program that never reads input, stores data, or displays output is rarely useful. The problem is that we need effects while also wanting a predictable way to compose them. We need to say which work depends on earlier results without accidentally performing that work while assembling the program.

`IO<T>` addresses that tension by turning **work that could happen later into a value we can return, store, and compose now**. Think of it as a recipe for an effect. `FlatMap` combines those recipes in dependency order, and one explicit call performs the resulting program.

This only works if creating the recipe does not perform the operation being deferred. Constructing an `IO<T>` may validate its arguments, but running it is when the stored operation may interact with the world. That separation gives the outermost caller control over when the composed program starts.

The underlying operation is still effectful. `IO<T>` does not turn a network request into mathematics or make a file write automatically reversible. It gives the effect a value-shaped description and makes the transition from description to execution explicit.

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

This eager mapping invokes the function once for each quantity and collects the results. For the inputs shown, performing this pure calculation immediately introduces no external effect.

The important property is not that the calculation is simple. It is that its explicit arguments determine its outcome and calling it changes no external state. Reusing a successfully computed value does not send a request or mutate shared state.

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

The shape looks harmless, but the sequential `Map` shorthand used here now calls `FetchCurrentPrice` three times immediately, once per element, in list order. If each service call issues an HTTP request, that means three requests. If the second service call throws, the third is never reached. The same product ID may also produce a different price later, and each request may consume quota or affect throttling.

Both mappings accept a function and return a list, but the second function hides an interaction with the world behind its `decimal` result. Its return type says nothing about when the request occurs. Changing invocation frequency does not add external effects to the first mapping, but it can materially change the second.

The list mapping is not doing anything wrong; it owns the rule for invoking its function. That rule was invisible with the pure calculation but is observable with the request. An eager list mapping invokes once per element, the earlier `Maybe<T>` zero or one times, the earlier `Result<TSuccess, TError>` only on success, and our `IO<T>` invokes its stored operation only when run.

Pure functions move comfortably among these contexts because calling them introduces no external effect. With effectful functions, the context becomes an execution policy. It decides whether the function runs and may also determine how many effects occur before a failure stops the computation.

This also breaks ordinary algebraic reasoning. Consider a tiny stateful function:

```csharp
private static int count = 0;

public static int Next()
{
    count++;
    return count;
}
```

Starting from zero, `Next() + Next()` produces `1 + 2`, or `3`. The apparently equivalent `2 * Next()` produces `2` and changes the counter only once. Replacing, repeating, or rearranging the call changed both the returned value and the program's state, so the usual algebraic substitution was not safe.

The difference is even clearer if we evaluate once and reuse the result. `var next = Next(); next + next` returns `2` and leaves the counter at `1`. Substituting the expression for the variable gives `Next() + Next()`, which returns `3` and leaves the counter at `2`. With a pure expression those forms would be equivalent; with an effectful call they describe different programs.

A remote request has the same problem, even when the mutation is less obvious. Repeating it may consume more quota, moving it may send data before validation, and skipping it may omit an audit record. Effectful functions are not defective functions; we just cannot reason about their calls as though they were ordinary values.

`IO<T>` does not make those eventual operations pure. It can move each call behind a value that says, "Here is how to perform this later." If constructing that value does not perform the deferred operation, we can pass it around and use `FlatMap` to record dependencies without triggering that operation.

`FlatMap` matters because later work often needs an earlier result. We cannot fetch a product's price until we know its ID, and we cannot render a report until we have the price. Composing those steps records their dependency order without performing any of them yet.

This `IO<T>` is **cold**: its stored operation does not run merely because the value exists. The value can be returned from a helper, stored in a variable, or combined into a larger value. Invoking the stored operation remains a separate decision made by the code that eventually runs it.

This separation is especially useful in non-strict languages such as Haskell, where unused expressions may never be evaluated. Haskell represents `IO` actions as values, and a program's `main` binding has an `IO` type. Ordinary C# method calls are eager, and C# specifies left-to-right operand and argument evaluation, so this tiny `IO<T>` borrows the separation between describing and performing work rather than fixing C#'s execution rules.

The practical shift is small but important: instead of asking a helper to perform an effect and return its result, ask it to return a value describing how to produce that result. We can then build the workflow one dependent operation at a time and run the whole thing at the application boundary.

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

Calling `FetchCurrentPriceIO` performs argument validation, but it does not send a request. It stores the request-producing function inside an `IO<decimal>`. The return type now tells callers that they received deferred work rather than an already available price.

Now the eager list can map over the same product IDs:

```csharp
List<IO<decimal>> requests =
    productIds.Map(productId =>
        FetchCurrentPriceIO(remotePriceApi, productId));
```

The list still maps immediately. It calls `FetchCurrentPriceIO` three times and creates three `IO<decimal>` values, but none of the stored API calls has run. We changed what the function returns, not how the list works.

Nothing mystical is happening: `IO<T>` is a deliberately named wrapper around a `Func<T>`. `Delay` only stores that delegate; it is unrelated to `Task.Delay` and does not schedule the work or move it to another thread.

There is one easy mistake to make here. Passing an effectful call to `Pure` is already too late:

```csharp
IO<decimal> notSuspended =
    IO<decimal>.Pure(
        remotePriceApi.GetCurrentPrice(productId));
// GetCurrentPrice is invoked before Pure can receive a decimal.
```

C# evaluates method arguments before calling the method. `Pure` can wrap the resulting price, but it cannot undo the request that produced it. Use `Delay` when producing the value is itself the work you want to postpone.

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

Three details are worth calling out:

- Part 1 used `Unit` for the operation that lifts a value. Here that operation follows another convention and is named `Pure`. The `Unit` *type* is a separate idea: a one-value stand-in for `void`, used when an effect has no interesting result beyond completion.
- `FlatMap` is deferred. Its calls to `UnsafeRun()` remain inside the delegate stored by the new `IO<TResult>`, so composing values performs none of the stored work. When run, it obtains the first result, constructs the dependent `IO`, and runs that next.
- The wrapper does not memoize. Every `UnsafeRun()` invokes the stored delegate again, so its effects and result may differ on each run.

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

There is nothing inherently wrong with this version. For many C# programs it is the clearest code. It starts performing the workflow as soon as the method is called.

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

`Map(ParseOrder)` is appropriate because parsing is intended to be a pure transformation from text to an order. The inner `Map` likewise treats calculation and rendering as pure transformations. The two `FlatMap` calls are where a result determines the next effectful computation.

Constructing this pipeline reads no file, sends no request, and writes no report. It creates one value that describes the dependency order:

```text
read -> parse -> fetch price -> calculate -> render -> write
```

If the composed value is run, `FlatMap` performs those steps from left to right. The read must produce text before parsing can happen, and the price request must produce a price before the total can be calculated.

## How do you run the damn thing?

Part 1 asked how to get values out of monads. With this tiny `IO<T>`, `UnsafeRun()` is the answer, but you normally want to postpone that answer until the edge of the application.

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

Calling `UnsafeRun()` a second time starts another attempt at the whole workflow. If each stage succeeds, it re-reads the file, re-fetches the price, and rewrites the report. An `IO<T>` is not a cached result; it is repeatable work.

The name `UnsafeRun()` does not mean memory-unsafe. It is a warning label: this is the point where the program stops merely describing effects and starts making them observable. If an operation throws, the exception propagates, later steps do not run, and effects that already happened are not automatically undone.

If a helper calls `UnsafeRun()` in the middle of your call graph, it has already performed that part of the program before its caller can compose anything around it. Returning `IO<T>` keeps that choice with the outer caller.

## Monad Laws

`Pure` and `FlatMap` form the monadic core. Just like the `Maybe` laws in Part 1, three laws keep composition predictable:

1. **Left identity:** `IO<T>.Pure(x).FlatMap(f)` behaves the same as `f(x)`. Lifting a value and immediately passing it to the next computation should add no behavior.
2. **Right identity:** `m.FlatMap(x => IO<T>.Pure(x))` behaves the same as `m`. Passing a result through `Pure` should not change the computation.
3. **Associativity:** `m.FlatMap(f).FlatMap(g)` behaves the same as `m.FlatMap(x => f(x).FlatMap(g))`. Regrouping dependent steps should not change their result or effect order.

"Behaves the same" is not a claim about wrapper reference equality. In this teaching model, it means that successful runs return equal results and perform the same effects in the same order. Object allocation, exception stack traces, and other runtime diagnostics are outside that chosen notion of observation.

There is an important C# caveat. These comparisons assume each side starts from equivalent state and that `f` and `g` only *construct* non-null `IO` values without throwing, calling `UnsafeRun()`, or performing other observable work. C# does not enforce those restrictions. If a continuation violates them, the stated equivalences need not hold.

## Conclusion

A synchronous function that directly returns the `T` produced by a synchronous effect must perform that effect before returning the value. A function that returns `IO<T>` can instead construct a cold value describing how to produce it later. `Delay` suspends the work, `Map` transforms its eventual result, `FlatMap` composes dependent steps, and `UnsafeRun()` marks the point where the deferred computation is allowed to interact with the world.

This does not make file access or API requests pure, nor does it make ordinary procedural C# wrong. Keep pure calculations as ordinary functions, return `IO<T>` from effectful helpers you want to defer, compose without forcing those values, and call `UnsafeRun()` near the application boundary.

This is a synchronous teaching model, not a replacement for the `Task`-based Asynchronous Pattern or normal C# application structure. As an exercise, implement `IO<T>` without AI assistance and use a counter to prove that construction, `Map`, and `FlatMap` do not invoke the stored operation while every `UnsafeRun()` invokes it again.
