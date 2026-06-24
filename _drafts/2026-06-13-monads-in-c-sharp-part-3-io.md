---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> turns an effectful computation into a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

A function is no longer "just a calculation" when running it can call an HTTP API, read from or write to a database, write a file, print to the console, or observe time or randomness. Here, *effect* just means that kind of observable interaction. A *pure* function, by contrast, always returns the same result for the same inputs and does not change anything outside itself. Earlier articles in this series used `Map` and `FlatMap` to compose calculations. For pure functions, the question is whether the inputs determine the result. For effectful functions, it can also matter when, how often, and in what order the function runs.

## When timing matters

As a quick refresher, consider a pure calculation:

```csharp
public static decimal CalculateTotal(decimal subtotal, decimal taxRate, decimal discount)
{
    decimal discountedSubtotal = subtotal - discount;
    decimal tax = discountedSubtotal * taxRate;

    return discountedSubtotal + tax;
}

decimal totalA = CalculateTotal(100m, 0.13m, 5m); // 107.35
decimal totalB = CalculateTotal(100m, 0.13m, 5m); // 107.35
```

Call it once or a thousand times, now or later, and the same inputs still determine the same result.

```csharp
List<decimal> subtotals = new() { 100m, 80m, 140m };

List<decimal> totals = subtotals
    .Select(subtotal => CalculateTotal(subtotal, 0.13m, 5m))
    .ToList();
```

`Select` and `ToList()` still control when the function runs. For a pure function, that affects when the work happens, not what result each input produces.

Consider an ordinary HTTP API call wrapped as a function:

```csharp
public static RiskScore GetRiskScore(IRiskApi riskApi, string customerId)
{
    return riskApi.GetCurrentScore(customerId);
}
```

Its type looks like an ordinary value-producing function:

```text
(IRiskApi, string) -> RiskScore
```

But calling it does more than calculate a value. It sends a request, observes the current state of another system, and may change externally visible conditions such as quota or throttling.

For a pure function, calling it again with the same input just gives you the same answer. For an effectful function, the inputs may stay the same while the outcome still changes depending on when, how often, or in what order the function runs, and subsequent invocations of the function could depend on whether others have run, even if they are not provided as explicit inputs. If you run GetRiskScore too fast, even with the same inputs, subsequent functions may change their output (e.g., be rate limited, maybe a timeout, etc.)

```csharp
RiskScore firstScore = GetRiskScore(riskApi, customerId);   // Sends one request now.
RiskScore secondScore = GetRiskScore(riskApi, customerId);  // May observe different service state.

Thread.Sleep(TimeSpan.FromSeconds(1));
RiskScore thirdScore = GetRiskScore(riskApi, customerId);   // May differ again, or hit throttling/rate limits.
```

The pure `CalculateTotal` example does not have that property. Call it now, later, once, or many times, and the same inputs still determine the same result.

If a function runs too quickly, in a different order, or after an earlier failure, the program may hit throttling, consume rate limits, or stop before later work runs. For effectful code, the problem is not just "it ran again." Timing, order, repetition, and failure behavior can all matter.

That becomes especially noticeable when the function is passed to an abstraction that controls when it is invoked:

```csharp
IEnumerable<RiskScore> scores = customerIds
    .Select(customerId => GetRiskScore(riskApi, customerId));
```

Constructing this query sends no requests. Enumeration does:

```csharp
List<RiskScore> first = scores.ToList();  // Sends the requests.
List<RiskScore> second = scores.ToList(); // Sends them all again.
```

This is normal `IEnumerable<T>` behavior. The selector is deferred and is invoked once for every value produced during each enumeration.

A list is only one example:

```csharp
var maybeScore =
    from customerId in maybeCustomerId
    select GetRiskScore(riskApi, customerId);

var resultScore =
    from customerId in validatedCustomerId
    select GetRiskScore(riskApi, customerId);
```

<details markdown="1">
<summary markdown="span">Equivalent method-call form</summary>

