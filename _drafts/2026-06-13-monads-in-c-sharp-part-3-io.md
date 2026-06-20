---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO makes effectful computations explicit so they can be composed before they are executed."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

In the previous articles, we passed functions to `Map` and `FlatMap`. Most of those functions were pure: they added numbers, concatenated strings, or transformed one value into another.

An effectful computation is different: it depends on or changes state that is not represented by its ordinary immutable inputs, such as files, clocks, services, or shared mutable state.

Strictly, `Map` is the functor operation. `Pure` and `FlatMap` provide the monadic composition used in this series. I discuss both because they are the operations through which our functions participate in a larger computation.

This article introduces a different kind of computation:

```csharp
IO<string> program =
    BuildReportTextProgram(
        "order.json",
        ReadAllTextIO,
        currency =>
            GetExchangeRateIO(
                exchangeRateService,
                currency));

// No file has been read.
// No service has been called.
```

`program` is not the report. It is a value representing the work required to produce the report.

That distinction is the point of `IO<T>`:

> `IO<T>` makes an effectful computation explicit in the type and keeps it composable before execution.

Three ideas are involved:

1. **Suspension** represents an operation without performing it.
2. **Composition** combines suspended operations while preserving their dependencies.
3. **Interpretation** executes the resulting program.

The toy `IO<T>` in this article demonstrates those ideas synchronously. It is not a production effect system or a recommendation to replace idiomatic C# I/O.

## Values and interactions are different

Consider a pure calculation:

```csharp
public static decimal ConvertToUsd(
    decimal amount,
    decimal exchangeRate)
{
    return amount * exchangeRate;
}
```

For a terminating pure function, immutable inputs determine the output. Given the same `amount` and `exchangeRate`, `ConvertToUsd` returns the same value.

Conceptually, the function could be replaced by a lookup table. Repeating the calculation may waste processor time, but it does not create another program-visible event.

Now consider obtaining the exchange rate:

```csharp
public static decimal GetExchangeRate(
    string currency)
{
    return exchangeRateService.GetCurrentRate(
        currency);
}
```

The visible input can remain unchanged while the result changes:

```csharp
decimal first =
    GetExchangeRate("EUR");

// The service might return 1.08.

decimal second =
    GetExchangeRate("EUR");

// It might now return 1.09,
// time out, or reject the request.
```

The second call is not merely a recalculation. It is another interaction. Even if both calls return `1.08`, two requests may consume more quota, produce two audit records, or encounter different rate limits.

The distinction is sharper for a write:

```csharp
File.WriteAllText(
    "report.txt",
    report);
```

The useful outcome is the write itself. Discarding the method's return value does not undo the interaction.

An effectful computation therefore has more than a returned value. Whether it runs, when it runs, and how often it runs can all matter.

## The implicit `World`

One way to model an effect is to imagine an extra input:

```csharp
public static string ReadOrderJson(
    string path
    /*, World world */)
{
    // Conceptually:
    //
    // return world.FileSystem.ReadAllText(path);

    return File.ReadAllText(path);
}
```

`World` is not a proposed C# class. It is bookkeeping for the files, databases, clocks, services, mutable objects, concurrent processes, and other external state available when the operation runs.

The semantic shape is closer to:

```text
(Path, World)
    -> (JSON or failure, World')
```

`World'` represents the world after the interaction. A read may only observe its source, but it may also advance a cursor, populate a cache, acquire a lock, create an audit record, or consume quota. A write changes external state more directly.

If the complete world were supplied as an immutable value and the transition were deterministic, the output and next world could in principle be predicted. Real programs do not receive such a value. They discover part of the world by performing the effect.

This model describes dependency and ordering. It does not mean that the program receives a literal snapshot of the universe, nor does sequencing two effects guarantee an atomic view of external systems.

## Higher-order operations own application

In synchronous procedural code, a call chooses an execution point:

```csharp
string json =
    File.ReadAllText("order.json");

// If the call returned normally,
// this read has completed.
```

When a function is passed to `Map` or `FlatMap`, another operation applies it according to a defined rule.

The types from the previous articles use different rules:

- `List` applies a function to every item.
- `Maybe` applies it only when a value is present.
- `Result` applies it only after success.

Those rules are part of the meaning of each type. They are not arbitrary scheduling decisions.

Pure functions fit them naturally because the function's program-visible contribution is its returned value. Effects may have stricter invocation requirements that the surrounding operation does not know about: a request may need rate limiting, a write may be unsafe to repeat, or a prompt may need to occur exactly once.

For example, this asks the user once per list item:

```csharp
List<decimal> adjustedAmounts =
    amounts.Map(amount =>
    {
        decimal adjustment =
            ReadAdjustmentFromConsole();

        return amount + adjustment;
    });
```

The number of prompts is now coupled to `List.Map`.

If the program needs one adjustment for the whole list, it should perform one interaction and delegate only the pure calculation:

