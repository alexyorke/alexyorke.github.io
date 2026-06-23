---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> turns an effectful computation into a cold value. FlatMap composes those computations, while Run() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

Earlier articles in this series used `Map` and `FlatMap` to compose calculations. Effects add another question: when does the callback run?

## Callback invocation becomes observable

Consider an ordinary API method:

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

For a total pure function, evaluating the same input again produces the same value without changing anything outside the function. For an effectful function, the timing, order, and number of evaluations can be observable, so execution order becomes part of the program's observable behavior.

That becomes especially noticeable when the function is passed to an abstraction that controls callback invocation:

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

The mismatch is that the callback's type advertises only a returned `RiskScore`. It does not indicate that invoking the callback also performs an external operation. Consequently, enumeration controls execution indirectly and can repeat it unexpectedly.

## From an immediate result to a suspended computation

A small `IO<T>` changes the signature:

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

Calling `GetRiskScoreIO` does not send a request. It returns a value representing a computation that can produce a `RiskScore` when run. The first call performs the operation. The second constructs an operation.

That separation is the central idea:

* `Delay` suspends a computation.
* `Map` transforms its eventual value.
* `FlatMap` makes a later suspended computation depend on an earlier result.
* `Run` performs the composed computation.

> **`IO<T>` does not make an effect pure. It makes the decision to perform the effect separate and explicit.**

Deferral alone is not what makes `IO<T>` monadic; a `Func<T>` can already defer work. The monadic part is `Pure` plus `FlatMap`: they let deferred, dependent computations be combined into another deferred computation.

```text
Pure    : T -> IO<T>
FlatMap : IO<T> -> (T -> IO<TResult>) -> IO<TResult>
```

Calling `FlatMap` constructs another `IO`; it does not run the first operation or invoke the next callback. Those things happen only when the resulting program is run.

This article implements that model as a small synchronous wrapper around `Func<T>`. The wrapper gives the thunk a meaningful type, an explicit execution boundary, and composition operations.

## A small `IO<T>`

A monad-shaped API needs a way to place an existing value in the context and a way to compose context-producing functions. Here those operations are named `Pure` and `FlatMap`. `Delay` serves a separate purpose: it suspends a computation.

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

`Map(ParseOrder)` keeps the pure parsing step inside the suspended computation. Each `FlatMap` builds a later suspended step that depends on an earlier result. The return value is another `IO<Unit>`, so the whole pipeline stays deferred.

If you prefer query syntax, the same composition can be written this way:

```csharp
public static IO<Unit> LoadOrderAndWriteReportQuery(
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

That is syntax sugar over the same `Map` / `FlatMap` structure. The important point is unchanged: compose first, then run.

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

What normally moves toward the application boundary is `Run()`, not `IO<T>`. `IO<T>` values may appear throughout the call graph. Control is lost when an inner helper calls `Run()` prematurely and turns part of the deferred description into an already performed effect. This toy `Run()` only executes the delegate it is given; it cannot inspect the built program or retroactively add policies such as retries, parallelism, cancellation, or cleanup. Those choices must be encoded while constructing the `IO<T>` or supplied by surrounding infrastructure.

## Runtime semantics and limitations

This teaching implementation is a cold, synchronous, non-memoized wrapper around `Func<T>`. `Run()` invokes the stored delegate on the current thread, every `Run()` starts the computation again, and exceptions from delayed operations or composed callbacks propagate to the caller. If a delayed callback closes over mutable state, it reads that state when the delegate executes, not when the `IO<T>` is constructed. C# does not enforce purity or effect tracking for callbacks, so the model relies on discipline rather than compiler guarantees. The type provides no cancellation, concurrency, resource bracketing, typed error model, or stack-safety guarantee. It is a teaching model, not a production effect system.

`Task<T>` is the usual .NET representation for asynchronous operations. This `IO<T>` is instead a cold, synchronous computation that does not begin until `Run()` is called.

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

A single `FlatMap` call operates on an `IO` already in hand; it does not by itself turn the outer `List` into an `IO`. The operation that swaps these layers is conventionally called `Sequence`.

```text
Sequence:
List<IO<T>> -> IO<List<T>>

Traverse:
List<A> x (A -> IO<B>) -> IO<List<B>>
```

`Sequence` handles effectful values already present in the collection. `Traverse` maps inputs to effectful values and combines them. `Sequence` is traversal with the identity function.

For this article, `TraverseSequential` and `SequenceSequential` are explicit names for one policy: combine many deferred `IO` recipes into one larger deferred recipe that runs them sequentially.

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

`TraverseSequential` contributes the traversal policy:

* list traversal is deferred until `Run()`;
* `action` is invoked during that traversal;
* items are handled in list order;
* one `IO` completes before the next begins;
* results are stored in the same order;
* an exception stops the traversal;
* every outer `Run()` traverses the list and executes the operations again.

If you wanted pauses between items, retries around each request, or some other batch policy, `Run()` would not invent that later. You would build it into each item `IO`, or write a different traversal helper whose rule is "run one item, apply the policy, then run the next." `TraverseSequential` itself only says: run the list sequentially.

This turns the list of request recipes into one batch recipe:

```csharp
IO<List<RiskScore>> program = requests.SequenceSequential();
```

`SequenceSequential` does not start the requests:

```csharp
List<RiskScore> scores = program.Run();
```

The outer `Run()` starts the traversal. The nested `Run()` calls inside `TraverseSequential` are part of that deferred traversal's implementation, so they happen only after the outer program begins.

## Conclusion

The central distinction is not merely that effects exist. It is that constructing an effectful computation is different from running it.

This tiny `IO<T>` makes the computation a first-class cold value. `Delay` suspends it, `FlatMap` composes dependent steps without running them, and `Run()` marks the execution boundary.

Because construction and execution are separate, sequencing and traversal policies can be expressed by combinators or surrounding infrastructure instead of being hidden inside whatever abstraction happens to invoke a callback. The discipline is not to ban `IO<T>` from the interior of the program. It is to avoid calling `Run()` prematurely.

## Appendix

<details markdown="1">
<summary markdown="span">Open the appendix for optional C# query syntax support</summary>

### Optional C# query syntax support

The main body uses `Map` and `FlatMap` directly. If you want C# query syntax, add the standard `Select` and `SelectMany` methods:

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
