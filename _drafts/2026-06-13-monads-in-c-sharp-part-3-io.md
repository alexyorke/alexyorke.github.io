---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO makes effectful computations explicit so they can be composed before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

So far in this series, the examples have mostly been computations over values. A `List` may apply a function to many items. A `Maybe` may skip it. A `Result` may stop after an error. In those examples, the supplied functions were pure computations: adding numbers, transforming a successful result, or producing another value from immutable inputs.

Programs are not very useful if they can only transform values in memory. Real programs read files, write to consoles, call databases, send HTTP requests, and update external systems. Those operations are usually called effects.
For a pure computation, the returned value captures its observable behavior: replacing the call with that value does not change the program. For an effectful computation, performing the operation is also part of the outcome. A file read can fail, a service call can consume quota, and a write can affect later reads even if it returns nothing useful. Therefore, whether, when, and how often an effect runs are part of its contract.

Passing a function to Map or FlatMap lets the surrounding type decide how it is applied. If an effect is hidden inside A -> B, that application rule also becomes the effect’s execution policy. For example, mapping over a list may issue one request per item in quick succession, deferred enumeration may delay or repeat requests, and short-circuiting may skip them. This means that _how_ the function is run, what the monad is doing, is now an important implementation detail, which makes composition more difficult.v

Changing the function to A -> IO<B> makes the effect explicit. Calling it builds a representation of the operation rather than performing it. The program can create List<IO<B>> without executing anything, combine those operations with Sequence or Traverse, and execute the resulting IO at a chosen boundary.

IO does not know every retry, rate-limit, or caching policy. It keeps effects deferred long enough for those policies to be composed explicitly before execution.
`IO<T>` is a way to represent that kind of computation as a value before executing it.

```csharp
IO<string> program = ReadOrderFile("order.json")
    .FlatMap(ParseOrder)
    .FlatMap(BuildReportText);

// No file has been read.
// No service has been called.
```

`program` is not the report text. It is a value describing the work required to produce it.

The examples use C#-style code to keep the discussion concrete. They are teaching examples, not an argument that C# applications should adopt an IO monad.

## Values and interactions are different

Consider a pure calculation:

```csharp
public static decimal ConvertToUsd(decimal amount, decimal exchangeRate)
{
    return amount * exchangeRate;
}
```

For a terminating pure function, immutable inputs determine the output. Given the same `amount` and `exchangeRate`, `ConvertToUsd` returns the same value.

That was the style used in Part 1 and Part 2: adding 1 to every item in a list, or transforming a successful `Result`. Those examples were computations over values. If a pure function runs twice, the important thing is still the value it produces.

Conceptually, the function could be replaced by a lookup table. Repeating the calculation may waste processor time, but it does not create another program-visible event.

Now consider obtaining the exchange rate:

```csharp
public static decimal GetExchangeRate(string currency)
{
    return exchangeRateService.GetCurrentRate(currency);
}
```

The visible input can remain unchanged while the result changes:

```csharp
decimal first = GetExchangeRate("EUR");

decimal second = GetExchangeRate("EUR");
```

The second call is not merely another calculation. It is another interaction. Even if both calls return the same number, two requests may consume more quota, produce two audit records, or encounter different rate limits.

The distinction is even sharper for a write:

```csharp
File.WriteAllText("report.txt", report);
```

The useful outcome is the write itself. Discarding the method's return value does not undo the interaction.

An effectful computation therefore has more than a returned value. Whether it runs, when it runs, and how often it runs can all matter. Performing the operation is part of the meaning now, not just a way to obtain a value.

## The implicit `World`

One way to model an effect is to imagine an extra input:

```csharp
public static string ReadOrderJson(string path /*, World world */)
{
    // Conceptually:
    //
    // return world.FileSystem.ReadAllText(path);

    return File.ReadAllText(path);
}
```

`World` is not a proposed C# class. It is bookkeeping for files, databases, clocks, services, mutable objects, concurrent processes, and other external state available when the operation runs.

The semantic shape is closer to:

```text
(Path, World)
    -> (JSON or failure, World')
```

`World'` represents the world after the interaction. A read may only observe its source, but it may also advance a cursor, populate a cache, acquire a lock, create an audit record, or consume quota.