```csharp
decimal adjustment =
    ReadAdjustmentFromConsole();

List<decimal> adjustedAmounts =
    amounts.Map(amount =>
        amount + adjustment);
```

That is sufficient when this method owns execution. The harder case is when the method should return the combined operation to another part of the program without prompting yet.

A deferred API exposes the same distinction. This LINQ query stores a file read until enumeration:

```csharp
IEnumerable<string> orderJson =
    orderPaths.Select(path =>
        File.ReadAllText(path));
```

Enumerating it later, or enumerating it twice, changes when and how often the reads occur. The API is behaving correctly; the effect has simply inherited the sequence's execution rule.

## What the abstraction must provide

We need an abstraction that can:

- represent an effect without performing it;
- compose an operation whose next step depends on the previous result;
- preserve the declared relative order of those operations;
- leave the start of execution explicit.

C# can provide suspension with a function:

```csharp
Func<string> readOrder =
    () => File.ReadAllText(
        "order.json");
```

This is a thunk: a repeatable recipe for obtaining a value.

At the level used in this article, `IO<T>` is essentially a named thunk with `Map` and `FlatMap`. The wrapper does not discover a new execution mechanism. Its value is that suspended effects receive a distinct type and a common composition interface.

## A small `IO<T>`

```csharp
public sealed class IO<T>
{
    private readonly Func<T> operation;

    public IO(Func<T> operation)
    {
        this.operation = operation
            ?? throw new ArgumentNullException(
                nameof(operation));
    }

    public T Run()
    {
        return operation();
    }

    public static IO<T> Pure(T value)
    {
        return new IO<T>(() => value);
    }

    public IO<TResult> Map<TResult>(
        Func<T, TResult> map)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();

            return map(value);
        });
    }

    public IO<TResult> FlatMap<TResult>(
        Func<T, IO<TResult>> next)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();
            IO<TResult> nextOperation =
                next(value);

            return nextOperation.Run();
        });
    }

    public IO<TResult> Select<TResult>(
        Func<T, TResult> select)
    {
        return Map(select);
    }

    public IO<TResult> SelectMany<TNext, TResult>(
        Func<T, IO<TNext>> next,
        Func<T, TNext, TResult> project)
    {
        return FlatMap(value =>
            next(value).Map(nextValue =>
                project(value, nextValue)));
    }
}
```

This implementation is synchronous. `Run` invokes the stored function on the current thread. It does not add background work, concurrency, cancellation, or memoization.

The three responsibilities are now visible:

```text
Construct:   create an IO program
Compose:     Pure, Map, and FlatMap
Interpret:   Run
```

`Run` is not what makes `IO<T>` a monad. `Pure` and `FlatMap` provide the monadic structure. `Run` is the interpreter for this particular teaching representation.

Haskell's `IO` is abstract and does not expose this public `Run` API; the method exists here to make interpretation visible in C#.

This type behaves monadically only under an important discipline: constructing an `IO<T>`, and invoking a function passed to `FlatMap`, must construct represented work rather than perform that work immediately. C# cannot enforce that discipline.

Actual production effect types also need concerns that this class omits, including stack-safe interpretation, asynchronous execution, cancellation, resource safety, and explicit failure behavior.

## Building one effectful program

First, represent the primitive effects:

```csharp
public readonly struct Unit
{
    public static Unit Value { get; } =
        new Unit();
}

public static IO<string> ReadAllTextIO(
    string path)
{
    return new IO<string>(() =>
        File.ReadAllText(path));
}

public static IO<decimal> GetExchangeRateIO(
    IExchangeRateService service,
    string currency)
{
    return new IO<decimal>(() =>
        service.GetCurrentRate(currency));
}

public static IO<Unit> WriteAllTextIO(
    string path,
    string contents)
{
    return new IO<Unit>(() =>
    {
        File.WriteAllText(path, contents);

        return Unit.Value;
    });
}
```

For focus, assume `OrderParser.Parse` and `RenderReport` are pure, and that parsing succeeds. Typed parse errors are addressed later.

Now compose the effects and pure calculations:

```csharp
public static IO<string> BuildReportTextProgram(
    string orderPath,
    Func<string, IO<string>> readText,
    Func<string, IO<decimal>> getExchangeRate)
{
    return
        from json in readText(orderPath)
        let order = OrderParser.Parse(json)
        from exchangeRate in
            getExchangeRate(order.Currency)
        select RenderReport(
            order,
            exchangeRate);
}
```

The same program in fluent form is:

```csharp
return readText(orderPath)
    .Map(OrderParser.Parse)
    .FlatMap(order =>
        getExchangeRate(order.Currency)
            .Map(exchangeRate =>
                RenderReport(
                    order,
                    exchangeRate)));
```

The query form is C# syntax over `Select` and `SelectMany`; it is not special syntax added by `IO`.

The final write can remain represented as well:

