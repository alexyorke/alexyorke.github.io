---
title: "Monads in C# (Part 3): A Tiny, Synchronous IO"
date: 2026-06-13
description: "A toy IO wrapper can represent deliberately deferred effects and compose them before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

Earlier articles in this series explained `Map` / `FlatMap` chaining. This one focuses on what changes once callbacks perform effects.

Useful programs perform effects somewhere. Here, an *effect* is behavior such as printing, writing a file, calling a service, or observing time or randomness. A function is *pure* when the same inputs produce the same result and evaluation produces no observable behavior beyond that result.

Once a callback performs effects, how and when it is invoked changes what the program does.

A simple pure function:

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

```csharp
decimal delayedTotal = CalculateTotal(100m, 0.13m, 5m);    // Still 107.35, even if this happens later.
decimal reorderedTotal = CalculateTotal(100m, 0.13m, 5m);  // Still 107.35, even if other work runs first.
```

Delay or reorder the calls and the result stays the same. The function remembers nothing about prior execution.

Host abstractions choose when callbacks run. LINQ `Select` is deferred: the selector runs when the sequence is enumerated, and another enumeration can run it again. `ToList()` forces one enumeration and stores the values.

```csharp
List<decimal> subtotals = new() { 100m, 80m, 140m };

List<decimal> totals = subtotals
    .Select(subtotal => CalculateTotal(subtotal, 0.13m, 5m))
    .ToList();
```

For a pure callback, different host rules can change evaluation timing or which values are produced, but not the meaning of each calculation.

Now compare an effectful function:

```csharp
public static RiskScore GetRiskScore(IRiskApi riskApi, string customerId)
{
    return riskApi.GetCurrentScore(customerId);
}

const string customerId = "cust-123";

RiskScore firstScore = GetRiskScore(riskApi, customerId);   // The first request has already happened.
RiskScore secondScore = GetRiskScore(riskApi, customerId);  // Delay, reorder, or interleave calls first, and this one may now differ.
```

Discarding `firstScore` does not undo the first API request. The next call with the same visible inputs is not guaranteed to return the same score. Call it again immediately, wait before calling it, or interleave other requests first, and the service may now have newer data, less quota, stronger throttling, or simply different timing conditions. Later calls can therefore see changed downstream conditions even with no explicit data flow between them.

With effects, execution policy affects observable behavior:

* when an operation runs;
* whether it runs;
* in what order operations run;
* how many times each operation runs.

> **Key point:** When one effect can change the conditions seen by the next, execution order becomes part of the result. Deferring those operations gives you a chance to choose that policy later. `IO<T>` turns each effectful step into a value, and helpers such as sequential traversal can combine those values into one larger program that runs in a known order.

Pure functions do not care whether you run them once, many times, or in a different order, except where later values are used as inputs. Effectful functions do, because earlier effects can change the downstream conditions seen by later ones. That is why order and repetition policy have to stay under control.

Procedural code commonly specifies that policy directly:

```csharp
var scores = new List<RiskScore>();

foreach (string customerId in customerIds)
{
    RiskScore score;

    try
    {
        score = riskApi.GetCurrentScore(customerId);
    }
    catch (TransientRiskApiException)
    {
        WaitBeforeRetry();
        score = riskApi.GetCurrentScore(customerId);
    }

    scores.Add(score);
}
```

The loop runs requests sequentially. A `TransientRiskApiException` from the first attempt causes one retry. If that retry throws, or if any other unhandled exception escapes, later IDs are not processed.

The ordinary method type does not distinguish this request from an in-memory calculation:

```text
(IRiskApi, string) -> RiskScore
```

Passing the function to another abstraction transfers some control over invocation to that abstraction:

```csharp
List<RiskScore> scores = customerIds
    .Select(customerId => GetRiskScore(riskApi, customerId))
    .ToList();

Maybe<RiskScore> score =
    maybeCustomerId.Map(customerId => GetRiskScore(riskApi, customerId));
```

Once you hand the callback to `Select`, `Maybe.Map`, or another host abstraction, that abstraction decides the act of running. `Select(...).ToList()` runs the request once per enumerated ID. `Maybe.Map(...)` may run it zero or one times. Another host could choose different invocation rules. That is harmless for pure callbacks, but not for effectful callbacks whose outcome depends on timing, order, repetition, or prior effects.

The `ToList()` call enumerates `customerIds`, so it decides when the requests happen and issues one request per ID. Without `ToList()`, the LINQ query stays deferred and later enumerations can issue the requests again. The host abstraction is therefore partly choosing program behavior. That is fine for pure callbacks. For effectful callbacks, it is a poor fit because it does not let you attach the execution policy you may need, such as explicit timing, retry behavior, or a known traversal policy.

> **Note:** `IO<T>` is not the only way to express execution policy in C#. Direct loops and resilience pipelines often handle retries, timeouts, circuit breakers, and rate limits more directly.