```csharp
var maybeScore =
    maybeCustomerId.Map(customerId => GetRiskScore(riskApi, customerId));

var resultScore =
    validatedCustomerId.Map(customerId => GetRiskScore(riskApi, customerId));
```

</details>

`Maybe` might invoke the function zero or one times. `Result` might invoke it only on the success path. The point is not `List.Select` specifically. Once you pass an effectful function into some host abstraction, that abstraction brings its own rule for when the function runs. You could imagine an abstraction that runs items in reverse order, or one that visits every second element before coming back for the rest. That rule may be perfectly valid for the abstraction, but still be the wrong execution policy for the effectful work you are trying to describe.

The mismatch is in the type signature: it looks like an ordinary function that returns a `RiskScore`, but calling it also performs an external operation. Once you pass that function into such an abstraction, the abstraction decides when it is invoked and how many times, and those details now matter.

Plain procedural code usually makes the execution policy obvious:

```csharp
var scores = new List<RiskScore>();

foreach (string customerId in customerIds)
{
    RiskScore score = riskApi.GetCurrentScore(customerId);
    scores.Add(score);
}
```

It runs now, in order, and stops on failure unless the code says otherwise. If you want pauses, retries, or rate limiting, this is where you would put them.

## From an immediate result to a suspended computation

`GetRiskScore` is still a function we want to compose with other steps. The problem is that, in its current form, calling it performs the effect immediately, so whatever abstraction invokes the function also ends up deciding when and how often that effect runs. We do not want to require every caller to adopt some special collection or special execution policy up front. What we want instead is a way to return an inert description of the work - something that can be combined like any other value, but that does not run until we explicitly choose to run it.

One way to do that is to change what the function returns:

```text
(IRiskApi, string) -> RiskScore
(IRiskApi, string) -> IO<RiskScore>
```

```csharp
public static IO<RiskScore> GetRiskScoreIO(
    IRiskApi riskApi,
    string customerId)
{
    return IO<RiskScore>.Delay(
        () => riskApi.GetCurrentScore(customerId));
}
```

Calling `GetRiskScoreIO` does not send a request. It returns a deferred computation that can produce a `RiskScore` when run. The outer function now returns something inert that can be passed around and combined before any effect happens.

That separation is the central idea:

* `Delay` suspends a computation.
* `Map` transforms its eventual value.
* `FlatMap` makes a later suspended computation depend on an earlier result.
* `Run` performs the composed computation.

> **`IO<T>` does not make an effect pure. It makes the decision to perform the effect separate and explicit.**

Deferral alone is not what makes `IO<T>` monadic; a `Func<T>` can already defer work. Plain deferral is useful, but by itself it does not give you a way to combine dependent deferred computations while keeping them deferred. `Pure` and `FlatMap` provide that composition. Once the effectful computation is represented as an `IO<T>` value, execution policy can be chosen by the surrounding combinator or program structure instead of by whatever host abstraction happens to invoke the function. You can still put delays or retries inside a plain function, but then that policy is tied to the particular abstraction that calls it. Representing the work as a value keeps that policy separate and makes it easier to compose.

```text
Pure    : T -> IO<T>
FlatMap : IO<T> -> (T -> IO<TResult>) -> IO<TResult>
```

Calling `FlatMap` builds another `IO`; it does not run the first operation or run the next deferred step. Those things happen only when the resulting program is run. This is also why `Run()` tends to move outward: once part of the program is executed too early, the surrounding code loses the chance to choose policy for the larger whole.

This article implements that model as a small synchronous wrapper around `Func<T>`. The wrapper gives the thunk a meaningful type, an explicit execution boundary, and composition operations.

## A small `IO<T>`

To support this style of composition, the type needs two basic operations: one to wrap an existing value as `IO<T>`, and one to chain functions that themselves return `IO<...>`. Here those operations are named `Pure` and `FlatMap`. `Delay` serves a separate purpose: it suspends a computation.

