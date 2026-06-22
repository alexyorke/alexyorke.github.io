---
title: "Monads in C# (Part 3): A Tiny, Synchronous IO"
date: 2026-06-13
description: "A toy IO wrapper can mark deliberately deferred effects and compose them before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

> **Scope:** The `IO<T>` below is a synchronous, non-memoized teaching model built on `Func<T>`. It executes on the caller's thread, repeats its effects on every `Run()`, lets exceptions escape, and provides no built-in cancellation, asynchronous I/O, concurrency, resource bracketing, or stack safety. It is not a production abstraction.

Earlier in this series, many of the teaching examples passed pure functions to `Map` and `FlatMap`. Part 2 also used repository lookups and mutation pragmatically, but it did not examine what happens when the number, order, or timing of those operations becomes observable.

A pure function is one whose observable result depends only on its explicit inputs: given the same arguments, it produces the same result and causes no observable behavior. An effect, also called a side effect, is observable behavior beyond returning a value: printing to the screen, writing to a file, mutating state, observing time or randomness, or throwing an exception. Useful programs usually need effects somewhere so results can be displayed, stored, sent, or logged, and that is why invocation policy becomes observable for effectful code in a way it does not for pure code.

Here is a simple pure function:

```csharp
public static decimal CalculateTotal(
    decimal subtotal,
    decimal taxRate,
    decimal discount)
{
    decimal discountedSubtotal = subtotal - discount;
    decimal tax = discountedSubtotal * taxRate;

    return discountedSubtotal + tax;
}

decimal totalA = CalculateTotal(100m, 0.13m, 5m);  // 107.35
decimal totalB = CalculateTotal(100m, 0.13m, 5m);  // 107.35
```

At this level of reasoning, discarding `totalA` does not change observable behavior: the next invocation still produces `107.35`, and repeated calls do not remember prior executions.

The first place this matters is the operation that applies your function. The eager `List.Map` helper from Part 1 invokes the function once per element, `Maybe.Map` invokes it zero or one times, and `Result.Map` invokes it only when a successful value is present.

For pure functions, those rules change only which values are returned. For effectful functions, they also change what the program does. Each abstraction brings its own execution policy, and effectful functions may care when, whether, or how they are invoked.

Now compare an effectful function:

```csharp
public static RiskScore GetRiskScore(
    IRiskApi riskApi,
    Customer customer)
{
    return riskApi.GetCurrentScore(customer.Id);
}

RiskScore firstScore =
    GetRiskScore(riskApi, customer);

RiskScore secondScore =
    GetRiskScore(riskApi, customer);
```

Discarding `firstScore` does not undo the first API call, and the next invocation is not guaranteed to return the same score: the service may have newer data, record audit or usage state, consume quota, change a cache, reject an expired token, throttle or rate-limit the caller, or be temporarily unavailable even though the visible arguments are the same. That first call can also affect downstream visible state even though none of that changed state is passed explicitly to the second call as an argument.

With effects, execution policy becomes part of the program's observable behavior:

* when an operation runs, including relative timing;
* whether it runs;
* in what order it runs;
* how many times it runs.

For pure functions, those details do not change the value-level meaning; for effectful functions, they can change the next visible state of the world. If an abstraction changes any of those details, it may change the program's visible behavior.

In procedural code, the programmer often controls that execution policy directly:

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

The loop fixes the execution policy: requests run in sequence, one particular exception causes one retry, and an unhandled exception stops later customers.

The ordinary method type does not distinguish this request from an in-memory calculation:

```text
(IRiskApi, Customer) -> RiskScore
```

Passing the function to another abstraction hands some invocation control to that abstraction:

```csharp
List<RiskScore> scores =
    customers.Map(
        customer => GetRiskScore(riskApi, customer));

Maybe<RiskScore> score =
    maybeCustomer.Map(
        customer => GetRiskScore(riskApi, customer));
```

Here `List.Map` invokes the request once per customer, while `Maybe.Map` invokes it zero or one times.

> **Note:** `IO<T>` is not the only way to express execution policy in C#. Direct loops, decorators, schedulers, and .NET resilience pipelines can supply retries, timeouts, circuit breakers, and rate limits, and they are often the more ordinary approach.

## Represent the deferred operation in the type

Instead of returning the result of the request immediately, return a recipe for performing it:

