---
title: "Monads in C# (Part 3): A Tiny, Synchronous IO"
date: 2026-06-13
description: "A toy IO wrapper can mark deliberately deferred effects and compose them before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

> **Scope:** The `IO<T>` below is a synchronous, non-memoized teaching model built on `Func<T>`. It executes on the caller's thread, repeats its effects on every `Run()`, lets exceptions escape, and provides no built-in cancellation, asynchronous I/O, concurrency, resource bracketing, or stack safety. It is not a production abstraction.

Earlier in this series, many of the teaching examples passed pure functions to `Map` and `FlatMap`. Part 2 also used repository lookups and mutation pragmatically, but it did not examine what happens when the number, order, or timing of those operations becomes observable.

An effect is observable behavior beyond returning a value: for example, I/O, mutation, observing time or randomness, or throwing an exception. This article focuses mainly on I/O and externally visible state.

A pure function's observable result depends only on its explicit inputs. Given the same arguments, it produces the same result, and evaluating it causes no other observable behavior.

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

decimal first = CalculateTotal(100m, 0.13m, 5m);   // 107.35
decimal second = CalculateTotal(100m, 0.13m, 5m);  // 107.35
```

Discarding `first` does not change the observable behavior of the program. The second invocation still produces `107.35`.

This matters first at the `Map` level. An eager list map invokes its function once for every element. `Maybe.Map` invokes it zero or one times. `Result.Map` invokes it only when a successful value is present.

When the function is pure, those differences affect only the returned values. When the function has effects, they also determine how many times those effects happen.

Strictly speaking, `Map` is the functor operation. `FlatMap`, also called bind, is the monadic operation used when the next function returns another value in the same context. ([Haskell][1])

In this article, `List.Map` refers to the eager `List<T>` helper introduced in Part 1. It is not LINQ's deferred `IEnumerable<T>.Select`. A deferred LINQ query can run later and can repeat its selector when enumerated more than once, which matters when the selector has side effects. ([Microsoft Learn][2])

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

The first request might succeed and the second might time out. The calls might return different scores, consume quota, encounter a rate limit, or observe different service state even though the explicit arguments are the same objects.

With effects, evaluation behavior becomes observable:

* when an operation runs;
* whether it runs;
* in what order it runs;
* how many times it runs.

In procedural code, the programmer often controls that behavior directly:

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

The loop specifies the execution behavior: requests run in sequence, a particular exception causes one retry, and later customers are not processed if an unhandled exception escapes.

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

This is not necessarily wrong. It is simply important once invocation itself is observable.

Wrapping an operation in `IO<T>` is also not the only way to express execution policy. Ordinary loops, decorators, schedulers, and .NET resilience pipelines can supply retries, timeouts, circuit breakers, rate limits, and related behavior. ([Microsoft Learn][3])

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

This does not make C# pure, and it does not prevent effects from being hidden inside ordinary delegates. It marks only the operations that the programmer deliberately wraps in `IO<T>`.

There is also no non-executing conversion from `IO<T>` to `T`. In this implementation, producing the `T` means calling `Run()`, and calling `Run()` executes the stored computation.

Keeping `Run()` at a small number of outer boundaries is a programming convention. The C# type system does not enforce it.

## A small `IO<T>`

```csharp
public sealed class IO<T>
{
    private readonly Func<T> operation;

    private IO(Func<T> operation)
    {
        ArgumentNullException.ThrowIfNull(operation);

        this.operation = operation;
    }

    public static IO<T> Delay(Func<T> operation)
    {
        return new IO<T>(operation);
    }

    public static IO<T> Pure(T value)
    {
        return new IO<T>(() => value);
    }

    public IO<TResult> Map<TResult>(
        Func<T, TResult> map)
    {
        ArgumentNullException.ThrowIfNull(map);

        return new IO<TResult>(() =>
        {
            T value = Run();

            return map(value);
        });
    }

    public IO<TResult> FlatMap<TResult>(
        Func<T, IO<TResult>> next)
    {
        ArgumentNullException.ThrowIfNull(next);

        return new IO<TResult>(() =>
        {
            T value = Run();
            IO<TResult> nextOperation = next(value);

            return nextOperation.Run();
        });
    }

    public IO<TResult> Select<TResult>(
        Func<T, TResult> select)
    {
        return Map(select);
    }

