---
title: "Monads in C# (Part 3): A Tiny, Synchronous IO"
date: 2026-06-13
description: "A toy IO wrapper can represent deliberately deferred effects and compose them before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

> **Scope:** The `IO<T>` below is a synchronous, non-memoized teaching model built on `Func<T>`. `Run()` directly invokes its stored delegate on the current thread; the wrapper itself performs no scheduling. Every call to `Run()` starts the computation again. Exceptions thrown by the delayed operation or its composed callbacks propagate to the caller. The type has no built-in asynchronous I/O, cancellation, concurrency, resource bracketing, error model, or stack-safety mechanism. It is not a production abstraction or a compiler-enforced effect system.

Earlier articles in this series passed functions to `Map` and `FlatMap`, but did not focus on when those functions run, how often they run, or when they interact with the outside world.

For this article, call a function *pure* when the same inputs produce the same result and evaluating it produces no observable behavior beyond that result. I use *effect* as shorthand for behavior such as printing, writing a file, mutating state, calling a service, or observing time or randomness. The traditional phrase is *side effect*.

Most useful programs perform effects somewhere. Once a callback is effectful, the policy governing its invocation becomes part of the program's visible behavior.

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

Discarding `totalA` does not alter the next invocation. Both calls return `107.35`, and the function retains no state between them.

Invocation policy first becomes visible in the abstraction that applies a callback. LINQ-to-Objects `Select` is deferred: the selector runs when the sequence is enumerated, and enumerating it again can run it again. Calling `ToList()` forces one enumeration and stores the resulting values.

```csharp
List<int> mapped = numbers
    .Select(number => number + 1)
    .ToList();
```

A particular `Maybe.Map` implementation may invoke its callback zero or one times, while a `Result.Map` implementation may invoke it only for a successful value. For a pure callback, those rules determine whether values are produced. For an effectful callback, they also determine whether and how often observable behavior occurs.

Now compare an effectful function:

```csharp
public static RiskScore GetRiskScore(IRiskApi riskApi, Customer customer)
{
    return riskApi.GetCurrentScore(customer.Id);
}

RiskScore firstScore = GetRiskScore(riskApi, customer);
RiskScore secondScore = GetRiskScore(riskApi, customer);
```

Discarding `firstScore` does not undo the first API request. The next invocation is not guaranteed to return the same score: the service may have newer data, consume quota, update internal state, throttle the caller, or be unavailable despite the same visible arguments.

With effects, execution policy affects observable behavior:

* when an operation runs;
* whether it runs;
* in what order operations run;
* how many times each operation runs.

Procedural code commonly specifies that policy directly:

```csharp
var scores = new List<RiskScore>();

foreach (Customer customer in customers)
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

The loop runs requests sequentially. A `TransientRiskApiException` from the first attempt causes one retry. If that retry throws, or if any other unhandled exception escapes, later customers are not processed.

The ordinary method type does not distinguish this request from an in-memory calculation:

```text
(IRiskApi, Customer) -> RiskScore
```

Passing the function to another abstraction transfers some control over invocation to that abstraction:

```csharp
List<RiskScore> scores = customers
    .Select(customer => GetRiskScore(riskApi, customer))
    .ToList();

Maybe<RiskScore> score =
    maybeCustomer.Map(customer => GetRiskScore(riskApi, customer));
```

The `ToList()` call enumerates `customers` and invokes the API request once per enumerated customer. Without `ToList()`, the LINQ query would remain deferred and later enumerations could issue the requests again.

> **Note:** `IO<T>` is not the only way to express execution policy in C#. Direct loops and resilience pipelines often handle retries, timeouts, circuit breakers, and rate limits more directly.

## Represent the deferred operation in the type

The shift is to return a recipe for performing the request later instead of performing it immediately:

```text
(IRiskApi, Customer) -> IO<RiskScore>
```

```csharp
public static IO<RiskScore> GetRiskScoreIO(IRiskApi riskApi, Customer customer)
{
    return IO<RiskScore>.Delay(() => riskApi.GetCurrentScore(customer.Id));
}
```

Calling `GetRiskScoreIO` constructs an `IO<RiskScore>`. It does not call the API.

The lambda captures `riskApi` and `customer`, so captured mutable state is read when the delegate runs. Making the computation itself a value lets inner functions return it, outer functions combine it, and a boundary execute it later.

Materializing a mapping over customers produces a list of separate request recipes:

```csharp
List<IO<RiskScore>> requests = customers
    .Select(customer => GetRiskScoreIO(riskApi, customer))
    .ToList();
```

No API requests have started. The useful next step is to combine those recipes into an `IO<List<RiskScore>>`: one larger deferred program with an explicit traversal policy. The appendix shows one implementation.

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

    public T Run()
    {
        return operation();
    }
}
```

`Pure` and `Delay` should not be confused:

```csharp
IO<int> value = IO<int>.Pure(42);
```

`Pure` receives a value that has already been computed. It does not defer evaluation of its argument:

```csharp
// The file is read before Pure is called.
IO<string> eager = IO<string>.Pure(File.ReadAllText(path));
```

Use `Delay` to suspend the read:

```csharp
IO<string> deferred = IO<string>.Delay(() => File.ReadAllText(path));
```

C# evaluates a method argument before invoking the target method, which is why wrapping an effectful expression in `Pure` cannot defer it.

The `Select` and `SelectMany` methods permit the C# query syntax used later. A `let` clause uses `Select`, while a second `from` clause uses the two-function `SelectMany` form included above.

For an effect whose only interesting result is that it completed, use a one-value `Unit` type:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}
```

This `Unit` is roughly `void` as a value. It is not the value-lifting operation that Part 1 called `Unit`; that operation is named `Pure` here to keep the two concepts distinct.

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

Assume `ParseOrder` and `RenderReport` are total pure functions:

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

### From a list of recipes to one recipe

Mapping `GetRiskScoreIO` over customers and materializing the result produces a `List<IO<RiskScore>>`:

```csharp
List<IO<RiskScore>> requests = customers
    .Select(customer => GetRiskScoreIO(riskApi, customer))
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

If you wanted pauses between items or some other batch policy, that would belong in each `IO` or in a different traversal helper.

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