## Represent the deferred operation in the type

The shift is to return a recipe for performing the request later instead of performing it immediately:

```text
(IRiskApi, string) -> IO<RiskScore>
```

```csharp
public static IO<RiskScore> GetRiskScoreIO(IRiskApi riskApi, string customerId)
{
    return IO<RiskScore>.Delay(() => riskApi.GetCurrentScore(customerId));
}
```

Calling `GetRiskScoreIO` constructs an `IO<RiskScore>`. It does not call the API.

Deferring the operation is not the whole point. The effectful step is now a value that can be composed before execution. That lets you choose the execution policy later, at the point where the larger program is run, which is what restores composability for effectful steps.

Materializing a mapping over customer IDs produces a list of separate request recipes:

```csharp
List<IO<RiskScore>> requests = customerIds
    .Select(customerId => GetRiskScoreIO(riskApi, customerId))
    .ToList();
```

No API requests have started. The useful next step is to combine those recipes into an `IO<List<RiskScore>>`: one larger deferred program with an explicit traversal policy. The appendix shows one implementation and where a delay policy would attach.

Some libraries use a name like `Eff` for a similar effect value.

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

> **Scope:** This `IO<T>` is a synchronous, non-memoized teaching model built on `Func<T>`. `Run()` directly invokes its stored delegate on the current thread; the wrapper itself performs no scheduling. Every call to `Run()` starts the computation again. Exceptions thrown by the delayed operation or its composed callbacks propagate to the caller. The type has no built-in asynchronous I/O, cancellation, concurrency, resource bracketing, error model, or stack-safety mechanism. It is not a production abstraction or a compiler-enforced effect system.

`Pure` and `Delay` should not be confused:

```csharp
IO<int> value = IO<int>.Pure(42);
```

`Pure` places an existing value in the context. `Delay` suspends a computation:

```csharp
IO<string> deferred = IO<string>.Delay(() => File.ReadAllText(path));
```

For an effect whose only interesting result is that it completed, use a one-value `Unit` type:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}
```

This `Unit` is roughly `void` as a value. It is not the value-lifting operation that Part 1 called `Unit`; that operation is named `Pure` here.

A deferred file read places the read inside the stored function:

```csharp
IO<string> text = IO<string>.Delay(() => File.ReadAllText(path));
```

`Map` is for a next step that returns a plain value. `FlatMap` is for a next step that returns another `IO`.

C# does not enforce purity for the callback passed to `Map`. This compiles:

```csharp
IO<int> program = IO<int>
    .Pure(42)
    .Map(value =>
    {
        Console.WriteLine(value);
        return value;
    });
```

The console write is deferred because the callback is invoked inside the stored delegate. However, the `Map` signature does not record that its callback performs an effect. This type relies on programming discipline rather than compiler-enforced effect tracking.

This implementation has several important runtime semantics:

* `Run()` synchronously invokes the delegate on the current thread. The wrapper performs no scheduling, although the delegate itself could start or schedule other work.
* Every `Run()` invokes the stored delegate again.
* Exceptions from the delayed operation and composed callbacks propagate instead of becoming values.
* Captured state is read when the corresponding delegate executes.
* No result is memoized.
* Composition creates nested delegates rather than an inspectable syntax tree.
* Long enough chains of nested `FlatMap` calls can consume stack space because the implementation provides no stack-safety mechanism.

`Task<T>` is the usual .NET representation for asynchronous operations. This `IO<T>` is instead a cold, synchronous computation that does not begin until `Run()` is called.

## Building one effectful program

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

Assume `ParseOrder` and `RenderReport` are total pure functions, and that `IO<T>` also provides the `Select` / `SelectMany` methods required by C# query syntax. The appendix shows those query-support methods.

```csharp
public static IO<string> LoadOrderAndRenderReport(
    IExchangeRateApi exchangeRateApi,
    string orderPath)
{
    return
        from json in ReadAllTextIO(orderPath)
        let order = ParseOrder(json)
        from exchangeRate in FetchExchangeRateIO(exchangeRateApi, order.Currency)
        select RenderReport(order, exchangeRate);
}

public static IO<Unit> LoadOrderAndWriteReport(
    IExchangeRateApi exchangeRateApi,
    string orderPath,
    string reportPath)
{
    return
        from report in LoadOrderAndRenderReport(exchangeRateApi, orderPath)
        from result in WriteAllTextIO(reportPath, report)
        select result;
}
```

Constructing the program performs none of the wrapped effects:

```csharp
IO<Unit> program = LoadOrderAndWriteReport(
    exchangeRateApi,
    "order.json",
    "report.txt");
