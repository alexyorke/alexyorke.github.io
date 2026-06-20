---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO makes effectful computations explicit so they can be composed before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

So far in this series, the functions passed to `Map` and `FlatMap` have mostly been pure. They transformed values from immutable inputs, and their observable contribution was the value they returned. Replacing a pure call with its result does not change the rest of the program.

In ordinary procedural code, execution is immediate. When the statement runs, the operation runs, and the programmer usually controls that sequence directly:

```csharp
var scores = new List<RiskScore>();

foreach (var customer in customers)
{
    RateLimit();

    var score =
        riskApi.GetCurrentScore(
            customer.Id);

    scores.Add(score);
}
```

That style is natural for effectful work. The loop decides when the request runs, how often it runs, and where rate limiting or error handling belongs.

Real programs need those kinds of effects. They read files, write to databases, call HTTP APIs, and interact with the external world. For an effectful computation, invoking it is part of the outcome in addition to any returned value.

For example:

```csharp
public static RiskScore GetRiskScore(
    Customer customer)
{
    return riskApi.GetCurrentScore(
        customer.Id);
}
```

If you call `GetRiskScore` directly in a loop, you control that policy yourself. Once you pass it to another abstraction, the abstraction owns the application rule:

```csharp
List<RiskScore> scores =
    customers.Map(GetRiskScore);

Maybe<RiskScore> score =
    maybeCustomer.Map(GetRiskScore);
```

The list may apply the function many times. `Maybe` may skip it. Another abstraction might defer it, batch it, or otherwise change when callbacks run. That is fine for pure computations because only the returned value matters. For effects, invoking the function is also part of the outcome, so the execution policy matters too.

`IO<T>` changes the operation from "perform the effect and return `T`" to "construct a program that may later perform the effect and return `T`." The program can still compose those operations, but it does not have to commit to their execution policy yet.

```csharp
IO<Unit> program =
    BuildReportProgram(
        "order.json",
        "report.txt");

// No file has been read.
// No service has been called.
// No report has been written.
```

`program` is a value describing the work. The work begins only when the program is interpreted:

```csharp
program.Run();
```

In this article, we will use `Run()`, although a real program is typically interpreted automatically from `Main` or another outer boundary. Using `Run()` is more explicit for teaching purposes; in practice, you usually would not call it directly.

The examples use C#-style code to make the ideas concrete. The `IO<T>` implementation is synchronous teaching code, not a recommendation to replace idiomatic C#.

## Pure calculations and effects

Consider a pure calculation:

```csharp
public static decimal ConvertToUsd(
    decimal amount,
    decimal exchangeRate)
{
    return amount * exchangeRate;
}
```

Given the same immutable inputs, `ConvertToUsd` returns the same value. Conceptually, it could be replaced by a lookup table.

Repeating the calculation may waste processor time, but it does not create another program-visible event. It does not append another line, consume service quota, advance a cursor, or affect what the next invocation returns.

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

The second call is another interaction, not merely another calculation.

Even if both requests return the same number, two requests may consume more quota, produce two audit records, or encounter different rate limits.

The distinction is clearer for a write:

```csharp
File.WriteAllText(
    "report.txt",
    report);
```

The useful outcome is the write itself. Discarding a return value does not undo the interaction.

For a pure computation, the program usually cares about the resulting value. For an effectful computation, the returned value may matter, but execution itself is also part of the outcome.

## The implicit `World`

One way to model an effect is to imagine an additional input:

```csharp
public static string ReadOrderJson(
    string path
    /*, World world */)
{
    // Conceptually:
    //
    // return world.FileSystem
    //     .ReadAllText(path);

    return File.ReadAllText(path);
}
```

`World` is not a proposed C# class. It represents the files, databases, clocks, services, mutable objects, concurrent processes, and other external state available when the operation runs.

`World'` represents the world after the interaction.

A read observes external state. Depending on the capability, it may also advance a cursor, populate a cache, acquire a lock, create an audit record, or consume quota. A write changes external state more directly.

If the complete world were available as an immutable input and the transition were deterministic, the result and next world could in principle be predicted. Real programs do not receive such a value. They discover part of the world by performing an effect.

`World` is therefore a model for dependency and ordering, not a literal snapshot of the universe. Sequencing two effects does not guarantee that an external system remains unchanged between them.

## Hidden effects inherit the surrounding rule

When a function is passed to `Map` or `FlatMap`, the surrounding type applies it according to its own rule.

The types from the previous articles use different rules:

- `List` applies a function to each item.
- `Maybe` applies it only when a value is present.
- `Result` applies it only after success.

These rules are part of the meaning of each type. They are not arbitrary scheduling decisions.

Pure functions fit them naturally because applying the function introduces no hidden interaction. Its contribution is the returned value.

Suppose, however, that this apparently ordinary function calls an API:

```csharp
public static RiskScore GetRiskScore(
    Customer customer)
{
    return riskApi.GetCurrentScore(
        customer.Id);
}
```

