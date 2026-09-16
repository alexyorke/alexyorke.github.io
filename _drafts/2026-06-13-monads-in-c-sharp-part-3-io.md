---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> turns effectful work into a cold value. FlatMap composes those values, while UnsafeRun() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

The first two parts used `Map` to transform contextual values and `FlatMap`—called `Bind` in Part 2—to compose steps whose next computation depended on an earlier result. `List`, `Maybe`, and `Result` decided what flowed onward.

The functions that we've discussed previously are called pure functions: they return the same output given the same input, and don't change the world. Here, the "world" means things outside the program, e.g., making an HTTP call, writing to a file or a database, or printing to the screen. Useful programs have to interact with the world in some way. Some functions also read files, ask for input, call APIs, draw to the screen, or change shared state. We call that interaction with the world an **effect**, and a function that performs one an **effectful function**.

So the I-O monad, M-O-N-I-D, is It is one approach to sequence and compose effectful computations in functional programs. The reason why it's one approach is because There are different functional programming languages, for example, non-pure ones that have different ways to compose these sequences. Effects and don't necessarily always need the IO monad and For example, OCaml, which is another programming language, what it does is it uses a semicolor to sequence and cause effects. And for procedural languages like C sharp, for example, it I guess the statement order, except if you're excluding like tasks and threading and such, statement order is what defines when effects run because they run sequence. For OCaml, it's similar. You could use IO monad if you wanted to, but it's not necessary to do them. For Haskell, it's a bit different because the way that it works is it is a pure functional process. Programming language, and the evaluation order is not necessarily specified. It's a lazily evaluated programming language. Because it's pure than, well, by definition, you can't just have effects anywhere. But this shows that the reason why the IO monad is required in that case to sequence and compose effects is because, well, there really isn't an evaluation order. And IO kind of by definition allows creating an I.O. action for the function you want to run. And then next, using map or flat map, for example, compose it with the other operations temporarily afterwards, where the program itself, the main, is the interpreter which runs the IO itself. Is one way of sequencing the effects because the language itself does not have the capability to do that. The reason why you have to, well, the reason why it's useful to have the capability to compose and sequence effects is because effects Typically, but not always, need to be need to run in a specific sequence and may not necessarily have explicit data dependencies between each other. Because they modify the world, which is a bit ambiguous, and Typically you have to run them in a specific order. And it has to be run at a specific time. For example, if you're asking users for an input, you want to have it at a specific time. If you want a con HTTP API, it has to be done after the next one, for instance. And Haskell, for example, evaluation order, it depends on the interpreter, doesn't really matter as long as the output is the same. Is a bit different, the order does matter. Now, you don't necessarily to have a purely functional programming language, you would have to have the IO mona, is my understanding. But for a functional programming language. You don't necessarily need to have one if you want to compose in sequence effects. Depends on what the language is capable of and what it's designed to do in this case and what machinery you have available to do this.

An effect matters even when its return value is discarded. `Console.WriteLine(...)` returns no useful value, but displaying the text is still part of the program. A file write or HTTP request can likewise change the world even if its result is ignored, for example, the data written to a file persists even after the program has closed.

A pure calculation is different. Evaluating and discarding `1 + 1` changes no external state. Repeating or skipping it likewise changes nothing outside the calculation. With an effect, **whether, how often, and in what order** it runs can change the program's meaning.

`IO<T>` is one way to represent effectful work as a value. Think of it as a recipe: construction describes work for later, `FlatMap` composes a result-dependent next IO, and application code chooses where to run the completed workflow.

When you wrap an effectful computation in IO, well, any computation for that matter:

IO.From(() => File.AppendAllText(...))

Nothing happens. It is just a recipe to append all text to that file, and is only executed when explicitly requested.

## Why do we need this IO monad?

Effects are sort of awkward in functional programming, but, we need to have effects, otherwise our programs are not very useful. Let me explain.

In ordinary C#, statement order already gives effects an obvious sequence:

```csharp
File.AppendAllText(path, "first");
File.AppendAllText(path, "second");
```

Assuming both calls succeed, the first append text to the file runs, then the second. Reversing or skipping either call changes the resulting file, if you write "second" first, then, well, your file will have the text "second" appended first. Although the functions return `void`, the calls run for their effects. The act of writing to the file is the effect. Fairly straightforward.

In functional programming, we have a couple useful things: referential transparency, the ability to replace an expression with its value and it returns the same result, and equational reasoning. The issue is that effects, as they are right now, break that model.



If I said:

x = 2 + 9
y = 4
z = y + 4

I want to get the value of z. Do I need to compute x? No, z doesn't depend on x. The issue is, that, if x is an effectful function, say:

x = DoStuff()

Then, well, x doesn't get executed if you only want z. That's an issue, because effectful functions make observable changes to the world; when they run and how often is important and observable. This means its difficult to sequence effects, because it has to run at a certain time, in a certain sequence.

If we enforce statement order, where each function runs one after the other, we'd lose the equational reasoning and referential transparency properties of functional programming, that is, the ability to substitute a value for its expression. We can no longer guarantee it.

Here is a case where the functions are not referentially transparent:

```csharp
int counter = 0;
int Next() => ++counter;

int x = Next();
int reused = x + x;                // 2: one call

counter = 0;
int repeated = Next() + Next();    // 3: two calls
```

`x + x` reuses one value. `Next() + Next()` performs two observable calls. Direct effects therefore make duplication and reordering observable even though useful programs still need them.

`IO<T>` does not make those operations pure. It represents them as deferred computations that can be returned and combined before the outer caller explicitly starts them.

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

Calling `FetchCurrentPriceIO` sends no request. It stores the request-producing function inside an `IO<decimal>`, so the return type signals deferred work rather than an available price.