```

At that point, the caller holds one larger deferred recipe.

Running it attempts the file read, exchange-rate request, and file write in that order:

```csharp
program.Run();
program.Run();
```

Each invocation re-reads the order, re-fetches the rate, and, if the preceding steps succeed, rewrites the report.

What normally moves toward the application boundary is `Run()`, not `IO<T>`. `IO<T>` values may appear throughout the call graph. Control is lost when an inner helper calls `Run()` prematurely and turns part of the deferred description into an already performed effect.

## `Run()` cannot inspect or rewrite the program

This implementation represents a program as one opaque `Func<T>`. Composition wraps that function in more functions. By the time `Run()` receives the program, it cannot inspect individual operations, identify API requests, or restructure the sequence.

That limits what can be added at execution time:

* `FlatMap` determines the order of dependent operations.
* Traversal helpers determine how collections of operations are executed.
* A retry combinator around one particular `IO<T>` can retry that operation.
* An external resilience pipeline can wrap the entire `program.Run()` callback, but its retry policy repeats the entire callback - not merely the step that failed.
* An external caller can run several complete `IO<T>` values concurrently, but `Run()` cannot discover and parallelize hidden steps inside one opaque delegate.
* Cooperative cancellation requires operations to accept and observe a cancellation signal. This `IO<T>` has no such channel.
* Resource acquisition, use, and disposal must all occur inside the delayed computation or an equivalent bracket operation.

A retry around the entire program can repeat earlier effects that completed before a later step failed. The same issue applies to timeout wrappers: if the callback does not observe cancellation, the underlying work can continue.

Resource lifetime needs the same care. A synchronous operation can acquire and dispose a resource inside its delayed delegate:

```csharp
public static IO<string> ReadFirstLineIO(string path)
{
    return IO<string>.Delay(() =>
    {
        using StreamReader reader = File.OpenText(path);
        return reader.ReadLine() ?? string.Empty;
    });
}
```

The `using` scope disposes the reader when control leaves the scope, including when an exception exits the block.

This toy implementation erases structure into delegates, so `Run()` is only an evaluator for the resulting opaque thunk.

## Conclusion

The central distinction is between a value and a deferred computation that may perform effects before producing a value.

This toy `IO<T>` makes such computations first-class values. They can be returned, mapped, combined, and traversed before execution. Calling `Run()` then executes the resulting synchronous, non-memoized thunk.

The discipline is not to ban `IO<T>` from the interior of the program. It is to avoid executing deferred operations prematurely and to make execution boundaries and repetition policy explicit.

## Appendix

<details markdown="1">
<summary markdown="span">Open the appendix for sequential traversal</summary>

### Optional C# query syntax support

The main body keeps `IO<T>` small. If you want C# query syntax, add the standard `Select` and `SelectMany` methods:

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

### From a list of recipes to one recipe

Mapping `GetRiskScoreIO` over customer IDs and materializing the result produces a `List<IO<RiskScore>>`:

```csharp
List<IO<RiskScore>> requests = customerIds
    .Select(customerId => GetRiskScoreIO(riskApi, customerId))
    .ToList();
```

This builds the individual recipes. It does not execute them.

```text
List<IO<RiskScore>>
IO<List<RiskScore>>
```

A single `FlatMap` call operates on an `IO` already in hand; it does not by itself turn the outer `List` into an `IO`. The operation that swaps these layers is conventionally called `Sequence`.

```text
Sequence:
List<IO<T>> -> IO<List<T>>

Traverse:
List<A> x (A -> IO<B>) -> IO<List<B>>
```

`Sequence` handles effectful values already present in the collection. `Traverse` maps inputs to effectful values and combines them. `Sequence` is traversal with the identity function.

For this article, `TraverseSequential` and `SequenceSequential` are just explicit names for one policy: combine many deferred `IO` recipes into one larger deferred recipe that runs them sequentially.

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

`TraverseSequential` contributes the following policy:

* list traversal is deferred until `Run()`;
* `action` is invoked during that traversal;
* items are handled in list order;
* one `IO` completes before the next begins;
* results are stored in the same order;
* an exception from `action` or an operation stops the traversal;
* every outer `Run()` traverses the list and executes the operations again.

If you wanted pauses between items, retries around each request, or some other batch policy, that policy would not be invented by `Run()` later. You would build it into each item `IO`, or write a different traversal helper whose rule is "run one item, apply the policy, then run the next." `TraverseSequential` itself only says: run the list sequentially.

This turns the list of request recipes into one batch recipe:

```csharp
IO<List<RiskScore>> program = requests.SequenceSequential();
```

`SequenceSequential` does not start the requests:

```csharp
List<RiskScore> scores = program.Run();
```

The outer `Run()` starts the traversal. The nested `Run()` calls inside `TraverseSequential` are part of that deferred traversal's implementation.

The important boundary is temporal: those nested calls occur only after the outer program starts. By contrast, calling `Run()` while constructing `program` would perform an effect prematurely.

</details>