Its type appears to be:

```text
Customer -> RiskScore
```

Mapping it over a list makes the list traversal an API execution plan:

```csharp
List<RiskScore> scores =
    customers.Map(GetRiskScore);
```

If the list contains ten thousand customers, the traversal makes ten thousand service calls. The implementation may be well defined and sequential, but several decisions have now been combined:

- which customers participate;
- when the requests begin;
- how many requests occur;
- how failures are retried;
- whether calls are throttled;
- whether returned values are cached.

The list has not behaved incorrectly. The effect was hidden inside what looked like an ordinary value transformation.

Retry can be placed inside the supplied function:

```csharp
List<RiskScore> scores =
    customers.Map(customer =>
        Retry(
            () => riskApi.GetCurrentScore(
                customer.Id),
            attempts: 3));
```

This can work, but execution and policy are now fixed inside the traversal. The caller cannot first obtain a value describing the complete collection of requests and then decide how those requests should run.

Other surrounding rules create similar consequences. An effect inside `Result.Map` is skipped on error. An effect inside a deferred `IEnumerable<T>` selector occurs during enumeration and may occur again during a second enumeration.

The issue is not that these abstractions cannot perform effects. The issue is that hiding an effect inside `A -> B` couples its execution to an application rule that does not express the effect's full operational contract.

## Make the effect part of the type

Represent the API request explicitly:

```csharp
public static IO<RiskScore> GetRiskScoreIO(
    Customer customer)
{
    return IO<RiskScore>.From(() =>
        riskApi.GetCurrentScore(
            customer.Id));
}
```

The type is now:

```text
Customer -> IO<RiskScore>
```

Calling `GetRiskScoreIO` constructs a represented request. It does not call the service.

Mapping over the customers therefore constructs a list of programs:

```csharp
List<IO<RiskScore>> requests =
    customers.Map(GetRiskScoreIO);
```

The type is:

```text
List<IO<RiskScore>>
```

At this point, no requests have occurred.

The responsibilities are now separated:

- `List` determines which customers participate.
- Each `IO<RiskScore>` represents one request.
- Additional combinators can describe retry or throttling.
- A sequencing operation can combine the requests.
- An interpreter eventually begins execution.

The effect has stopped masquerading as an ordinary returned value. It is now the value being composed.

## A small `IO<T>`

C# can suspend a synchronous operation with a function:

```csharp
Func<string> readOrder =
    () => File.ReadAllText(
        "order.json");
```

At the level used in this article, `IO<T>` is essentially a named thunk with a composition interface. It does not discover a new execution mechanism. It gives suspended effects a distinct type and common operations.

```csharp
public sealed class IO<T>
{
    private readonly Func<T> operation;

    private IO(Func<T> operation)
    {
        this.operation =
            operation
            ?? throw new ArgumentNullException(
                nameof(operation));
    }

    public static IO<T> From(
        Func<T> operation)
    {
        return new IO<T>(operation);
    }

    public static IO<T> Pure(
        T value)
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

    public T Run()
    {
        return operation();
    }
}
```

This implementation is synchronous. `Run` invokes the stored function on the current thread. It does not add background work, concurrency, cancellation, or memoization.

The responsibilities are:

```text
Construct:
    From and Pure

Compose:
    Map and FlatMap

Interpret:
    Run
```

`Run` is not what makes `IO<T>` a monad. `Pure` and `FlatMap` provide the monadic structure. `Run` is the interpreter for this teaching representation.

The type behaves as intended only under an important discipline: constructing an `IO<T>`, and invoking a function passed to `FlatMap`, should construct represented work rather than perform that work immediately. C# cannot enforce that discipline.

`Pure` also does not defer evaluation of its argument. This performs the read before `Pure` is called:

```csharp
IO<string> order =
    IO<string>.Pure(
        File.ReadAllText(
            "order.json"));
```

Deferral requires placing the operation inside a function:

```csharp
IO<string> order =
    IO<string>.From(() =>
        File.ReadAllText(
            "order.json"));
```

## Building one effectful program

First, define a void-like result for operations whose useful outcome is the effect itself:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } =
        new Unit();
}
```

Now represent the primitive effects:

```csharp
public static IO<string> ReadAllTextIO(
    string path)
{
    return IO<string>.From(() =>
        File.ReadAllText(path));
}

public static IO<decimal> FetchExchangeRateIO(
    string currency)
{
    return IO<decimal>.From(() =>
        exchangeRateService.GetCurrentRate(
            currency));
}

public static IO<Unit> WriteAllTextIO(
    string path,
    string contents)
{
    return IO<Unit>.From(() =>
    {
        File.WriteAllText(
            path,
            contents);

        return Unit.Value;
    });
}
```

Parsing and rendering remain ordinary pure functions:

```csharp
public static Order ParseOrder(
    string json)
{
    return OrderParser.Parse(json);
}

