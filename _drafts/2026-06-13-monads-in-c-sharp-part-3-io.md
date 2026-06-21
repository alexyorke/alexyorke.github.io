---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO makes effects explicit so they can be composed before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

This article builds on the previous two. In those articles, the functions passed to `Map` and `FlatMap` were mostly pure. A pure function depends only on its explicit inputs: given the same arguments, it produces the same result regardless of external state or invocation history.

This article is about what changes when executing an operation becomes part of the outcome. Programs need effects so results can be observed.

```csharp
public static int Add(int x, int y)
{
    return x + y;
}

int first = Add(2, 4);   // 6
int second = Add(2, 4);  // 6
```

If we throw away `first`, the earlier invocation still does not change the later result. The next invocation is still `6`.

That is why the earlier examples could let the surrounding monad decide how and whether the function is invoked. `List` can apply the function to many values. `Maybe` can skip it. `Result` can stop after an error. For pure functions, that stays compatible with composition because only the returned value matters.

An effect, in this article, is an operation whose interaction with the outside world is part of what the program does: printing text, reading a file, writing data, or issuing an API request.

```csharp
public static void AppendLine(string path, string line)
{
    File.AppendAllText(path, line + Environment.NewLine);
}

AppendLine("log.txt", "hello");
AppendLine("log.txt", "hello");
// log.txt now contains two lines
```

Invoke `AppendLine("log.txt", "hello")` once and the file gains one line. Invoke it twice and the file gains two. Another process may change or lock the file in between. A later read from the same path may now produce a different result.

Once an operation interacts with the world, later invocations depend on what happened before: whether the file was already changed, whether an API was already invoked, or whether rate limits, retries, or delays now apply. A stateful or rate-limited API may need a specific invocation pattern if you want later requests to succeed.

With effects, the act of executing the operation is also part of the outcome. In this article, execution policy means when, whether, in what order, and how often the effect executes. For `Add`, changing that policy usually does not change the result. For `AppendLine`, earlier executions become part of what later operations observe. If you issue requests to an API too quickly, later requests may time out or hit a rate limit. If you append to a file ten thousand times, that is a different outcome than appending once.

Once those choices matter, execution order and repeat count have become part of the operation's contract. Different monads can impose different application policies, and those policies may not match how an effectful operation needs to execute. You could invent a special monad for one callback, or bury retry and throttling inside the callback itself, but then callers have to know hidden policy details and the function loses composability. `IO<T>` uses a different strategy: it returns a description of the computation first, and the boundary decides when to execute it. `IO<T>` does not remove those effects; it preserves composability while leaving control over execution strategy at the boundary.

In straightforward procedural code, execution is often immediate, and the programmer controls that sequence directly:

```csharp
var scores = new List<RiskScore>();

foreach (var customer in customers)
{
    RateLimit();
    var score = riskApi.GetCurrentScore(customer.Id);
    scores.Add(score);
}
```

The loop specifies the policy: where requests execute, how often, and where rate limiting or error handling belongs.

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

That type does not reveal the difference between a calculation and an API request. In `customers.Map(GetRiskScore)`, a pure `GetRiskScore` is a value transformation. An effectful `GetRiskScore` is also an execution plan.

Invoke `GetRiskScore` directly in a loop and you control that policy yourself. Pass it to another monad or higher-order abstraction and you delegate the application policy:

```csharp
List<RiskScore> scores = customers.Map(GetRiskScore);
Maybe<RiskScore> score = maybeCustomer.Map(GetRiskScore);
```

The list may apply the function many times. `Maybe` may skip it. Another abstraction might defer it or batch it. For pure computations, only the returned value matters. For effects, invocation matters too.

The need to represent effects explicitly appears when the program grows and that policy must stay composable.

`IO<T>` can be viewed as a deferred effectful computation: a recipe for a computation that does nothing until it is executed. Constructing or naming one does not begin execution; it only describes later execution. It makes that difference explicit by changing the type:

```text
Customer -> IO<RiskScore>
```

Instead of performing an effect and returning a value, the function returns a value that describes a computation. That computation may later interact with the outside world and produce a result. This lets a program compose effectful computations before an outer boundary decides how to execute them.

