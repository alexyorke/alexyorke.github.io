---
title: "Monads in C# (Part 3): A Tiny, Synchronous IO"
date: 2026-06-13
description: "A toy IO wrapper can mark deliberately deferred effects and compose them before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

> **Scope:** The `IO<T>` below is a synchronous, non-memoized teaching model built on `Func<T>`. It executes on the caller's thread, repeats its effects on every `Run()`, lets exceptions escape, and provides no built-in cancellation, asynchronous I/O, concurrency, resource bracketing, or stack safety. It is not a production abstraction.

Earlier in this series, many of the teaching examples passed pure functions to `Map` and `FlatMap`. Part 2 also used repository lookups and mutation pragmatically, but it did not examine what happens when the number, order, or timing of those operations becomes observable.

An effect is observable behavior beyond returning a value: for example, I/O, mutation, observing time or randomness, or throwing an exception. Whole programs usually need effects somewhere because results have to be displayed, stored, sent, or otherwise observed. This article focuses mainly on I/O and externally visible state.

For a terminating pure function, the observable result depends only on its explicit inputs. Given the same arguments, it produces the same result, and evaluating it causes no other observable behavior.

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

At this level of reasoning, discarding `totalA` does not change the observable behavior of the program. The next invocation still produces `107.35`.

The first place this matters is the operation that applies your function. The eager `List.Map` helper from Part 1 invokes the function once for every element. `Maybe.Map` invokes it zero or one times. `Result.Map` invokes it only when a successful value is present.

When the function is pure, those rules only affect which values are returned. When the function has effects, the same rules also decide how many times those effects happen. A list of ten customers can mean ten API calls. A missing `Maybe` value can mean no API call. A failed `Result` can mean the next effectful step is skipped. For other monads, the rules differ.

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

Discarding `firstScore` does not undo the first API call. The next invocation is not guaranteed to return the same score: the service may have newer data, record audit or usage state, consume quota, change a cache, reject an expired token, throttle or rate-limit the caller, or be temporarily unavailable even though the visible arguments are the same.

With effects, execution policy becomes part of the program's observable behavior:

* when an operation runs;
* whether it runs;
* in what order it runs;
* how many times it runs.

For a pure function, those invocation details do not change the value-level meaning: the caller only observes returned values. For an effectful function, delegating invocation to `List.Map`, `Maybe.Map`, `Result.Map`, or another mapping operation also delegates part of the execution policy. That abstraction can decide whether the function is called, how often it is called, and what prior effects later operations may observe.

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

Direct loops and ordinary .NET resilience tools are often the right approach in C#. Wrapping an operation in `IO<T>` is not the only way to express execution policy. Ordinary loops, decorators, schedulers, and resilience pipelines can supply retries, timeouts, circuit breakers, rate limits, and related behavior.

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

If you map `GetRiskScoreIO` over a list of customers, the result is a `List<IO<RiskScore>>`: a list of deferred request recipes, not a list of scores and not one larger combined program. Combining many `IO` recipes into one larger recipe is useful, but it is a separate sequencing topic; the appendix sketches it.

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

    public T Run()
    {
        return operation();
    }
}
```

`Delay` stores a function without invoking it.

`Pure` puts an already-computed value into `IO<T>`. It does not defer evaluation of its argument.

This defeats deferral when the expression itself performs an effect:

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

* `Run()` executes synchronously on the calling thread.
* Every call to `Run()` invokes the stored delegate again unless caching is added explicitly.
* Exceptions are delayed, not modeled as values. They escape when `Run()` executes.
* Captured mutable state is observed when the delegate runs, not when the `IO<T>` is constructed.

`Task<T>` is the usual .NET tool for asynchronous work, and it is a good fit for the Task-based Asynchronous Pattern.

This example deliberately avoids it because the article is focused on cold deferral. Under the normal Task-based Asynchronous Pattern, tasks returned by asynchronous methods are active: the represented operation has already been initiated. Consumers are not expected to call `Start()` on those tasks.

This `IO<T>` is different. It is a cold computation that does not start until `Run()` is called.

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

The dependent operations can now be composed in order:

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
* A sequencing helper can commit to one-at-a-time traversal over many operations; the appendix shows one such helper.
* A retry combinator could commit to repeating a particular operation.
* An external resilience pipeline could provide retries, timeouts, circuit breaking, or rate limiting.
* Resource lifetime must still be handled with a construct such as `using`, `await using`, or an equivalent bracket operation. C#'s `using` statement guarantees disposal even when an exception leaves the block.

A richer effect system could preserve an inspectable description of individual operations and use a programmable interpreter or runtime. This toy implementation erases the composed structure into nested delegates, so `Run()` is only a runner.

## Conclusion

The useful distinction is between a value and a deferred computation that may perform observable effects before producing a value.

This toy `IO<T>` makes deliberately wrapped computations composable and provides an explicit point at which to start them. It delays execution; it does not enforce purity or leave every execution-policy decision until `Run()`.

Order, traversal, retry, cancellation, concurrency, failure, and resource behavior are determined by the combinators and runtime used to construct the program.

In this implementation, `Run()` simply executes the resulting synchronous, replayable thunk.

## Appendix

### Optional C# query syntax support

C# query syntax is translated by the compiler into method calls such as `Select` and `SelectMany`. That syntax is not restricted to enumerable collections; another type can participate by providing methods with the required shapes.

```csharp
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
```

With those methods added to `IO<T>`, the earlier program can also be written with query syntax:

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

That operation is commonly called `Sequence`. A related operation called `Traverse` combines mapping with sequencing. The standard Haskell operations likewise distinguish `sequence`, which turns a list of actions into one action producing a list, from `mapM`, which first maps an action-producing function over the inputs.

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
* another call to `Run()` attempts to enumerate the source and perform every operation again.

`Run()` starts the program whose sequencing behavior has already been constructed.

As elsewhere, C# cannot enforce that `action` merely constructs an `IO<TResult>`. A caller could pass a function that performs an effect before returning its recipe.