```csharp
public sealed class IO<T>
{
    private readonly Func<T> operation;

    private IO(Func<T> operation)
    {
        this.operation = operation;
    }

    public static IO<T> Pure(T value)
    {
        return new IO<T>(() => value);
    }

    public static IO<T> Delay(Func<T> operation)
    {
        return new IO<T>(operation);
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

`Pure` wraps an existing value. `Delay` suspends a computation.

For an effect whose only interesting result is that it completed, use a one-value `Unit` type:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}
```

This `Unit` is roughly `void` as a value. It is not the value-lifting operation that Part 1 called `Unit`; that operation is named `Pure` here.

`Map` is for a next step that returns a plain value. `FlatMap` is for a next step that returns another `IO`.

## Compose first, run later

Suppose we want to read an order from disk, fetch its exchange rate, render a report, and write that report to disk:

```csharp
public static IO<string> ReadAllTextIO(string path)
{
    return IO<string>.Delay(() => File.ReadAllText(path));
}

public static IO<decimal> FetchExchangeRateIO(IExchangeRateApi exchangeRateApi, string currency)
{
    return IO<decimal>.Delay(() => exchangeRateApi.GetCurrentRate(currency));
}
```

For a file write, the interesting result is normally successful completion, so return `IO<Unit>`:

```csharp
public static IO<Unit> WriteAllTextIO(string path, string contents)
{
    return IO<Unit>.Delay(() =>
    {
        File.WriteAllText(path, contents);
        return Unit.Value;
    });
}
```

```csharp
public static IO<Unit> LoadOrderAndWriteReport(
    IExchangeRateApi exchangeRateApi,
    string orderPath,
    string reportPath)
{
    return
        from json in ReadAllTextIO(orderPath)
        let order = ParseOrder(json)
        from exchangeRate in FetchExchangeRateIO(exchangeRateApi, order.Currency)
        let report = RenderReport(order, exchangeRate)
        from result in WriteAllTextIO(reportPath, report)
        select result;
}
```

The `let` clauses keep the pure parsing and rendering steps inside the suspended computation. The later `from` clauses represent effectful steps that depend on earlier results. The return value is still another `IO<Unit>`, so the whole pipeline stays deferred.

<details markdown="1">
<summary markdown="span">Equivalent `Map` / `FlatMap` form</summary>

```csharp
public static IO<Unit> LoadOrderAndWriteReport(
    IExchangeRateApi exchangeRateApi,
    string orderPath,
    string reportPath)
{
    return ReadAllTextIO(orderPath)
        .Map(ParseOrder)
        .FlatMap(order =>
            FetchExchangeRateIO(exchangeRateApi, order.Currency)
                .Map(exchangeRate =>
                    RenderReport(order, exchangeRate)))
        .FlatMap(report =>
            WriteAllTextIO(reportPath, report));
}
```

</details>

That query is syntax sugar over the same `Map` / `FlatMap` structure. The important point is unchanged: compose first, then run.

## The execution boundary

Constructing the program performs none of the wrapped effects:

```csharp
IO<Unit> program = LoadOrderAndWriteReport(
    exchangeRateApi,
    "order.json",
    "report.txt");
```

At that point, the caller holds one larger deferred computation.

Calling `Run()` crosses the execution boundary:

```csharp
program.Run();
```

That call attempts the file read, exchange-rate request, report rendering, and file write in dependency order. A second `Run()` re-reads the order, re-fetches the rate, re-renders the report, and rewrites the file.

In this style, you usually push calls to `Run()` outward toward the application boundary, while `IO<T>` values can remain in the call graph. Control is lost when an inner helper calls `Run()` prematurely and turns part of the deferred description into an already performed effect. This toy `Run()` only executes the delegate it is given; it cannot inspect the built program or retroactively add policies such as retries, parallelism, cancellation, or cleanup. Those choices must be encoded while constructing the `IO<T>` or supplied by surrounding infrastructure.

## Runtime semantics and limitations

