---
title: "Monads in C# (Part 3): A Tiny, Synchronous IO"
date: 2026-06-13
description: "A toy IO wrapper can mark deliberately deferred effects and compose them before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

> **Scope:** The `IO<T>` below is a synchronous, non-memoized teaching model built on `Func<T>`. It executes on the caller's thread, repeats its effects on every `Run()`, lets exceptions escape, and provides no built-in cancellation, asynchronous I/O, concurrency, resource bracketing, or stack safety. It is not a production abstraction.

Earlier in this series, many of the teaching examples passed pure functions to `Map` and `FlatMap`. Part 2 also used repository lookups and mutation pragmatically, but it did not examine what happens when the number, order, or timing of those operations becomes observable.

Recall that a pure function is one whose observable result depends only on its explicit inputs. Given the same arguments, it produces the same result, and evaluating it causes no observable behavior.

An effect, also called a side effect, is observable behavior beyond returning a value: for example, printing something to the screen, writing to a file, mutating state, observing time or randomness, or throwing an exception. Whole programs usually need effects somewhere to be useful: results usually have to be displayed, stored, sent, logged, or otherwise observed. Without some external observation, a finished computation leaves no evidence that it happened at all. This article focuses mainly on I/O and externally visible state.

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

At this level of reasoning, discarding `totalA` does not change the observable behavior of the program. The next invocation still produces `107.35`, and repeated calls do not accumulate state or remember prior executions.

The first place this matters is the operation that applies your function. The eager `List.Map` helper from Part 1 invokes the function once for every element. `Maybe.Map` invokes it zero or one times. `Result.Map` invokes it only when a successful value is present.

When the function is pure, those rules only affect which values are returned. When the function has effects, they also affect what the program does: a list of ten customers can mean ten API calls, a missing `Maybe` value can mean no API call, and a failed `Result` can mean the next effectful step is skipped. You can think of each monad as bringing its own execution policy: pure functions usually remain composable because they do not care about that policy, but effectful functions may produce different outcomes when the abstraction is free to choose when, whether, or how to run them.

> Note: I am starting with `Map` because it is the simplest place to see the invocation question. Strictly speaking, `Map` is the functor operation. `FlatMap`, also called bind, is the monadic operation used when the next function returns another value in the same context.

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

Calling `GetRiskScore` twice is not equivalent to calling `CalculateTotal` twice.

Discarding `firstScore` does not undo the first API call. The next invocation is not guaranteed to return the same score: the service may have newer data, record audit or usage state, consume quota, change a cache, reject an expired token, throttle or rate-limit the caller, or be temporarily unavailable even though the visible arguments are the same. That first call can also affect downstream visible state even though none of that changed state is passed explicitly to the second call as an argument.

With effects, execution policy becomes part of the program's observable behavior:

* when an operation runs, including relative timing;
* whether it runs;
* in what order it runs;
* how many times it runs.

For a pure function, those invocation details do not change the value-level meaning: the caller only observes returned values. For an effectful function, they can change the next visible state of the world. One way to reason about this is that effectful code is implicitly threaded through a changing world state rather than operating only on explicit arguments.

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

The loop specifies the execution policy: requests run in sequence, a particular exception causes one retry, and later customers are not processed if an unhandled exception escapes.

The ordinary method type does not distinguish this request from an in-memory calculation:

```text
(IRiskApi, Customer) -> RiskScore
```

Passing the function to another abstraction transfers some control over invocation to that abstraction:

```csharp
List<RiskScore> scores =
    customers.Map(
        customer => GetRiskScore(riskApi, customer));

Maybe<RiskScore> score =
    maybeCustomer.Map(
        customer => GetRiskScore(riskApi, customer));
```

The eager list map invokes the request once for every customer. `Maybe.Map` invokes it zero or one times.

> **Note:** `IO<T>` is not the only way to express execution policy in C#. Direct loops, decorators, schedulers, and .NET resilience pipelines can supply retries, timeouts, circuit breakers, and rate limits, and they are often the more ordinary approach.

The narrower benefit of `IO<T>` is that a deliberately deferred operation becomes a value. Code can return, combine, and rearrange that value without starting the operation immediately.

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

Calling `GetRiskScoreIO` constructs an `IO<RiskScore>`. It does not call the API.

`IO<RiskScore>` does not contain a completed `RiskScore`. It contains a computation that may produce one when executed.

`IO<T>` helps not merely by postponing effects, but by making an effectful computation into a value. Inner functions can return `IO<T>` recipes without executing them, outer functions can combine those recipes into larger recipes, and a boundary can decide later when to start the finished program.

If you map `GetRiskScoreIO` over a list of customers, the result is a `List<IO<RiskScore>>`: a list of deferred request recipes, not a list of scores and not one larger combined program. How that becomes `IO<List<RiskScore>>` is a separate sequencing topic, and the appendix gives one concrete answer. That composition works because the recipes are inert values until execution, not because the effects somehow became safe on their own.

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

`Delay` stores a function without invoking it.

To defer a file read, the read itself has to happen inside the stored function:

```csharp
IO<string> text =
    IO<string>.Delay(
        () => File.ReadAllText(path));
```

`Map` is intended for transformations that do not introduce another `IO` layer. `FlatMap` is used when the next step returns another `IO`.

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

The console write is delayed because the mapping function is called from the stored recipe, but nothing in the `Map` signature reveals that the function writes to the console.

This implementation also has several important runtime semantics:

