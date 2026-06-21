---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO makes effects explicit so they can be composed before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

> **Note:** This article is not recommending `IO<T>` for production C#. C# is only the teaching language here: it makes the execution-policy problem concrete without also introducing Haskell syntax at the same time.

This article builds on the previous two. Earlier in the series, many of the small teaching examples passed pure functions to `Map` and `FlatMap`, although Part 2 already mixed in repository lookups and pragmatic mutation. A pure function depends only on its explicit inputs: given the same arguments, it produces the same result, and calling it causes no side effects.

This article is about what changes when running an operation can affect what later code or the outside world observes, even when the explicit inputs stay the same.

```csharp
public static int Add(int x, int y)
{
    // Pure function: the result depends only on x and y,
    // and calling it causes no other changes.
    return x + y;
}

int first = Add(2, 4);   // 6
int second = Add(2, 4);  // 6
```

If we throw away `first`, nothing observable changes. The next invocation is still `6`.

That is why the earlier examples could let the surrounding monad, meaning the type that controls how the function gets applied, decide how to apply the function. The list monad can apply the function to many values. The maybe monad can skip it. The result monad continues with later mapped steps only after success; once a failure value is present, later steps are skipped. For pure functions, that stays compatible with composition because only the returned value matters.

An effect is an operation whose interaction with the outside world is part of what the program does. Useful programs eventually need effects, otherwise no result is ever read, displayed, saved, or sent anywhere. Running an effect can change what later operations or external systems observe, even when you make the same explicit request a second time.

```csharp
public static RiskScore GetRiskScore(Customer customer)
{
    return riskApi.GetCurrentScore(customer.Id);
}

RiskScore firstScore = GetRiskScore(customer);
RiskScore secondScore = GetRiskScore(customer);
```

Calling `GetRiskScore(customer)` twice is not like calling `Add(2, 4)` twice. The request might time out, consume quota, hit a rate limit, or return a different score on the second call even with the same customer.

With effects, execution policy becomes important: when the operation runs, whether it runs at all, in what order it runs, and how often it runs. Later effectful steps may depend on whether earlier ones already ran, whether they succeeded, and what state they left behind, so those choices become part of the outcome.

The problem is not that monads cannot express execution policy. The problem is that each surrounding monad already comes with its own way of applying and sequencing functions. For effectful computations, the surrounding monad's policy may no longer match what the effect needs.

`IO<T>` changes `Customer -> RiskScore` into `Customer -> IO<RiskScore>`. Instead of performing the request immediately, the function returns a recipe for a request that can be run later. `IO<T>` names a computation to run later, not a finished `T` waiting inside.

```text
Customer -> IO<RiskScore>
```

In straightforward procedural code, execution is often immediate, and the programmer usually controls that sequence directly:

```csharp
var scores = new List<RiskScore>();

foreach (var customer in customers)
{
    RiskScore score;

    try
    {
        score = riskApi.GetCurrentScore(customer.Id);
    }
    catch (TransientRiskApiException)
    {
        // Toy example: in production you would usually use
        // async retry logic instead of blocking with Thread.Sleep.
        Thread.Sleep(250);
        score = riskApi.GetCurrentScore(customer.Id);
    }

    // At this point, score has already been evaluated and is known.
    // The request has already happened, so local fallback logic still belongs here.
    scores.Add(score);
}
```

Here the programmer specifies the execution policy directly, and the loop is where that policy is visible: where requests run, how retries happen, and where delay or error handling belongs.

The visible type of `GetRiskScore` is:

```text
Customer -> RiskScore
```

That type does not reveal the difference between a calculation and an API request. That matters because once the type hides observable work, the surrounding monad's way of applying the function also affects how the effect behaves.

Invoke `GetRiskScore` directly in a loop and you control that execution policy yourself. Pass it to another monad and the surrounding monad decides how and whether to call it:

```csharp
List<RiskScore> scores = customers.Map(GetRiskScore);
Maybe<RiskScore> score = maybeCustomer.Map(GetRiskScore);
```

The list monad may call the function many times. The maybe monad may skip it. Another surrounding type might defer the calls or batch them.

You can hide retry or delay inside `GetRiskScore`, and in a trivial case that may look sufficient. But the surrounding monad still decides when and whether the function gets called at all. If you need a different overall policy, you either bake that policy into the function itself or invent a special monad for that case, and both choices reduce composability.

A common question is how to extract the `T` from `IO<T>`. In the middle of the program, there is no general safe unwrap. A variable of type `IO<T>` names a recipe for the computation, not a finished `T`. The result appears only when the effect runs. Until then, keep composing, or return the `IO<T>` outward until a boundary decides to execute it.

## Make the effect part of the type

The next step is to stop returning the API result directly. Instead, return a recipe for the request so callers can keep composing it without committing to an execution policy.

Represent the API request explicitly:

```csharp
public static IO<RiskScore> GetRiskScoreIO(Customer customer)
{
    return IO<RiskScore>.From(() => riskApi.GetCurrentScore(customer.Id));
}
```

Calling `GetRiskScoreIO` constructs a request recipe.

Mapping over the customers constructs a list of request recipes:

```csharp
List<IO<RiskScore>> requests = customers.Map(GetRiskScoreIO);
```

The list still determines which customers participate, but each `IO<RiskScore>` now represents one request recipe. `requests` is still a collection of recipes, not completed scores. `List<IO<RiskScore>>` is not the same as `IO<List<RiskScore>>`: one is a list of request recipes, while the other is one larger recipe that produces a list. A later step can combine them into `IO<List<RiskScore>>` and execute them under a chosen policy.

## A small `IO<T>`

Here, `IO<T>` is a small wrapper around a deferred computation.

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

`From` defers a function. `Pure` puts an already-computed value into `IO<T>`; it does not execute an effect or extract anything from `IO<T>`. `Map` applies pure logic to the eventual value, while `FlatMap` is for the dependent case where the next step also returns `IO`. `Run` executes the stored recipe.

This implementation is intentionally a toy. It is synchronous, and C# cannot enforce that constructing an `IO<T>` should represent computation rather than execute it immediately.

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
```

The composed program:

```csharp
public static IO<string> LoadOrderAndRenderReport(string orderPath)
{
    return ReadAllTextIO(orderPath)
        .Map(ParseOrder)
        .FlatMap(order => FetchExchangeRateIO(order.Currency)
            .Map(exchangeRate => RenderReport(order, exchangeRate)));
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

At the boundary:

```csharp
IO<Unit> program = LoadOrderAndWriteReport("order.json", "report.txt");

program.Run();
```

Here, `Run()` is explicit for teaching purposes. In a real program, final execution is usually at an outer boundary such as `Main`.

## Running at the edge

"Move effects to the edge" means moving the final `Run()` outward. Helper functions can return effect recipes, larger functions can compose them, and an outer boundary such as `Main` or a request handler decides when to execute the final program.

That boundary still cannot freeze the world or selectively retry a hidden operation. Policies such as retry or throttling have to be attached while the relevant operation is still explicit.

## Conclusion

The important distinction is between a plain value and a recipe for a computation that may interact with the outside world before producing a value. Once that distinction is visible in the type, the program can decide at the boundary when, whether, and how often to execute it.