public static string RenderReport(
    Order order,
    decimal exchangeRate)
{
    return ReportRenderer.Render(
        order,
        exchangeRate);
}

public static IO<Order> ParseOrderIO(
    string json)
{
    return IO<Order>.Pure(
        ParseOrder(json));
}

public static IO<string> RenderReportIO(
    Order order,
    decimal exchangeRate)
{
    return IO<string>.Pure(
        RenderReport(
            order,
            exchangeRate));
}
```

The larger program now reads as direct `FlatMap` composition:

```csharp
public static IO<string> BuildReportTextProgram(
    string orderPath)
{
    return ReadAllTextIO(orderPath)
        .FlatMap(ParseOrderIO)
        .FlatMap(order =>
            FetchExchangeRateIO(
                order.Currency)
            .FlatMap(exchangeRate =>
                RenderReportIO(
                    order,
                    exchangeRate)));
}
```

The final write remains represented as well:

```csharp
public static IO<Unit> BuildReportProgram(
    string orderPath,
    string reportPath)
{
    return BuildReportTextProgram(
            orderPath)
        .FlatMap(report =>
            WriteAllTextIO(
                reportPath,
                report));
}
```

Constructing this value reads no file, calls no service, and writes no report.

At the boundary, the program decides whether to run it:

```csharp
IO<Unit> program =
    BuildReportProgram(
        "order.json",
        "report.txt");

program.Run();
```

Calling `Run` again repeats the whole program. One-time execution, caching, idempotency, and exactly-once delivery are additional policies, not guarantees supplied by `IO<T>`.

## Combining many effects

Mapping an effectful function over a list produces a list of programs:

```csharp
List<IO<RiskScore>> requests =
    customers.Map(customer =>
        GetRiskScoreIO(customer));
```

Often, the desired result is one program that produces all scores:

```text
IO<List<RiskScore>>
```

The operation that turns:

```text
List<IO<T>>
```

into:

```text
IO<List<T>>
```

is commonly called `Sequence`.

```csharp
public static class IOExtensions
{
    public static IO<List<T>> Sequence<T>(
        this IReadOnlyList<IO<T>> operations)
    {
        return IO<List<T>>.From(() =>
        {
            var results =
                new List<T>(
                    operations.Count);

            foreach (IO<T> operation
                in operations)
            {
                results.Add(
                    operation.Run());
            }

            return results;
        });
    }
}
```

Calling `Sequence` does not run the inner programs. Their `Run` calls are inside the suspended outer operation.

```csharp
IO<List<RiskScore>> allScores =
    requests.Sequence();
```

When `allScores` is interpreted, this implementation executes the requests sequentially and collects their results.

A production asynchronous effect system might offer other explicit policies, such as bounded concurrency.

Mapping an effectful function and then sequencing the resulting programs is commonly called `Traverse`:

```text
List<A>
    + (A -> IO<B>)
    -> IO<List<B>>
```

This is the direct connection between `List` and `IO`. `List` determines which values participate, while `IO` describes when the effects associated with those values are interpreted.

## Interpretation at the edge

As smaller IO programs are combined, a larger part of the application may become one larger `IO` value.

That does not make the application pure or remove its effects. It keeps the effects represented until execution begins.

"Move effects to the edge" means moving final interpretation outward. It does not mean defining every file read or service request in `Main`.

A helper can describe an effect. Another helper can attach retry or validation. A larger function can compose those pieces. The boundary-perhaps `Main`, a request handler, a command dispatcher, or a background worker-selects dependencies and interprets the final program.

That boundary cannot inspect a complete `World` or guarantee that external state is correct. It can establish known preconditions, choose an observation point, request available consistency guarantees, and validate outcomes.

An outer `Run` also cannot inspect an arbitrary stored function and selectively retry one internal operation. Policies such as retry must be attached while that operation is still explicitly represented.

## Limits of the toy type

This implementation demonstrates synchronous suspension and dependent sequencing only.

A production effect type may also need:

- stack-safe interpretation;
- asynchronous execution;
- cancellation;
- resource safety;
- controlled concurrency;
- tracing;
- typed failures.

`IO` and `Result` describe different concerns:

```text
IO<Result<T, Error>>
```

The outer type says that obtaining the value requires an interaction. The inner type describes an expected success or failure. Composing this combined shape ergonomically requires additional operations and is outside the scope of this article.

Production C# normally uses `Task`, `Task<T>`, and `async`/`await` for asynchronous I/O. This toy `IO<T>` isolates a narrower idea: the separation between describing an interaction and interpreting it.

## Conclusion

`IO<T>` does not make an effect pure, safe, asynchronous, or one-shot.

It makes the effect explicit as a composable value.

Suspension preserves the choice not to execute yet. `FlatMap` preserves dependencies between represented effects. An interpreter begins execution. Other combinators can add policies such as retry, caching, resource safety, or concurrency.

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