    public IO<TResult> SelectMany<TNext, TResult>(
        Func<T, IO<TNext>> next,
        Func<T, TNext, TResult> project)
    {
        ArgumentNullException.ThrowIfNull(next);
        ArgumentNullException.ThrowIfNull(project);

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

`Delay` stores a function without invoking it.

`Pure` puts an already-computed value into `IO<T>`. It does not defer evaluation of its argument.

This is wrong when the expression itself performs an effect:

```csharp
IO<string> text =
    IO<string>.Pure(File.ReadAllText(path));
```

The file is read before `Pure` is called.

Use `Delay` to defer the read:

```csharp
IO<string> text =
    IO<string>.Delay(
        () => File.ReadAllText(path));
```

`Map` is intended for transformations that do not introduce another `IO` layer. `FlatMap` is used when the next step returns another `IO`.

C# cannot enforce that the function passed to `Map` is pure. This compiles:

```csharp
IO<int> program =
    IO<int>.Pure(42)
        .Map(value =>
        {
            Console.WriteLine(value);

            return value;
        });
```

The console write is delayed because the mapping function is called from the stored recipe, but nothing in the `Map` signature reveals that the function writes to the console.

This implementation also has several important runtime semantics:

* It is synchronous. `Run()` executes on the calling thread.
* It is non-memoized. Every call to `Run()` invokes the stored delegate again.
* Exceptions are delayed, not modeled as values. They escape when `Run()` executes.
* A deeply nested chain of `Map` or `FlatMap` calls is not stack-safe.
* Captured mutable state is observed when the delegate runs, not necessarily when the `IO<T>` is constructed.
* Running the same `IO<T>` concurrently is only as safe as the code and state captured by its delegate.

The name `IO` is conventional, but this particular implementation is only a thin wrapper around a synchronous `Func<T>`.

## Why this is not `Task<T>`

This example deliberately avoids `Task<T>`.

Under the normal .NET Task-based Asynchronous Pattern, tasks returned by asynchronous methods are active: the represented operation has already been initiated. Consumers are not expected to call `Start()` on those tasks. ([Microsoft Learn][4])

This `IO<T>` is different. It is a cold computation that does not start until `Run()` is called.

A realistic asynchronous effect abstraction would also need to address cancellation and resource lifetime, perhaps by storing something such as:

```csharp
Func<CancellationToken, Task<T>>
```

That is outside the scope of this synchronous teaching type.

## From a list of recipes to one recipe

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

`FlatMap` cannot by itself turn the first shape into the second. `FlatMap` removes a nested layer when both layers use the same abstraction:

```text
IO<IO<T>>     -> IO<T>
List<List<T>> -> List<T>
```

`List<IO<T>>` contains two different structures. Combining them requires a rule for how the list is traversed and how the individual operations are run.

That operation is commonly called `Sequence`. A related operation called `Traverse` combines mapping with sequencing. The standard Haskell operations likewise distinguish `sequence`, which turns a list of actions into one action producing a list, from `mapM`, which first maps an action-producing function over the inputs. ([Haskell][1])

Here is one specific traversal:

```csharp
public static class IOExtensions
{
    public static IO<List<TResult>>
        TraverseSequential<T, TResult>(
            this IEnumerable<T> source,
            Func<T, IO<TResult>> action)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(action);

        return IO<List<TResult>>.Delay(() =>
        {
            var results = new List<TResult>();

            foreach (T item in source)
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
            operation => operation);
    }
}
```

The list of request recipes can now become one larger recipe:

```csharp
IO<List<RiskScore>> scoresProgram =
    requests.SequenceSequential();
```

Or `TraverseSequential` can combine the mapping and sequencing steps directly:

```csharp
IO<List<RiskScore>> scoresProgram =
    customers.TraverseSequential(
        customer => GetRiskScoreIO(
            riskApi,
            customer));
```

This implementation commits to a concrete policy:

* the source is enumerated when `Run()` is called;
* operations run in source order;
* only one operation runs at a time;
* the first thrown exception stops the traversal;
* the result list is returned only if every operation succeeds;
* another call to `Run()` enumerates the source and performs every operation again.

The traversal policy is selected by `TraverseSequential`, not by the final call to `Run()`.

`Run()` starts the program whose sequencing behavior has already been constructed.

As elsewhere, C# cannot enforce that `action` merely constructs an `IO<TResult>`. A caller could pass a function that performs an effect before returning its recipe.

## Building one effectful program

Start with effects that produce useful values:

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

A real parser would usually make failure explicit, perhaps with `Result<Order>`. This `IO<T>` does not do that. Exceptions from parsing, file access, or the API simply escape from `Run()`.

The dependent operations can now be composed in order:

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

C# query syntax is translated by the compiler into method calls such as `Select` and `SelectMany`. That syntax is not restricted to enumerable collections; another type can participate by providing methods with the required shapes. ([Microsoft Learn][5])

<details>
<summary>The same program with Map and FlatMap</summary>

```csharp
public static IO<string> LoadOrderAndRenderReport(
    IExchangeRateApi exchangeRateApi,
    string orderPath)
{
    return ReadAllTextIO(orderPath)
        .Map(ParseOrder)
        .FlatMap(order =>
            FetchExchangeRateIO(
                    exchangeRateApi,
                    order.Currency)
                .Map(exchangeRate =>
                    RenderReport(
                        order,
                        exchangeRate)));
}

public static IO<Unit> LoadOrderAndWriteReport(
    IExchangeRateApi exchangeRateApi,
    string orderPath,
    string reportPath)
{
    return LoadOrderAndRenderReport(
            exchangeRateApi,
            orderPath)
        .FlatMap(report =>
            WriteAllTextIO(
                reportPath,
                report));
}
```

</details>

Constructing the program still performs none of the wrapped effects:

```csharp
IO<Unit> program =
    LoadOrderAndWriteReport(
        exchangeRateApi,
        "order.json",
        "report.txt");
```

The effects begin when the program is run:

```csharp
program.Run();
```

Calling it again repeats the file read, exchange-rate request, and file write:

```csharp
program.Run();
```

Moving effects to the edge means moving the final `Run()` outward by convention. Helper functions return deferred computations, larger functions compose them, and an outer boundary, such as a console application's `Main` method, decides when to start the final program.

This convention does not guarantee that all effects occur at the boundary. C# still permits an effect while constructing an `IO<T>`, inside a function passed to `Map`, or before a value is passed to `Pure`.

## `Run()` is a runner, not an interpreter

In this implementation, `Run()` invokes one opaque `Func<T>`.

It cannot inspect the program and determine which part is an API request, which part is a file write, and which part is pure calculation. It therefore cannot retroactively choose to parallelize independent operations, retry only one request, inject cancellation, or add resource cleanup.

Those decisions must be encoded while constructing the program:

* `FlatMap` commits to dependent sequential composition.
* `TraverseSequential` commits to one-at-a-time traversal.
* A retry combinator could commit to repeating a particular operation.
* An external resilience pipeline could provide retries, timeouts, circuit breaking, or rate limiting. ([Microsoft Learn][3])
* Resource lifetime must still be handled with a construct such as `using`, `await using`, or an equivalent bracket operation. C#'s `using` statement guarantees disposal even when an exception leaves the block. ([Microsoft Learn][6])

A richer effect system could preserve an inspectable description of individual operations and use a programmable interpreter or runtime. This toy implementation erases the composed structure into nested delegates, so `Run()` is only a runner.

## Conclusion

The useful distinction is between a value and a deferred computation that may perform observable effects before producing a value.

This toy `IO<T>` makes deliberately wrapped computations composable and provides an explicit point at which to start them. It delays execution; it does not enforce purity or leave every execution-policy decision until `Run()`.

Order, traversal, retry, cancellation, concurrency, failure, and resource behavior are determined by the combinators and runtime used to construct the program.

In this implementation, `Run()` simply executes the resulting synchronous, replayable thunk.

[1]: https://www.haskell.org/onlinereport/haskell2010/haskellch13.html "13 Control.Monad"
[2]: https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca1851 "CA1851: Possible multiple enumerations of 'IEnumerable' collection - .NET | Microsoft Learn"
[3]: https://learn.microsoft.com/en-us/dotnet/core/resilience/ "Introduction to resilient app development - .NET | Microsoft Learn"
[4]: https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/task-based-asynchronous-pattern-tap "Task-based Asynchronous Pattern (TAP): Introduction and overview - .NET | Microsoft Learn"
[5]: https://learn.microsoft.com/en-us/dotnet/csharp/linq/get-started/write-linq-queries "Write LINQ queries - C# | Microsoft Learn"
[6]: https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/statements/using "using statement - ensure the correct use of disposable objects - C# reference | Microsoft Learn"