```text
(IRiskApi, Customer) -> IO<RiskScore>
```

```csharp
public static IO<RiskScore> GetRiskScoreIO(
    IRiskApi riskApi,
    Customer customer)
{
    return IO<RiskScore>.Delay(
        () => riskApi.GetCurrentScore(customer.Id));
}
```

Calling `GetRiskScoreIO` constructs an `IO<RiskScore>`, not a score and not an API call. `IO<T>` helps not just by delaying effects, but by making the effectful computation itself into a value that inner functions can return, outer functions can combine, and a boundary can run later. The wrapped effect is still the same effect, but it can now be assembled into a larger program before anything happens. Mapping it over customers therefore yields `List<IO<RiskScore>>`, a list of inert request recipes; the appendix shows one concrete way to turn that into `IO<List<RiskScore>>`.

## A small `IO<T>`

```csharp
public sealed class IO<T>
{
    private readonly Func<T> operation;

    private IO(Func<T> operation)
    {
        this.operation = operation;
    }

    public static IO<T> Delay(Func<T> operation)
    {
        return new IO<T>(operation);
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

To defer a file read, the read itself has to happen inside the stored function:

```csharp
IO<string> text =
    IO<string>.Delay(
        () => File.ReadAllText(path));
```

Use `Map` when the next step returns a plain value and `FlatMap` when it returns another `IO`.

C# cannot enforce that the function passed to `Map` is pure. This compiles:

```csharp
IO<int> program =
    IO<int>.Delay(() => 42)
        .Map(value =>
        {
            Console.WriteLine(value);

            return value;
        });
```

The console write is delayed here, but the `Map` signature does not reveal that the mapping function has effects.

This implementation also has several important runtime semantics:

* `Run()` executes on the calling thread.
* Each call to `Run()` invokes the stored delegate again unless caching is added.
* Exceptions are delayed rather than modeled as values.
* Captured mutable state is observed when the delegate runs.

Nothing here memoizes results or preserves an inspectable tree of operations; the recipe is just a stored delegate and whatever other delegates get nested into it during composition.

`Task<T>` is the usual .NET abstraction for asynchronous work. This article instead uses a cold computation that does not start until `Run()` is called.

## Building one effectful program

Suppose the goal is to read an order from disk, fetch the current exchange rate for its currency, render a report, and write that report to disk. Start with effects that produce the intermediate values:

```csharp
public static IO<string> ReadAllTextIO(
    string path)
{
    return IO<string>.Delay(
        () => File.ReadAllText(path));
}

public static IO<decimal> FetchExchangeRateIO(
    IExchangeRateApi exchangeRateApi,
    string currency)
{
    return IO<decimal>.Delay(
        () => exchangeRateApi.GetCurrentRate(currency));
}
```

Writing a file matters mainly because it happened, so use a small `Unit` value when there is no more useful result:

```csharp
public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}

public static IO<Unit> WriteAllTextIO(
    string path,
    string contents)
{
    return IO<Unit>.Delay(() =>
    {
        File.WriteAllText(path, contents);

        return Unit.Value;
    });
}
```

Assume `ParseOrder` and `RenderReport` are pure, `ParseOrder` is total, and `IO<T>` also provides the standard `Select` / `SelectMany` methods required by C# query syntax.

```csharp
public static IO<string> LoadOrderAndRenderReport(
    IExchangeRateApi exchangeRateApi,
    string orderPath)
{
    return
        from json in ReadAllTextIO(orderPath)
        let order = ParseOrder(json)
        from exchangeRate in FetchExchangeRateIO(
            exchangeRateApi,
            order.Currency)
        select RenderReport(order, exchangeRate);
}

public static IO<Unit> LoadOrderAndWriteReport(
    IExchangeRateApi exchangeRateApi,
    string orderPath,
    string reportPath)
{
    return
        from report in LoadOrderAndRenderReport(
            exchangeRateApi,
            orderPath)
        from ignored in WriteAllTextIO(
            reportPath,
            report)
        select ignored;
}
```

Constructing the program still performs none of the wrapped effects:

```csharp
IO<Unit> program =
    LoadOrderAndWriteReport(
        exchangeRateApi,
        "order.json",
        "report.txt");
