---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO makes effectful computations explicit so they can be composed before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

This article builds on the previous two. TL;DR: useful programs need effects so their results can be observed. `IO<T>` does not remove those effects; it keeps effectful computations composable while leaving control over execution strategy at the boundary, where that strategy can change the outcome in a way pure functions do not.

In those articles, the functions passed to `Map` and `FlatMap` were mostly pure functions. A pure function depends only on its explicit inputs: given the same arguments, it produces the same result regardless of external state or call history.

```csharp
public static int Add(int x, int y)
{
    return x + y;
}

int first = Add(2, 4);   // 6
int second = Add(2, 4);  // 6
```

If we throw away `first`, the earlier call still does not change the later answer. The next call is still `6`.

An effect, in this article, is an operation whose interaction with the outside world is part of what the program does: printing text, reading a file, writing data, or calling an API.

```csharp
public static void AppendLine(string path, string line)
{
    File.AppendAllText(path, line + Environment.NewLine);
}

AppendLine("log.txt", "hello");
AppendLine("log.txt", "hello");
// log.txt now contains two lines
```

Call `AppendLine("log.txt", "hello")` once and the file gains one line. Call it twice and the file gains two. Another process may also change or lock the file in between. Even a later read from the same path may now produce a different result.

Once an operation touches the world, later calls depend on what happened before: whether the file was already changed, whether an API was already called, or whether rate limits, retries, or delays now apply. An HTTP request often needs a specific calling pattern if you want later requests to succeed.

That is why the earlier examples could let the surrounding monad decide how and whether the function is called. `List` can apply the function to many values. `Maybe` can skip it. `Result` can stop after an error. For pure functions, that stays compatible with composition because only the returned value matters.

With effects, the act of running the operation is also part of the outcome. In this article, execution policy means the rule for when, whether, in what order, and how often the effect runs. For `Add`, changing that policy usually does not change the answer. For `AppendLine`, previous runs become part of what later operations observe. If you blast a service with requests, later calls may time out or hit a rate limit. If you append to a file ten thousand times, that is a different outcome than appending once.

Once those choices matter, ordering and repetition have become part of the operation's contract. Different monads bring different application rules, and those rules may not match how an effectful operation needs to run. You could invent a special monad for one callback, or bury retry and throttling inside the callback itself, but then callers have to know hidden policy details and the function stops composing cleanly. `IO<T>` takes a different route: it returns a description of the work first, and the boundary decides when to run it.

In straightforward procedural code, execution is usually immediate. When the statement runs, the operation usually runs too, and the programmer controls that sequence directly:

```csharp
var scores = new List<RiskScore>();

foreach (var customer in customers)
{
    RateLimit();
    var score = riskApi.GetCurrentScore(customer.Id);
    scores.Add(score);
}
```

That style is natural for effects. In a tiny program, it may be enough. The loop makes the policy visible: where requests run, how often they run, and where rate limiting or error handling belongs. The pressure to represent effects explicitly appears when the program grows and that policy needs to stay composable.

For example:

```csharp
public static RiskScore GetRiskScore(Customer customer)
{
    return riskApi.GetCurrentScore(customer.Id);
}
```

Its visible type is:

```text
Customer -> RiskScore
```

That type does not reveal the difference between an ordinary calculation and an API call. In `customers.Map(GetRiskScore)`, a pure `GetRiskScore` is a value transformation. An effectful `GetRiskScore` is also an execution plan.

If you call `GetRiskScore` directly in a loop, you control that policy yourself. If you pass it to another monad or higher-order abstraction, you delegate the application rule:

```csharp
List<RiskScore> scores = customers.Map(GetRiskScore);
Maybe<RiskScore> score = maybeCustomer.Map(GetRiskScore);
```

The list may apply the function many times. `Maybe` may skip it. Another abstraction might defer it or batch it. That delegation is one of the benefits of these abstractions. For pure computations, only the returned value matters. For effects, invocation matters too.

`IO<T>` can be thought of as a deferred effectful computation: a recipe for work that does nothing until it is run. It makes that difference visible by changing the type:

```text
Customer -> IO<RiskScore>
```

Instead of performing an effect and returning a value, the function returns a value that describes a computation. That computation may later interact with the outside world and produce a result. This lets a program compose effectful work before an outer boundary decides how to execute it.

In LINQ syntax, the same deferred program can be sketched like this once the usual LINQ aliases are available:

```csharp
IO<Unit> program =
    from contents in ReadAllTextIO("order.json")
    from _ in WriteAllTextIO("order-copy.json", contents)
    select Unit.Value;
```

<details>
<summary>Equivalent <code>FlatMap</code> form</summary>

```csharp
IO<Unit> program = ReadAllTextIO("order.json")
    .FlatMap(contents => WriteAllTextIO("order-copy.json", contents));

// No file has been read.
// No file has been written.
```

</details>

`program` is a value describing the work. At this point, no file has been read or written. The work begins only when the program is run, here by calling `Run()`:

```csharp
program.Run();
```

In this article, `Run()` is explicit for teaching purposes. In a real program, the final run point is usually arranged at an outer boundary such as `Main`.

This `IO<T>` implementation is synchronous teaching code, not a recommendation to replace idiomatic C#.

## The implicit `World`

One way to model an effect is to imagine a hidden input and output:

```csharp
public static string ReadOrderJson(string path /*, World world */)
{
    // Conceptually:
    //
    // return world.FileSystem.ReadAllText(path);

    return File.ReadAllText(path);
}
```