```csharp
public static IO<Unit> BuildReportProgram(
    string orderPath,
    string reportPath,
    Func<string, IO<string>> readText,
    Func<string, IO<decimal>> getExchangeRate,
    Func<string, string, IO<Unit>> writeText)
{
    return BuildReportTextProgram(
            orderPath,
            readText,
            getExchangeRate)
        .FlatMap(report =>
            writeText(
                reportPath,
                report));
}
```

Constructing this value reads no file, calls no service, and writes no report.

At the boundary, the program can select implementations and policies. Assume `Retry` constructs another `IO<T>` that retries only the operation it wraps:

```csharp
Func<string, IO<decimal>>
    getExchangeRateWithRetry =
        currency =>
            Retry(
                GetExchangeRateIO(
                    exchangeRateService,
                    currency),
                attempts: 3);

IO<Unit> program =
    BuildReportProgram(
        "order.json",
        "report.txt",
        ReadAllTextIO,
        getExchangeRateWithRetry,
        WriteAllTextIO);

program.Run();
```

The mechanisms are distinct:

- `IO` suspends and composes the interactions.
- Function parameters make dependencies replaceable.
- `Retry` supplies a repetition policy for one operation.
- `Run` begins interpretation.

The file read is not repeated merely because the exchange-rate request needs another attempt.

Calling `Run` again repeats the whole program. One-time execution, caching, retry limits, and idempotency are additional policies, not guarantees supplied by `IO<T>`.

## Connecting `List` and `IO`

Mapping an effectful function over a list produces a list of programs:

```csharp
List<IO<string>> reportPrograms =
    orderPaths.Map(orderPath =>
        BuildReportTextProgram(
            orderPath,
            ReadAllTextIO,
            currency =>
                GetExchangeRateIO(
                    exchangeRateService,
                    currency)));
```

The type is:

```text
List<IO<string>>
```

Often, the useful result is one program that produces all reports:

```text
IO<List<string>>
```

The operation that turns the first shape into the second is commonly called `Sequence`:

```csharp
public static class IOExtensions
{
    public static IO<List<T>> Sequence<T>(
        this IReadOnlyList<IO<T>> operations)
    {
        return new IO<List<T>>(() =>
        {
            var results =
                new List<T>(operations.Count);

            foreach (IO<T> operation in operations)
            {
                results.Add(operation.Run());
            }

            return results;
        });
    }
}
```

Now:

```csharp
IO<List<string>> allReports =
    reportPrograms.Sequence();
```

The inner `Run` calls are inside the suspended outer operation, so calling `Sequence()` itself performs no effects. When the outer `IO` is interpreted, this implementation runs the programs sequentially.

A production library might also provide bounded-concurrent or parallel variants.

Mapping an effectful function and then sequencing the result is commonly called `Traverse`. This is the direct connection between `List` and `IO`: `List` describes how many values participate, while `IO` describes when the effects that produce them are interpreted.

## Errors and other C# types

`IO` and `Result` describe different concerns:

```csharp
IO<Result<Order, OrderError>>
```

The outer `IO` says that obtaining the result requires an interaction. The inner `Result` describes an expected success or failure.

Composing several values of this combined shape requires additional combinators or a combined effect type. That subject is outside this article; merely nesting the types does not make the ergonomics disappear.

The toy `IO<T>` also differs from several familiar C# types:

| Type | Typical meaning |
|---|---|
| `Func<T>` | A repeatable synchronous recipe |
| `Lazy<T>` | A deferred value, usually memoized |
| `Task<T>` | One asynchronous operation and its completion |
| `Func<CancellationToken, Task<T>>` | A repeatable asynchronous recipe |
| toy `IO<T>` | A named synchronous effect recipe with monadic composition |

Production C# normally uses `Task`, `Task<T>`, and `async`/`await` for asynchronous I/O. The purpose of this toy type is to isolate the distinction between describing an interaction and interpreting it.

## Interpretation at the edge

As smaller IO programs are combined, a larger part of the application may become one larger `IO` value. That does not make the application pure or remove its effects. It keeps the effects represented until execution begins.

"Move effects to the edge" means moving final interpretation outward. It does not mean defining every file read and service call in `Main`.

A helper can describe an individual effect. Another helper can attach retry or validation. A larger function can compose those pieces. The boundary-perhaps `Main`, a request handler, a command dispatcher, or a background worker-selects dependencies and calls the interpreter.

That boundary cannot inspect a complete `World` or guarantee that external state is correct. It can establish known preconditions, choose an observation point, request available consistency guarantees, and validate outcomes.

## Conclusion

`IO<T>` does not make an effect pure, safe, asynchronous, or one-shot.

It makes the effect explicit as a composable value.

Suspension preserves the choice not to execute yet. `FlatMap` preserves dependency order between represented effects. An interpreter begins execution. Other combinators provide policies such as retry, caching, resource safety, or concurrency.

The distinction is:

```text
a value of type T
```

versus:

```text
a computation that may produce T
by interacting with the world
```

Keeping those separate lets the program compose effectful work before committing to its execution.