```

At that point, the caller has one larger recipe whose execution can still be controlled as a unit.

The effects begin when the program is run:

```csharp
program.Run();
```

Calling it again repeats the file read, exchange-rate request, and file write:

```csharp
program.Run();
```

What moves to the edge is `Run()`, not `IO<T>`. `IO<T>` values can appear deep in the call graph and still be composed into larger deferred programs; scattered descriptions are fine. The loss of control happens when helpers call `Run()` early and collapse part of the description into an already performed effect.

## `Run()` is a runner, not an interpreter

In this implementation, `Run()` invokes one opaque `Func<T>`. It cannot inspect the program to distinguish API requests from file writes or pure calculations, so it cannot retroactively choose parallelism, retries, cancellation, or cleanup. By the time `Run()` is called, the larger recipe has already been collapsed into nested delegates. Control therefore comes from the combinators that shaped the program and from where that recipe is run.

Those decisions must be encoded while constructing the program:

* `FlatMap` and sequencing helpers fix composition and traversal policy.
* Retries, timeouts, and rate limits can come from combinators or external resilience pipelines.
* Resource lifetime still needs `using`, `await using`, or an equivalent bracket operation; `using` guarantees disposal when an exception escapes.

A richer effect system could preserve an inspectable description of the program, but this toy implementation erases structure into nested delegates, so `Run()` is only a runner.

## Conclusion

The key distinction is between a value and a deferred computation that may perform observable effects before producing a value. This toy `IO<T>` restores composability by making the effectful computation itself a first-class value that can be combined before execution.

Here `Run()` merely executes the resulting synchronous, replayable thunk. Order, traversal, retries, and resource behavior still come from the combinators and runtime used to build the program. The discipline is to centralize execution, not to ban `IO<T>` from the rest of the program.

## Appendix

<details>
<summary>Open the appendix for sequential traversal</summary>

### From a list of recipes to one recipe

Mapping `GetRiskScoreIO` over the customers produces a `List<IO<RiskScore>>`: separate request recipes, with no requests started yet. `IO<List<RiskScore>>` is different: it is one larger recipe that, when run, traverses the collection and produces the list.

```csharp
List<IO<RiskScore>> requests =
    customers.Map(
        customer => GetRiskScoreIO(riskApi, customer));
```

```text
List<IO<RiskScore>>
IO<List<RiskScore>>
```

`FlatMap` alone cannot turn `List<IO<T>>` into `IO<List<T>>` because the two layers use different structures, so you need a rule for how the list is traversed and how the operations are run. Deferral made the individual requests composable as values; traversal chooses how to combine many of those values into one larger program.

Two useful shapes are:

```text
Sequence:
List<IO<T>> -> IO<List<T>>

Traverse:
List<A> x (A -> IO<B>) -> IO<List<B>>
```

`Sequence` handles computations already in hand. `Traverse` maps inputs to computations and sequences the results. `Sequence` is traversal with the identity function, and `Traverse` is usually presented in applicative terms.

Here is one specific traversal:

```csharp
public static class IOExtensions
{
    public static IO<List<TResult>>
        TraverseSequential<TSource, TResult>(
            this IEnumerable<TSource> source,
            Func<TSource, IO<TResult>> action)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(action);

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

    public static IO<List<T>> SequenceSequential<T>(
        this IEnumerable<IO<T>> source)
    {
        return source.TraverseSequential(
            static operation => operation);
    }
}
```

`TraverseSequential` contributes a particular policy:

* enumerate in source order;
* execute one `IO` at a time;
* stop when an unhandled exception escapes;
* preserve result order;
* return one `IO<List<T>>`.

Some effect libraries also offer parallel variants such as `parTraverse`.

The list of request recipes can now become one larger recipe:

```csharp
IO<List<RiskScore>> program =
    requests.SequenceSequential();
```

Or `TraverseSequential` can combine the mapping and sequencing steps directly:

```csharp
IO<List<RiskScore>> program =
    customers.TraverseSequential(
        customer => GetRiskScoreIO(
            riskApi,
            customer));
```

`TraverseSequential` does not run the requests. It returns one larger deferred computation.

```csharp
List<RiskScore> scores = program.Run();
```

That outer `Run()` starts the traversal, and the nested `Run()` calls inside `TraverseSequential` are internal details of that one larger recipe. Application code still initiates one top-level program at the edge. The callback passed to `TraverseSequential` should construct an `IO`, not perform the effect before returning it.

</details>