Conceptually:

```text
(path, World) -> (contents, World')
```

`World` is not a proposed C# class. It stands for files, databases, clocks, services, mutable objects, and other external state. `World'` is the world after the interaction.

This is only a model for dependency and ordering, not a literal snapshot. Sequencing two effects does not stop an external system from changing between them.

## Make the effect part of the type

The next step is to stop returning the API result directly. Instead, return a value that describes the request, so callers can keep composing it without committing to a calling policy yet.

Represent the API request explicitly:

```csharp
public static IO<RiskScore> GetRiskScoreIO(Customer customer)
{
    return IO<RiskScore>.From(() => riskApi.GetCurrentScore(customer.Id));
}
```

Calling `GetRiskScoreIO` constructs a represented request. It does not call the service.

Mapping over the customers therefore constructs a list of programs:

```csharp
List<IO<RiskScore>> requests = customers.Map(GetRiskScoreIO);
```

Mapping still invokes `GetRiskScoreIO` once per customer, but those invocations only construct `IO` values. At this point, no requests have occurred.

The list still determines which customers participate, but each `IO<RiskScore>` now describes one request as a value. A later step can combine those requests and run them under a chosen policy. The effect is no longer hidden inside an ordinary returned value.

## A small `IO<T>`

At the level used in this article, `IO<T>` is a named thunk with a composition interface.

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

    public IO<TResult> Map<TResult>(Func<T, TResult> map)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();
            return map(value);
        });
    }

    public IO<TResult> FlatMap<TResult>(Func<T, IO<TResult>> next)
    {
        return new IO<TResult>(() =>
        {
            T value = Run();
            IO<TResult> nextOperation = next(value);
            return nextOperation.Run();
        });
    }

    public T Run()
    {
        return operation();
    }
}
```

`From` suspends a function. `Pure` lifts an already-computed value into `IO<T>`. `Map` and `FlatMap` build more suspended computations. `Run` executes one.

This implementation is deliberately limited. It is synchronous, and C# cannot enforce the discipline that constructing an `IO<T>` should describe work rather than perform it immediately.

`Pure` also does not defer evaluation of its argument. This performs the read before `Pure` is called:

```csharp
IO<string> order = IO<string>.Pure(File.ReadAllText("order.json"));
```

Deferral requires placing the operation inside a function:

```csharp
IO<string> order = IO<string>.From(() => File.ReadAllText("order.json"));
```

## Building one effectful program

First, define a void-like result for operations whose useful outcome is the effect itself:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new Unit();
}
```

Now represent the primitive effects:

```csharp
public static IO<string> ReadAllTextIO(string path)
{
    return IO<string>.From(() => File.ReadAllText(path));
}

public static IO<decimal> FetchExchangeRateIO(string currency)
{
    return IO<decimal>.From(() => exchangeRateApi.GetCurrentRate(currency));
}

public static IO<Unit> WriteAllTextIO(string path, string contents)
{
    return IO<Unit>.From(() =>
    {
        File.WriteAllText(path, contents);
        return Unit.Value;
    });
}
```

Parsing and rendering remain ordinary pure functions:

```csharp
public static Order ParseOrder(string json)
{
    return OrderParser.Parse(json);
}

public static string RenderReport(Order order, decimal exchangeRate)
{
    return ReportRenderer.Render(order, exchangeRate);
}

public static IO<Order> ParseOrderIO(string json)
{
    return IO<Order>.Pure(ParseOrder(json));
}

public static IO<string> RenderReportIO(Order order, decimal exchangeRate)
{
    return IO<string>.Pure(RenderReport(order, exchangeRate));
}
```

The larger program now reads as direct `FlatMap` composition:

```csharp
public static IO<string> LoadOrderAndRenderReport(string orderPath)
{
    return ReadAllTextIO(orderPath)
        .FlatMap(ParseOrderIO)
        .FlatMap(order => FetchExchangeRateIO(order.Currency)
            .FlatMap(exchangeRate => RenderReportIO(order, exchangeRate)));
}
```

The final write remains represented as well:

```csharp
public static IO<Unit> LoadOrderAndWriteReport(string orderPath, string reportPath)
{
    return LoadOrderAndRenderReport(orderPath)
        .FlatMap(report => WriteAllTextIO(reportPath, report));
}
```

Constructing this value reads no file, calls no service, and writes no report. At the boundary, the program decides whether to run it:

```csharp
IO<Unit> program = LoadOrderAndWriteReport("order.json", "report.txt");

program.Run();
```

Calling `Run` again repeats the whole program. One-time execution, caching, idempotency, and exactly-once delivery are additional policies, not guarantees supplied by `IO<T>`.

## Running at the edge

As smaller `IO` values are combined, a larger part of the application may become one larger `IO` value. That does not remove effects; it keeps them deferred until execution begins.

"Move effects to the edge" means moving the final `Run()` outward. Helpers can describe effects, larger functions can compose them, and an outer boundary such as `Main` or a request handler decides when to run the final program.

That boundary still cannot freeze the world or selectively retry a hidden operation. Policies such as retry or throttling have to be attached while the relevant operation is still explicitly represented.

## Conclusion

`IO<T>` does not remove effects. It makes them explicit.

The important distinction is between a plain value and a piece of work that may touch the outside world before producing a value. Once that distinction is visible in the type, the program can build effectful work first and decide at the boundary when, whether, and how often to run it.
