---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO makes effects explicit so they can be composed before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

> **Note:** This article is not recommending `IO<T>` for production C#.

Earlier in the series, many of the small teaching examples passed pure functions to `Map` and `FlatMap`, although Part 2 already mixed in repository lookups and pragmatic mutation.

An effect is an operation whose interaction with the outside world is part of what the program does. I use side effect for an outside-world interaction that happens while computing a value, beyond the value the function returns.

A pure function depends only on its explicit inputs: given the same arguments, it produces the same result, and calling it causes no interaction with the outside world.

This article is about what changes when those outside-world interactions affect what later code or external systems observe, even when the explicit inputs stay the same.

```csharp
public static decimal CalculateTotal(
    decimal subtotal,
    decimal taxRate,
    decimal discount)
{
    // Pure function: the result depends only on the arguments,
    // and calling it does not interact with the outside world.
    decimal discountedSubtotal = subtotal - discount;
    decimal tax = discountedSubtotal * taxRate;
    return discountedSubtotal + tax;
}

decimal first = CalculateTotal(100m, 0.13m, 5m);   // 107.35
decimal second = CalculateTotal(100m, 0.13m, 5m);  // 107.35
```

If we throw away `first`, nothing observable changes. The next invocation is still `107.35`.

That is why the earlier examples could let each monad decide how to apply the function. The List monad can apply it to many values. The Maybe monad can skip it. The Result monad continues with later mapped steps only after success; once a failure value is present, later steps are skipped. For pure functions, that stays compatible with composition because only the returned value matters.

Now compare an effectful function:

```csharp
public static RiskScore GetRiskScore(Customer customer)
{
    return riskApi.GetCurrentScore(customer.Id);
}

RiskScore firstScore = GetRiskScore(customer);
RiskScore secondScore = GetRiskScore(customer);
```

Calling `GetRiskScore(customer)` twice is not like calling `CalculateTotal(100m, 0.13m, 5m)` twice. The request might time out, consume quota, hit a rate limit, or return a different score on the second call even with the same customer.

With effects, execution policy becomes part of the outcome: when the operation runs, whether it runs at all, in what order it runs, and how often it runs. That matters because each monad already has its own way of applying and sequencing functions.

`IO<T>` changes `Customer -> RiskScore` into `Customer -> IO<RiskScore>`. Instead of performing the request immediately, the function returns a recipe for a request that can be run later. `IO<T>` names a computation to run later, not a finished `T` waiting inside. There is no value to pull out yet because the recipe has not run.

```text
Customer -> IO<RiskScore>
```

In procedural code, execution is often immediate, and the programmer usually controls that sequence directly:

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
        WaitBeforeRetry();
        score = riskApi.GetCurrentScore(customer.Id);
    }

    scores.Add(score);
}
```

Here the programmer specifies the execution policy directly, and the loop is where that policy is visible: where requests run, how retries happen, and where delay or error handling belongs.

```text
Customer -> RiskScore
```

That type does not reveal the difference between a calculation and an API request. Invoke `GetRiskScore` directly in a loop and you control that execution policy yourself. Pass it to another monad and that monad decides how and whether to call it:

```csharp
List<RiskScore> scores = customers.Map(GetRiskScore);
Maybe<RiskScore> score = maybeCustomer.Map(GetRiskScore);
```

The List monad may call `GetRiskScore` once for each customer under its traversal policy. The Maybe monad may skip the call entirely. Another monad could define a different policy. If you need a different overall policy, you either bake that policy into the function itself or invent a special monad for that case, and both choices reduce composability.

A common question is how to extract the `T` from `IO<T>`. In the middle of the program, there is no general safe unwrap. A variable of type `IO<T>` names a recipe for the computation, not a finished `T`. The result appears only when the effect runs. Until then, keep composing, or return the `IO<T>` outward until a boundary decides to execute it.

## Make the effect part of the type

Instead, return a recipe for the request so callers can keep composing it without committing to an execution policy.

```csharp
public static IO<RiskScore> GetRiskScoreIO(Customer customer)
{
    return IO<RiskScore>.From(() => riskApi.GetCurrentScore(customer.Id));
}
```

Mapping over the customers constructs a list of request recipes:

```csharp
List<IO<RiskScore>> requests = customers.Map(GetRiskScoreIO);
```

The list still determines which customers participate, but each `IO<RiskScore>` now represents one request recipe. `requests` is still a collection of recipes, not completed scores. `List<IO<RiskScore>>` is not the same as `IO<List<RiskScore>>`: one is a list of request recipes, while the other is one larger recipe that produces a list. A later step can combine them into `IO<List<RiskScore>>` and execute them under a chosen policy.

That combining step is often called `Sequence` or `Traverse`. I am not going to build it here, but it is the operation that turns many separate recipes into one larger recipe.

`FlatMap` is not enough by itself because it flattens one kind of structure at a time: `IO<IO<T>>` into `IO<T>`, or `List<List<T>>` into `List<T>`. `List<IO<T>>` mixes two structures, so the program still needs a rule for how the list traversal becomes one `IO` recipe. The same issue appears with shapes like `Maybe<IO<T>>`.

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

    public IO<TResult> Select<TResult>(Func<T, TResult> select)
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

    public T Run()
    {
        return operation();
    }
}
```