If the complete world were supplied as an immutable value and the transition were deterministic, the output and next world could in principle be predicted. Real programs do not receive such a value. They discover part of the world by performing the effect.

This model explains dependency and ordering. It does not mean that the program receives a literal snapshot of the universe, nor does sequencing two effects guarantee an atomic view of external systems.

## Higher-order functions own invocation

In synchronous procedural code, a direct call chooses an execution point:

```csharp
string json = File.ReadAllText("order.json");

// If the call returned normally,
// this read has completed.
```

At this point, `json` already contains the file contents. The read happened immediately. The caller chose exactly when that interaction occurred.

The previous articles already used a different pattern. `List`, `Maybe`, and `Result` each decide whether and how to apply the functions passed into them.

- `List` may apply one callback to many values.
- `Maybe` may skip it.
- `Result` may stop at the first error.

That abstraction is what makes monadic composition useful. The surrounding type owns callback application. `Maybe` does not ask the callback how it wants to be invoked; it either applies it or skips it. `List` may apply it several times.

Those rules are fine for pure functions because the interesting contribution is the returned value. Effects can have stricter requirements because performing the operation is part of the outcome: a request may need rate limiting, a write may be unsafe to repeat, or a prompt may need to happen exactly once. In those cases, delegating execution to the surrounding type may not match the policy the program actually needs.

If a callback performs effects, then whether it ran, how many times it ran, and where failure handling lives can all matter to later interactions with the world. You can try to hide retry or failure policy inside the callback, but then you start encoding execution concerns into ordinary return values and working around the surrounding monad rather than using its composition rule.

For example, this asks the user once per item:

```csharp
IEnumerable<decimal> adjustedAmounts = amounts.Select(
    amount => amount + ReadAdjustmentFromConsole());
```

The number of prompts is now coupled to the enumeration rule.

If the program needs one adjustment for the whole list, it should perform one interaction and then delegate only the pure calculation:

```csharp
decimal adjustment = ReadAdjustmentFromConsole();

IEnumerable<decimal> adjustedAmounts = amounts.Select(
    amount => amount + adjustment);
```

A deferred API exposes the same issue more clearly. This LINQ query stores file reads until enumeration:

```csharp
IEnumerable<string> orderJson = orderPaths.Select(
    path => File.ReadAllText(path));
```

Enumerating it later, or enumerating it twice, changes when and how often the reads occur. The API is behaving correctly; the effect has simply inherited the sequence's execution rule.

Hiding an effect inside a function passed to one of these surrounding operations makes the structure's application rule double as the effect's execution policy. If a list applies that function to ten thousand values, ten thousand interactions occur according to the list traversal. Retry, throttling, caching, and one-time requirements must then be hidden inside the function or coordinated through additional state.

Returning `IO<T>` changes the operation from "perform the effect and return `T`" to "construct a program that may later perform the effect and return `T`." Mapping a list of inputs to `IO<T>` values now produces a list of programs without running them. A separate `Sequence` or `Traverse` step can combine those programs under an explicit execution policy, and an interpreter eventually starts them.

`IO` is therefore not needed because imperative code cannot perform effects. It is useful when the program needs to compose effectful work before committing to how and when that work executes.

## What `IO<T>` must provide

We need an abstraction that can:

- represent an effect without performing it;
- compose an operation whose next step depends on the previous result;
- preserve the declared relative order of those operations;
- leave the start of execution explicit.

C# can already suspend a synchronous operation with a function:

```csharp
Func<string> readOrder = () => File.ReadAllText("order.json");
```

That is a repeatable recipe for obtaining a value.

At the level used in this article, `IO<T>` is essentially a named recipe with `Pure` and `FlatMap`. The wrapper does not discover a new execution mechanism. Its value is that suspended effects receive a distinct type and a common composition rule.

## A small `IO<T>`

```csharp
public sealed class IO<T>
{
    private readonly Func<T> operation;

    private IO(Func<T> operation)
    {
        this.operation = operation;
    }

    public static IO<T> From(Func<T> operation)
    {
        return new IO<T>(operation);
    }

    public static IO<T> Pure(T value)
    {
        return new IO<T>(() => value);
    }

    public IO<TResult> FlatMap<TResult>(Func<T, IO<TResult>> next)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();

            return next(value).Run();
        });
    }

    public T Run()
    {
        return operation();
    }
}
```