`Pure` cannot suspend an effectful call because C# evaluates the argument before calling `Pure`:

```csharp
IO<decimal> eager = IO<decimal>.Pure(
    remotePriceApi.GetCurrentPrice(productId));

IO<decimal> deferred = IO<decimal>.Delay(
    () => remotePriceApi.GetCurrentPrice(productId));
```

The request for `eager` has already happened. The lambda passed to `Delay` postpones the request until the resulting IO is run.

## Deferral, composition, and execution are different jobs

`Delay` stores an operation without invoking it. That makes the work a value, but it does not decide its order or how many times it runs.

Suppose a function returning `IO<decimal>` is mapped over an `IO<Order>`. Ordinary `Map` produces `IO<IO<decimal>>`. `FlatMap` avoids that nesting: when the composed computation is run, it runs the source, passes the result to the continuation, and then runs the IO returned or selected by that continuation.

This composes IO with IO, not IO automatically with `List`, `Result`, or `Task`. The stored work does not execute merely because the IO value is returned. Application code starts the completed computation with `UnsafeRun()`.

| Operation | Job |
| --- | --- |
| `Delay` | Defer a delegate body. |
| `Map` | Transform the eventual result with an ordinary function. |
| `FlatMap` | Compose a result-dependent function returning another IO. |
| `UnsafeRun()` | Invoke the stored computation. |

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
- `FlatMap` is deferred because its `UnsafeRun()` calls remain inside the stored delegate. When run, it obtains the first result, asks the continuation to return or select the next `IO`, and runs it.

"Cold" means that construction and composition do not invoke those stored delegate bodies. C# still evaluates receivers and arguments immediately, and this implementation performs null checks and allocations while building the computation, so construction can throw. The `Func` types also cannot enforce the convention that effects remain inside `Delay` delegates rather than in surrounding callers or continuations.

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

Constructing this pipeline does not invoke the stored file or network operations. Its nested delegates encode the dependency order:

```text
read -> parse -> fetch price -> calculate -> render -> write
```

When the composed program is run, `FlatMap` follows those dependencies from left to right. The read must produce text before parsing, and the request must produce a price before calculation.

## How do you run the damn thing?

Part 1 asked how to get values out of monads. For this tiny `IO<T>`, `UnsafeRun()` is the answer, but normally only at an application boundary such as `Main`, a request handler, or a background-worker entry point.

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

Calling `UnsafeRun()` again starts another attempt by invoking the stored delegate anew. If the operations succeed again, it re-reads the file, re-fetches the price, and rewrites the report. The wrapper adds no memoization, but a captured operation may cache internally, be one-shot, return a different result, or fail before later steps are reached.

`UnsafeRun()` is a warning label, not memory-unsafe: this is where the stored computation is invoked. Exceptions propagate, later steps do not run, and completed effects are not undone.

`UnsafeRun()` synchronously invokes the stored delegate on the caller's thread and adds no asynchronous behavior. Keep acquisition, use, and disposal of resources owned by the workflow inside the same delayed scope with [`using`](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/statements/using) or `try`/`finally`. This wrapper supplies no scheduler, cancellation, or thread-safety guarantees, and deeply nested `Map` or `FlatMap` chains may overflow the stack because it has no trampoline.

Calling `UnsafeRun()` inside a helper performs work before its caller can compose around it. Returning `IO<T>` keeps that choice with the outer caller.

## Monad Laws

`Pure` and `FlatMap` form the monadic core. Just like the `Maybe` laws in Part 1, three laws keep composition predictable:

1. **Left identity:** `IO<T>.Pure(x).FlatMap(f)` behaves the same as `f(x)`. Lifting a value and immediately passing it to the next computation should add no behavior.
2. **Right identity:** `m.FlatMap(x => IO<T>.Pure(x))` behaves the same as `m`. Passing a result through `Pure` should not change the computation.
3. **Associativity:** `m.FlatMap(f).FlatMap(g)` behaves the same as `m.FlatMap(x => f(x).FlatMap(g))`. Regrouping dependent steps should not change their result or effect order.

"Behaves the same" is observational, not wrapper reference equality. For freshly constructed programs with equivalent starting state, both sides should have the same termination behavior and relevant effects in the same order and, when they terminate, the same result or equivalent failure. Wrapper identity, allocations, and diagnostic stack traces are outside that observation.

These comparisons require `f` and `g` to be deterministic, total, nonthrowing constructors of non-null `IO` values. During construction they must not read mutable or external state, perform effects, call `UnsafeRun()`, or force the returned IO. They may still return IO values whose stored `Delay` delegates perform effects later. If the comparison includes rerunning the same wrapper, repeated continuation construction must also produce rerun-equivalent computations without fresh hidden mutable state. C# cannot enforce these rules, and the comparison is limited by this interpreter's operational bounds. A failure raised by a stored IO operation is an outcome to compare, not automatically a law violation.

## Conclusion

A function returning the `T` produced by an effect must perform it first; returning `IO<T>` can instead describe how to produce it later.

Use `Delay` to construct deferred effects, `Map` to transform eventual values, `FlatMap` to compose a result-dependent next IO, and `UnsafeRun()` to invoke the composed program at the application boundary. This does not make file access or API requests pure.

This synchronous teaching model is not a replacement for the `Task`-based Asynchronous Pattern or normal C# application structure. As an exercise, build a counter-backed IO and predict the counter after construction, after adding `Map`, after adding `FlatMap`, after the first `UnsafeRun()`, and after a second run. Then compare `Pure(Next())` with `Delay(() => Next())`, and predict which later steps are skipped when one delayed operation throws.