`From` defers a function. `Pure` puts an already-computed value into `IO<T>`; it does not execute an effect or extract anything from `IO<T>`. `Map` applies pure logic to the eventual value, while `FlatMap` is for the dependent case where the next step also returns `IO`. `Select` and `SelectMany` let C# query syntax use the same operations. `Run` executes the stored recipe.

## Building one effectful program

Start with effects that produce useful values:

```csharp
public static IO<string> ReadAllTextIO(string path)
{
    return IO<string>.From(() => File.ReadAllText(path));
}

public static IO<decimal> FetchExchangeRateIO(string currency)
{
    return IO<decimal>.From(() => exchangeRateApi.GetCurrentRate(currency));
}
```

Writing a file mostly matters because the write happened. Since `IO<T>` still has a type parameter, use a small `Unit` value for effects whose useful result is just "it ran":

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new Unit();
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

Assume `ParseOrder` and `RenderReport` are pure functions.

The larger program can put the dependent steps in order:

```csharp
public static IO<string> LoadOrderAndRenderReport(string orderPath)
{
    return
        from json in ReadAllTextIO(orderPath)
        let order = ParseOrder(json)
        from exchangeRate in FetchExchangeRateIO(order.Currency)
        select RenderReport(order, exchangeRate);
}

public static IO<Unit> LoadOrderAndWriteReport(string orderPath, string reportPath)
{
    return
        from report in LoadOrderAndRenderReport(orderPath)
        from _ in WriteAllTextIO(reportPath, report)
        select Unit.Value;
}
```

<details>
<summary>The same program with Map and FlatMap</summary>

```csharp
public static IO<string> LoadOrderAndRenderReport(string orderPath)
{
    return ReadAllTextIO(orderPath)
        .Map(ParseOrder)
        .FlatMap(order => FetchExchangeRateIO(order.Currency)
            .Map(exchangeRate => RenderReport(order, exchangeRate)));
}

public static IO<Unit> LoadOrderAndWriteReport(string orderPath, string reportPath)
{
    return LoadOrderAndRenderReport(orderPath)
        .FlatMap(report => WriteAllTextIO(reportPath, report));
}
```

</details>

At the boundary:

```csharp
IO<Unit> program = LoadOrderAndWriteReport("order.json", "report.txt");

program.Run();
```

Moving effects to the edge means moving the final `Run()` outward. Helper functions can return effect recipes, larger functions can compose them, and an outer boundary such as `Main` or a request handler decides when to execute the final program.

In this toy type, `Run()` is the interpreter. In a real effect library, the interpreter is usually where policies such as retries, logging, concurrency, cancellation, and resource cleanup become explicit.

## Conclusion

The important distinction is between a plain value and a recipe for a computation that may interact with the outside world before producing a value. `IO<T>` is useful here because it preserves composition while delaying the execution policy decision. Once the distinction is visible in the type, the program can decide at the boundary when, whether, and how often to execute the effect.