This implementation is synchronous. `Run` invokes the stored function on the current thread. It does not add background work, concurrency, cancellation, or memoization.

You can think of `Run()` here as the manual escape hatch in the toy example. In a real effect system, you would usually return an `IO<T>` outward and let the surrounding interpreter decide when to execute it.

This type behaves as intended only under an important discipline: constructing an `IO<T>`, and invoking a function passed to `FlatMap`, should construct represented work rather than perform that work immediately. C# cannot enforce that discipline.

Actual production effect types also need concerns that this class omits, including stack-safe interpretation, asynchronous execution, cancellation, resource safety, and explicit failure behavior.

## Building one effectful program

First, represent the primitive effects:

```csharp
public static IO<string> ReadOrderFile(string path)
{
    return IO<string>.From(() => File.ReadAllText(path));
}

public static IO<Order> ParseOrder(string json)
{
    return IO<Order>.Pure(OrderParser.Parse(json));
}

public static IO<decimal> FetchExchangeRate(string currency)
{
    return IO<decimal>.From(() =>
        exchangeRateService.GetCurrentRate(currency));
}

public static IO<string> RenderReportText(Order order, decimal exchangeRate)
{
    return IO<string>.Pure(RenderReport(order, exchangeRate));
}

public static IO<string> BuildReportText(Order order)
{
    return FetchExchangeRate(order.Currency)
        .FlatMap(exchangeRate => RenderReportText(order, exchangeRate));
}

public static IO<string> WriteReportFile(string path, string contents)
{
    return IO<string>.From(() =>
    {
        File.WriteAllText(path, contents);

        return path;
    });
}
```

For focus, assume `OrderParser.Parse` and `RenderReport` are pure, and assume parsing succeeds.

`WriteReportFile` returns the path only so the toy example keeps a concrete result type. The interesting effect is still the write.

Now the larger program reads as a sequence of named steps:

```csharp
public static IO<string> ReadAndRenderReport(string orderPath)
{
    return ReadOrderFile(orderPath)
        .FlatMap(ParseOrder)
        .FlatMap(BuildReportText);
}

public static IO<string> BuildAndWriteReport(string orderPath, string reportPath)
{
    return ReadAndRenderReport(orderPath)
        .FlatMap(report => WriteReportFile(reportPath, report));
}
```

Constructing these values reads no file, calls no service, and writes no report.

For simplicity, this article calls `Run()` directly at the boundary:

```csharp
IO<string> program = BuildAndWriteReport("order.json", "report.txt");

program.Run();
```

Running the program performs the read, then the parse, then the exchange-rate request, then the render, then the write.

The pure steps still matter, but they matter as ordinary values inside the larger effectful sequence. `Pure` is how they enter that sequence without becoming immediate world interactions.

Calling `Run` again repeats the whole program. One-time execution, caching, retry limits, and idempotency are additional policies, not guarantees supplied by `IO<T>`.

## Running at the boundary

As smaller IO programs are combined, a larger part of the application may become one larger `IO` value. That does not make the application pure or remove its effects. It keeps the effects represented until execution begins.

"Move effects to the edge" means moving final interpretation outward. It does not mean defining every file read and service call in `Main`.

A helper can describe an individual effect. Another helper can attach retry or validation. A larger function can compose those pieces. The boundary - perhaps `Main`, a request handler, a command dispatcher, or a background worker - selects dependencies and calls the interpreter.

That boundary cannot inspect a complete `World` or guarantee that external state is correct. It can establish known preconditions, choose an observation point, request available consistency guarantees, and validate outcomes.

## Conclusion

`IO<T>` does not make an effect pure, safe, asynchronous, or one-shot.

It makes the effect explicit as a composable value.

Suspension preserves the choice not to execute yet. `FlatMap` preserves dependency order between represented effects. An interpreter begins execution. Other combinators can add policies such as retry, caching, resource safety, or concurrency.

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
