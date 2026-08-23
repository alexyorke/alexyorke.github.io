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

Useful programs need effects; without output, storage, or communication, they are just black boxes that get warm while computing with no output or indication that a computation occured.

A pure calculation is different. Evaluating and discarding `1 + 1` changes no external state. Repeating or skipping it likewise changes nothing outside the calculation. With an effect, **whether, how often, and in what order** it runs can change the program's meaning.

The IO monad is one way to sequence and compose effectful computations, sort of like recipes or deferred computations in functional programming. Sure that's great and all, but what are effectful computations, why do we need to sequence them, and _why_ do we need an IO monad for this? Why are effects so special?

## Why do we need this IO monad?

In ordinary procedural programming, using the familar C# language as a stand-in, statement order already gives effects an obvious sequence:

```csharp
File.AppendAllText(path, "first");
File.AppendAllText(path, "second");
```

Assuming both calls succeed, the first append runs before the second. Reversing or skipping either call changes the file. Although they return `void`, the calls run for their effects; the next statement answers "what happens next?" Pretty standard.

Functional programming often reasons about expressions more like algebra. This changes the execution model a lot from next-next-next to something a lot different. Consider:

```text
x = 2
y = x + 4
z = x + y + 1
```

Replacing `x` with `2`, or `y` with `x + 4`, leaves `z` with the same resultant value if it were to be evaluated. This is **referential transparency**: replacing an expression with its value preserves meaning. It supports **equational reasoning**, where equal expressions can be substituted as in algebra. I mean, it's algebra.

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

`z` is never evaluated. Why would it need to be? It's not used. With an effectful expression, however, evaluation itself changes the world. Recall that evaluating the file append text function earlier, even though it didn't have a result that was used, well, it was still evaluated.

Procedural programming behaves differently:

```
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

Although `z` is unused, its initializer still runs—and prints—because C# evaluates the statement eagerly. The result is discarded, but the effect remains, the effect here is the writing-to-screen part.

Effectful functions also resist substitution:

```
x = ReadFile(...) // let's say this returns "2" this time
y = ReadFile(...) // could return "2" or "3" or anything else, depends on the file
z = x + y
```

Doesn't have to be a file, could be an HTTP API, database, etc.

Effects make substitution observable: two file reads may return different values, so replacing `x + y` with `2 * x`, even though x and y refer to the same function, can change the program. Wouldn't that be disasterous for algebra, not even sure if you could call it algebra anymore.

It would be pretty brutal for algebra, where you cannot say that:

x = 2
y = x + 4
z = x + x
a = x + x

a != z

We can't say a == z because evaluating x could, theoretically, be different each time. Eeeeeeeah.

Yikes. This can make reasoning about programs more difficult. Or what if you needed to know how many times "x" was used in previous calculations? Yikes is right.

So, we need effects, but effects are a bit awkward. When they run, how often, in what sequence, etc. _is_ their output so to speak. This makes it complicated when referential transparency, equational reasoning, etc. is to be preserved.

Instead, `IO<T>` represents effectful work as a deferred recipe. `FlatMap` composes recipes in dependency order, and the outer caller starts it. The operations remain effectful; only their execution is postponed.

When we defer execution of IO, this allows us to sequence and compose it, i.e., the primary things that made it awkward and difficult to do in functional programming. Sequencing is the act of making it run in a specific sequence. In procedural programming, the sequence was defined by statement order, in functional programming it may not be so.

## Return the work instead of doing it

In this example, `FetchCurrentPrice` calls the API before it can return a `decimal`. To separate construction from execution, return an `IO<decimal>` instead:

```csharp
public static IO<decimal> FetchCurrentPriceIO(
    IRemotePriceApi remotePriceApi,
    string productId)
{
    return IO<decimal>.Delay(
        () => remotePriceApi.GetCurrentPrice(productId));
}
```

Calling `FetchCurrentPriceIO` validates its arguments but sends no request. It stores the request-producing function inside an `IO<decimal>`, so the return type signals deferred work rather than an available price.

## Why does deferring IO make it composable and sequencable?

When we defer IO, it allows it to be composed with other monads. The order of which it is composed allows it to run at the right time, and at the right frequency.

For example:

list.Map(...).FlatMap(...)

The map is responsible for calling f, that's all it knows. This recipe is in effect being applied to the functions that are called, thereby sequencing the IO. After this, then do that. Nothing happens until its executed, typically you don't execute it yourself, you just return the whole composition/monad thing to the main program which executes it for you. It's like writing a list of instructions, executed one-by-one in the order you desire.

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