This `IO<T>` is intentionally small: it is synchronous, cold, and non-memoized. Nothing happens until `Run()`, `Run()` executes on the current thread, and calling `Run()` twice runs the whole computation twice. Exceptions propagate normally, and closures over mutable state are observed when the computation runs. C# does not verify purity here. This is a teaching model, not a production-grade effect runtime. For asynchronous work, .NET normally uses `Task` and `Task<T>`.

## Traversal and policy

Mapping `GetRiskScoreIO` over customer IDs and materializing the result produces a `List<IO<RiskScore>>`:

```csharp
List<IO<RiskScore>> requests = customerIds
    .Select(customerId => GetRiskScoreIO(riskApi, customerId))
    .ToList();
```

This builds separate suspended operations. It does not execute them.

```text
List<IO<RiskScore>>  // Many suspended request recipes.
IO<List<RiskScore>>  // One suspended program that will produce a list.
```

After `Select`, you still need a helper that combines those many deferred requests into one deferred batch. A helper such as `SequenceSequential` or `TraverseSequential` also fixes the policy for that batch. In this article, that policy is: run later, in list order, one at a time, and stop on exception.

This turns the list of request recipes into one batch recipe:

```csharp
IO<List<RiskScore>> program = requests.SequenceSequential();
```

Here is one simple implementation:

```csharp
public static class IOExtensions
{
    public static IO<List<TResult>> TraverseSequential<TSource, TResult>(
        this List<TSource> source,
        Func<TSource, IO<TResult>> action)
    {
        return IO<List<TResult>>.Delay(() =>
        {
            var results = new List<TResult>();

            foreach (TSource item in source)
            {
                IO<TResult> operation = action(item);
                TResult result = operation.Run();
                results.Add(result);
            }

            return results;
        });
    }

    public static IO<List<T>> SequenceSequential<T>(this List<IO<T>> source)
    {
        return source.TraverseSequential(static operation => operation);
    }
}
```

`SequenceSequential` still does not start the requests. The work begins only when the outer `Run()` executes the batch program:

```csharp
List<RiskScore> scores = program.Run();
```

`TraverseSequential` contributes the following policy:

* list traversal is deferred until `Run()`;
* `action` is invoked during that traversal;
* items are handled in list order;
* one `IO` completes before the next begins;
* results are stored in the same order;
* an exception stops the traversal;
* every outer `Run()` traverses the list and executes the operations again.

The nested `Run()` calls inside `TraverseSequential` are part of that deferred traversal's implementation, so they happen only after the outer batch program begins. If you wanted pauses between items, retries around each request, reverse order, or some other rule, `Run()` would not invent that later. You would build it into each item `IO`, or write a different traversal helper with a different policy.

## Conclusion

The central distinction is not merely that effects exist. It is that constructing an effectful computation is different from running it.

This tiny `IO<T>` makes the computation a first-class cold value. `Delay` suspends it, `FlatMap` composes dependent steps without running them, and `Run()` marks the execution boundary.

Because construction and execution are separate, sequencing and traversal policies can be expressed by combinators or surrounding infrastructure instead of being hidden inside whatever abstraction happens to control when a function is invoked. The discipline is not to ban `IO<T>` from the interior of the program. It is to avoid calling `Run()` prematurely.

## Appendix

<details markdown="1">
<summary markdown="span">Open the appendix for optional query syntax support</summary>

### Optional C# query syntax support

The main body uses C# query syntax for the composed `IO` examples. If you want that surface on `IO<T>`, add the standard `Select` and `SelectMany` methods:

```csharp
public IO<TResult> Select<TResult>(Func<T, TResult> selector)
{
    return Map(selector);
}

public IO<TResult> SelectMany<TNext, TResult>(
    Func<T, IO<TNext>> next,
    Func<T, TNext, TResult> project)
{
    return FlatMap(value =>
        next(value).Map(nextValue =>
            project(value, nextValue)));
}
```

</details>
