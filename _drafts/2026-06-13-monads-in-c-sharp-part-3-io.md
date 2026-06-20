---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO makes effectful computations explicit so they can be composed before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

This article continues those two parts. There, the functions passed to `Map` and `FlatMap` were mostly pure calculations. A pure function is determined by its explicit inputs. Conceptually, it could be replaced by a lookup table: the same arguments produce the same result regardless of prior or later calls. Its observable contribution is the value it returns.

That is why the earlier examples could delegate application to the surrounding monad. `List` can apply the function to many values. `Maybe` can skip it. `Result` can stop after an error. For pure computations, that is fine and convenient.

Effectful computations are different. Real programs read files, write to databases, and call HTTP APIs. Here, performing the operation is part of the outcome, even when the operation also returns a value. A file read can fail. A request can consume quota. A write can change what a later read sees. Once that is true, execution policy matters too: when, whether, and how often the effect runs.

In procedural code, execution is immediate. When the statement runs, the operation runs, and the programmer controls that sequence directly:

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

For example:

```csharp
public static RiskScore GetRiskScore(
    Customer customer)
{
    return riskApi.GetCurrentScore(
        customer.Id);
}
```

If you call `GetRiskScore` directly in a loop, you control that policy yourself. If you pass it to another monad or higher-order abstraction, you delegate the application rule:

```csharp
List<RiskScore> scores =
    customers.Map(GetRiskScore);

Maybe<RiskScore> score =
    maybeCustomer.Map(GetRiskScore);
```

The list may apply the function many times. `Maybe` may skip it. Another abstraction might defer it or batch it. That delegation is one of the benefits of these abstractions. For pure computations, only the returned value matters. For effects, invocation matters too.

`IO<T>` changes the operation from "perform the effect and return `T`" to "construct a program that may later perform the effect and return `T`." It defers the computation like a recipe, so the program can still compose those operations without committing to their execution policy yet.

```csharp
IO<Unit> program =
    ReadAllTextIO("order.json")
        .FlatMap(contents =>
            WriteAllTextIO(
                "order-copy.json",
                contents));

// No file has been read.
// No file has been written.
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

Calling it again with the same arguments may waste processor time, but it does not create another program-visible event. It does not append another line, consume service quota, advance a cursor, or affect what the next invocation returns.

Now consider obtaining the exchange rate:

```csharp
public static decimal GetExchangeRate(
    string currency)
{
    return exchangeRateApi.GetCurrentRate(
        currency);
}
```

Assume `exchangeRateApi` reads from an external service.

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

Because the requests are represented explicitly, a later step can decide whether to combine them, delay them, or interpret them under another policy. The effect has stopped masquerading as an ordinary returned value. It is now the value being composed.

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
        this.operation = operation;
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

This is synchronous teaching code. `Run` invokes the stored function on the current thread. It does not add background work, concurrency, cancellation, memoization, or production-grade safety.

`From` and `Pure` construct `IO<T>` values. `Map` and `FlatMap` compose them. `Run` interprets this teaching representation.

`Run` is not what makes `IO<T>` a monad. `Pure` and `FlatMap` provide the monadic structure. `Run` is just the interpreter for this representation.

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
        exchangeRateApi.GetCurrentRate(
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
public static IO<string> LoadOrderAndRenderReport(
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
public static IO<Unit> LoadOrderAndWriteReport(
    string orderPath,
    string reportPath)
{
    return LoadOrderAndRenderReport(
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
    LoadOrderAndWriteReport(
        "order.json",
        "report.txt");

program.Run();
```

Calling `Run` again repeats the whole program. One-time execution, caching, idempotency, and exactly-once delivery are additional policies, not guarantees supplied by `IO<T>`.

## Interpretation at the edge

As smaller IO programs are combined, a larger part of the application may become one larger `IO` value.

That does not make the application pure or remove its effects. It keeps the effects represented until execution begins.

"Move effects to the edge" means moving final interpretation outward. It does not mean defining every file read or service request in `Main`.

A helper can describe an effect. Another helper can attach retry or validation. A larger function can compose those pieces. The boundary, perhaps `Main`, a request handler, a command dispatcher, or a background worker, selects dependencies and interprets the final program.

That boundary cannot inspect a complete `World` or guarantee that external state is correct. It can establish known preconditions, choose an observation point, request available consistency guarantees, and validate outcomes.

An outer `Run` also cannot inspect an arbitrary stored function and selectively retry one internal operation. Policies such as retry must be attached while that operation is still explicitly represented.

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