A common question is how to extract the `T` from `IO<T>`. In the middle of the program, there is no general safe unwrap. A variable of type `IO<T>` names the described computation, not a finished `T`. `IO<T>` is a recipe, not a box with a finished `T` inside; the result appears only when the effect executes. Until then, keep composing, or return the `IO<T>` outward until a boundary decides to execute it.

In LINQ syntax, the same deferred program can be written like this once the usual LINQ aliases are available:

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

`program` is a value describing the computation. Naming it does not read or write anything. Execution begins only when the program is executed, here by calling `Run()`:

```csharp
program.Run();
```

Here, `Run()` is explicit for teaching purposes. In a real program, final execution is usually at an outer boundary such as `Main`.

> **Note:** This article is not advocating `IO<T>` in production C#. C# is only the teaching language: a familiar procedural language that makes the execution-policy problem concrete without also teaching Haskell syntax.

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

`World` is not a proposed C# class. It denotes files, databases, clocks, services, mutable objects, and other external state. `World'` is the world after the interaction.

This is only a model for dependency and ordering, not a literal snapshot. It is useful because it makes the changing environment explicit in the model, even though ordinary C# does not pass a real `World` value around. Sequencing two effects does not stop external systems from changing between them.

## Make the effect part of the type

The next step is to stop returning the API result directly. Instead, return a value that describes the request, so callers can keep composing it without committing to an invocation policy.

Represent the API request explicitly:

```csharp
public static IO<RiskScore> GetRiskScoreIO(Customer customer)
{
    return IO<RiskScore>.From(() => riskApi.GetCurrentScore(customer.Id));
}
```

Calling `GetRiskScoreIO` constructs a request description. It does not issue the request.

Mapping over the customers constructs a list of computations:

```csharp
List<IO<RiskScore>> requests = customers.Map(GetRiskScoreIO);
```

Mapping still invokes `GetRiskScoreIO` once per customer, but those invocations only construct `IO` values.

The list still determines which customers participate, but each `IO<RiskScore>` now describes one request as a value. `requests` is still a collection of descriptions, not completed scores. `List<IO<RiskScore>>` is not the same type as `IO<List<RiskScore>>`: one is many request descriptions, while the other is one larger described computation. A later step can combine them into `IO<List<RiskScore>>` and execute them under a chosen policy. The effect is no longer hidden inside an ordinary returned value.

## A small `IO<T>`

Here, `IO<T>` is a named thunk with a composition interface.

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

`From` defers a function. `Pure` injects an already-computed value into `IO<T>`; it does not execute an effect or extract anything from `IO<T>`. `Map` applies pure logic to the eventual value, while `FlatMap` is for the dependent case where the next step also returns `IO`. `Run` executes one.

This implementation is intentionally limited. It is synchronous, and C# cannot enforce that constructing an `IO<T>` should describe computation rather than execute it immediately.

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

Now represent the basic effects:

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

Parsing and rendering remain pure functions:

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

The composed program:

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

Constructing this value performs no file read, no service request, and no report write. At the boundary:

```csharp
IO<Unit> program = LoadOrderAndWriteReport("order.json", "report.txt");

program.Run();
```

Calling `Run` again re-executes the whole program. One-time execution, caching, idempotency, and exactly-once delivery are additional policies, not guarantees of `IO<T>`.

## Running at the edge

As smaller `IO` values are combined, a larger part of the application may become one larger `IO` value. That does not remove effects; it keeps them deferred.

"Move effects to the edge" means moving the final `Run()` outward. Helper functions can describe effects, larger functions can compose them, and an outer boundary such as `Main` or a request handler decides when to execute the final program.

That boundary still cannot freeze the world or selectively retry a hidden operation. Policies such as retry or throttling have to be attached while the relevant operation is still explicit.

## Conclusion

`IO<T>` does not remove effects. It makes them explicit.

The important distinction is between a plain value and a computation that may interact with the outside world before producing a value. Once that distinction is visible in the type, the program can decide at the boundary when, whether, and how often to execute it.