* `Run()` executes synchronously on the calling thread.
* Every call to `Run()` invokes the stored delegate again unless caching is added explicitly.
* Exceptions are delayed, not modeled as values. They escape when `Run()` executes.
* Captured mutable state is observed when the delegate runs, not when the `IO<T>` is constructed.

`Task<T>` is the usual .NET tool for asynchronous work, and it is a good fit for the Task-based Asynchronous Pattern.

This example deliberately avoids it because the article is focused on cold deferral. Under the normal Task-based Asynchronous Pattern, tasks returned by asynchronous methods are active: the represented operation has already been initiated. Consumers are not expected to call `Start()` on those tasks.

This `IO<T>` is different. It is a cold computation that does not start until `Run()` is called.

## Building one effectful program

Suppose the goal is to read an order from disk, fetch the current exchange rate for the order's currency, render a report, and then write that report to disk.

Start with effects that produce the intermediate values:

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

Writing a file matters primarily because the write happened. Since `IO<T>` still has a type parameter, use a small `Unit` value when there is no more useful result:

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

For this example, assume that `ParseOrder` and `RenderReport` are pure and that `ParseOrder` is total: it always returns an `Order` rather than throwing or returning a failure.

The dependent operations can now be composed in order:

Assume `IO<T>` also provides the standard `Select` / `SelectMany` methods required by C# query syntax.

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

What moves to the edge is `Run()`, not `IO<T>` itself. Helper functions can return `IO<T>` from deep inside the application, larger functions can compose those deferred computations into bigger ones, and an outer boundary, such as a console application's `Main` method, can decide when to start the final program. Calling `Run()` deep in the program gives up that compositional benefit because the effect has already happened.

This convention does not guarantee that all effects occur at the boundary. `IO<T>` can appear throughout the call graph, and that is not itself a loss of control. The loss of control happens when execution, not description, is mixed everywhere. Once a helper executes an effect early, surrounding code can no longer incorporate that step into one larger deferred program.

## `Run()` is a runner, not an interpreter

In this implementation, `Run()` invokes one opaque `Func<T>`.

It cannot inspect the program and determine which part is an API request, which part is a file write, and which part is pure calculation. It therefore cannot retroactively choose to parallelize independent operations, retry only one request, inject cancellation, or add resource cleanup.

Once execution has been described as one larger recipe, control comes from where and how that recipe is run, but this toy `IO<T>` still cannot inspect or optimize the recipe after construction.

Those decisions must be encoded while constructing the program:

* `FlatMap` commits to dependent sequential composition.
* A sequencing helper can commit to one-at-a-time traversal over many operations; the appendix shows one such helper.
* A retry combinator could commit to repeating a particular operation.
* An external resilience pipeline could provide retries, timeouts, circuit breaking, or rate limiting.
* Resource lifetime must still be handled with a construct such as `using`, `await using`, or an equivalent bracket operation. C#'s `using` statement guarantees disposal even when an exception leaves the block.

A richer effect system could preserve an inspectable description of individual operations and use a programmable interpreter or runtime. This toy implementation erases the composed structure into nested delegates, so `Run()` is only a runner.

## Conclusion

The useful distinction is between a value and a deferred computation that may perform observable effects before producing a value.

This toy `IO<T>` makes deliberately wrapped computations composable and provides an explicit point at which to start them. It delays execution, but the deeper benefit is that effectful programs become first-class values that can be combined before any effect occurs. It does not enforce purity or leave every execution-policy decision until `Run()`.

Order, traversal, retry, cancellation, concurrency, failure, and resource behavior are determined by the combinators and runtime used to construct the program.

In this implementation, `Run()` simply executes the resulting synchronous, replayable thunk. The practical discipline is to centralize execution, not to ban `IO<T>` from the rest of the program.

## Appendix

<details>
<summary>Open the appendix for sequential traversal</summary>

### From a list of recipes to one recipe

Mapping `GetRiskScoreIO` over the customers constructs a list of request recipes:

```csharp
List<IO<RiskScore>> requests =
    customers.Map(
        customer => GetRiskScoreIO(riskApi, customer));
```

No API request has happened yet.

The types describe two different shapes:

```text
List<IO<RiskScore>>
IO<List<RiskScore>>
```

`List<IO<RiskScore>>` is a collection of separate recipes.

`IO<List<RiskScore>>` is one larger recipe that, when run, performs some traversal and produces a list.

A single `FlatMap` on either structure is not enough to turn the first shape into the second. `FlatMap` removes a nested layer when both layers use the same abstraction:

```text
IO<IO<T>>     -> IO<T>
List<List<T>> -> List<T>
```

`List<IO<T>>` contains two different structures. Combining them requires a rule for how the list is traversed and how the individual operations are run.

Two useful shapes are:

```text
Sequence:
List<IO<T>> -> IO<List<T>>

Traverse:
List<A> x (A -> IO<B>) -> IO<List<B>>
```

`Sequence` handles computations that already exist. `Traverse` maps inputs to computations and sequences the results. `Sequence` is traversal with the identity function. In general functional-programming terminology, `Traverse` is usually presented in applicative terms.

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

Effect libraries often distinguish this ordinary sequential traversal from parallel traversal operations such as `parTraverse`.

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

Calling `TraverseSequential` does not run the requests. It returns one larger deferred computation.

```csharp
List<RiskScore> scores = program.Run();
```

That outer `Run()` starts the traversal. During that execution, `TraverseSequential` runs each component `IO` in order. The nested calls to `Run()` inside `TraverseSequential` are internal to one larger deferred program, so application code still starts one top-level program at the edge. The callback passed to `TraverseSequential` should construct an `IO`, not perform the effect before returning it.

</details>
