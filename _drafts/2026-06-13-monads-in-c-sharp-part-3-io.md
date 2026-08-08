---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> turns effectful work into a cold value. FlatMap composes those values, while UnsafeRun() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

The first two parts applied the same pattern to `List`, `Maybe`, and `Result`: lift a value, then use `FlatMap` to compose a dependent step while the context determines what flows onward.

`IO` is often described as a way to **sequence effects**. That sounds simple, but what needs sequencing, and why?

An effect is an interaction with the world: reading or writing a file, asking for input, calling an API, drawing to the screen, or changing shared state. Programs need effects to be useful. The challenge is that their order, frequency, and even whether they happen can change the program's meaning.

In procedural C#, statement order provides an obvious sequence:

```csharp
File.WriteAllText(path, "first");
File.AppendAllText(path, "second");
```

The first statement runs before the second. Their return values are not the point--both methods return `void`--but executing them changes the file. Reversing, repeating, or skipping either statement changes the result. This is sequencing, supplied by C#'s statement-evaluation rules.

Pure functional code has a different reasoning model. Consider these equations (recall the days from high school algebra):

```text
x = 5 + 1
y = 4 + 9 - 2
w = y + x
z = y + y + x
```

It does not matter whether `x` or `y` is evaluated first. Because `w` does not contribute to `z`, it need not be evaluated at all. Once we know that `y` is `11`, we may replace either occurrence of `y` with `11`, or rewrite `z` as `2y + x`, without changing the answer.

This is **referential transparency**, and it supports **equational reasoning**: replacing equals with equals preserves meaning. Algebra needs no equivalent of the semicolon because evaluating a pure expression cannot change anything else. Evaluation order may affect cost, but it does not affect the result or the world.

Side effects break that model. Consider a stateful counter:

```csharp
private static int count = 0;

public static int Next()
{
    count++;
    return count;
}
```

Starting from zero, `Next() + Next()` evaluates to `1 + 2`, or `3`. The familiar algebraic rewrite `2 * Next()` invokes the counter once and produces `2`. A transformation that was harmless in the algebra example changed both the answer and the number of state changes. Files and APIs behave similarly: repeated calls may observe or create different external states.

Lazy evaluation makes the mismatch especially visible. In a non-strict language such as Haskell, an expression is evaluated only when its value is needed:

```haskell
main = print result
  where
    a = 10
    unused = undefined
    b = 20
    result = a + b
```

Evaluating `undefined` would fail, but `unused` is never demanded, so this program prints `30`. Skipping an unused pure expression only avoids unnecessary work. If effects behaved like ordinary expressions, however, an unused file write could disappear, and two independent operations could run in an order we did not intend. The problem is not only which effect runs first, but whether it runs at all.

The pieces now line up. `IO<T>` represents an operation without performing it: a file write becomes `IO<Unit>`, where `Unit` plays the role of `void`, while a read becomes `IO<int>`. Constructing either does nothing to the file, so the descriptions can be composed first:

```text
current : IO<A>
next    : A -> IO<B>

current.FlatMap(next) : IO<B>
```

`FlatMap` creates one larger `IO<B>` that describes a sequence: perform `current`, give its result to `next`, then perform the `IO<B>` returned by `next`. It adds the dependency that ordinary pure expressions do not need, without performing either effect while the program is being assembled.

Here is the connection: **`IO` makes effects values, `FlatMap` makes their order explicit, and the execution boundary performs the resulting program.** In Haskell, the final `IO` value is exposed as `main`, and the runtime performs the actions it describes. Simon Peyton Jones and Philip Wadler describe this design in [*Imperative functional programming*](https://www.microsoft.com/en-us/research/publication/imperative-functional-programming/). In this article's small C# model, the application passes the final value to `UnsafeRun()`.

The guarantee is conditional: if the composed `IO` program is run, its effects are performed in the sequence encoded by `FlatMap`. An `IO` value that is merely constructed and discarded does not run.

C# already evaluates eagerly and specifies expression order, so this wrapper is not repairing C#'s evaluation semantics or enforcing purity. It makes effectful operations explicit and composable. Despite its name, this tiny `IO<T>` can suspend any synchronous operation, including in-memory mutation; it does not statically distinguish I/O from other effects.

That raises the practical question: why can the effectful code not remain an ordinary function? Why not call it inside `Map` or `Select`, just as we do with pure functions? C# accepts that code. `Enumerable.Select` makes clear what reasoning power is lost.

> **Scope:** This is a teaching model, not a recommendation to replace normal C# application structure or the Task-based Asynchronous Pattern (TAP). It does not enforce purity or provide stack safety, async execution, cancellation, concurrency, or thread safety. The examples target C# 10 and .NET 6 or later.

## Why not compose the function directly?

First consider a pure price calculation composed with `Select`:

```csharp
public static decimal CalculateLineTotal(
    int quantity,
    decimal unitPrice,
    decimal taxRate)
{
    decimal subtotal = quantity * unitPrice;
    return subtotal + subtotal * taxRate;
}

var quantities = new List<int> { 1, 2, 3 };

IEnumerable<decimal> totals =
    quantities.Select(quantity =>
        CalculateLineTotal(quantity, 19.99m, 0.13m));
```

`Select` controls when and how often it invokes the function, but each quantity still determines the same total and enumeration changes nothing outside the calculation.

Now use the same shape with an effectful function:

```csharp
var productIds =
    new List<string> { "A-100", "B-200", "C-300" };

IEnumerable<decimal> prices =
    productIds.Select(productId =>
        remotePriceApi.GetCurrentPrice(productId));

// Select has not enumerated productIds, so it has sent no requests.
```

The requests occur when someone enumerates `prices`. With this synchronous API, enumeration sends one request, waits for it, then moves to the next item. There is no concurrency here.

```csharp
List<decimal> firstRead = prices.ToList();  // Three requests.
List<decimal> secondRead = prices.ToList(); // The same three calls run again.
```

If nobody enumerates the sequence, no request is sent; enumerating twice sends the requests twice. A lazy or mutable source may even supply different inputs. `IEnumerable<T>` defers a many-value traversal, but it does not mark one explicit effect boundary or promise exactly one result.

Both selectors compose mechanically, but only the effectful selector makes enumeration policy part of the program's meaning: enumeration decides whether, when, and how often requests happen.

When an effectful function returns `decimal`, whoever calls it decides when the effect happens: a loop, `Select`, or some other caller. When it returns `IO<decimal>`, that decision moves to whoever calls `UnsafeRun()`.

## From an immediate result to a suspended computation

The signature change is small:

```text
(IRemotePriceApi, string) -> decimal
(IRemotePriceApi, string) -> IO<decimal>
```

The first form must perform the request to produce its `decimal`. The second form constructs a value that can produce a `decimal` later:

```csharp
public static IO<decimal> FetchCurrentPriceIO(
    IRemotePriceApi remotePriceApi,
    string productId)
{
    ArgumentNullException.ThrowIfNull(remotePriceApi);
    ArgumentNullException.ThrowIfNull(productId);

    return IO.Delay(
        () => remotePriceApi.GetCurrentPrice(productId));
}
```

Constructing this value sends no request. C# cannot prevent a method from performing effects before it calls `IO.Delay`.

The returned value is **cold**: constructing and composing it does not invoke the delegate stored by `IO<T>`. Calling `UnsafeRun()` invokes that delegate. The word "unsafe" marks the point where described work becomes observable.

```csharp
IO<decimal> request =
    FetchCurrentPriceIO(remotePriceApi, productId);
// This implementation has not sent the request.

decimal price = request.UnsafeRun();
// UnsafeRun invokes the stored delegate synchronously here.
```

Here, `Delay` means **defer evaluation**; it neither pauses a thread nor behaves like `Task.Delay`. The names follow precedents such as [Cats Effect's `IO.pure` and delayed effect construction](https://typelevel.org/cats-effect/docs/datatypes/io).

Passing an effectful call to `Pure` is already too late because C# evaluates method arguments before making the call:

```csharp
IO<decimal> notSuspended =
    IO.Pure(
        remotePriceApi.GetCurrentPrice(productId));
// GetCurrentPrice ran before Pure received the decimal.
```

`Pure` lifts an available value, while `Delay` introduces a suspended effect. `Map` and `Flatten` derive from `Pure` and `FlatMap`; `Delay` and `UnsafeRun` are specific to this effect type rather than operations every monad provides.

## A small `IO<T>`

The following is a complete synchronous implementation. `Unit` represents successful completion when an operation has no meaningful result. `Unit.Value` is the same value as `default(Unit)`; similar unit types appear in F#, `System.ValueTuple`, and Reactive Extensions.

```csharp
using System;

public readonly record struct Unit
{
    public static Unit Value { get; } = new();
}

// This is the Result type from Part 2, shortened to the operations
// that Attempt uses below.
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess value;
    private readonly TError error;
    private readonly bool isSuccess;

    private Result(
        TSuccess value,
        TError error,
        bool isSuccess)
    {
        this.value = value;
        this.error = error;
        this.isSuccess = isSuccess;
    }

    public static Result<TSuccess, TError> Ok(TSuccess value) =>
        new(value, default!, true);

    public static Result<TSuccess, TError> Fail(TError error) =>
        new(default!, error, false);

    public TResult Match<TResult>(
        Func<TSuccess, TResult> ok,
        Func<TError, TResult> fail)
    {
        ArgumentNullException.ThrowIfNull(ok);
        ArgumentNullException.ThrowIfNull(fail);

        return isSuccess ? ok(value) : fail(error);
    }
}

public sealed class IO<T>
{
    private readonly Func<T> operation;

    private IO(Func<T> operation)
    {
        this.operation = operation;
    }

    public static IO<T> Pure(T value) =>
        new(() => value);

    public static IO<T> Delay(Func<T> operation)
    {
        ArgumentNullException.ThrowIfNull(operation);
        return new IO<T>(operation);
    }

    public IO<TResult> Map<TResult>(
        Func<T, TResult> transform)
    {
        ArgumentNullException.ThrowIfNull(transform);

        return new IO<TResult>(
            () => transform(UnsafeRun()));
    }

    public IO<TResult> FlatMap<TResult>(
        Func<T, IO<TResult>> next)
    {
        ArgumentNullException.ThrowIfNull(next);

        return new IO<TResult>(() =>
        {
            T value = UnsafeRun();
            IO<TResult>? nextComputation = next(value);

            if (nextComputation is null)
            {
                throw new InvalidOperationException(
                    "FlatMap continuation returned null.");
            }

            return nextComputation.UnsafeRun();
        });
    }

    public IO<TResult> Select<TResult>(
        Func<T, TResult> selector) =>
        Map(selector);

    public IO<TResult> SelectMany<TNext, TResult>(
        Func<T, IO<TNext>> next,
        Func<T, TNext, TResult> project)
    {
        ArgumentNullException.ThrowIfNull(next);
        ArgumentNullException.ThrowIfNull(project);

        return FlatMap(value =>
        {
            IO<TNext>? nextComputation = next(value);

            if (nextComputation is null)
            {
                throw new InvalidOperationException(
                    "SelectMany selector returned null.");
            }

            return nextComputation.Map(
                nextValue => project(value, nextValue));
        });
    }

    public IO<TResult> Then<TResult>(
        IO<TResult> next)
    {
        ArgumentNullException.ThrowIfNull(next);
        return FlatMap(_ => next);
    }

    public IO<(T First, TNext Second)> Zip<TNext>(
        IO<TNext> other)
    {
        ArgumentNullException.ThrowIfNull(other);

        return FlatMap(first =>
            other.Map(second => (first, second)));
    }

    public IO<Result<T, TException>> Attempt<TException>()
        where TException : Exception
    {
        return IO.Delay(() =>
        {
            try
            {
                return Result<T, TException>.Ok(UnsafeRun());
            }
            catch (TException exception)
                when (exception is not OperationCanceledException)
            {
                return Result<T, TException>.Fail(exception);
            }
        });
    }

    public T UnsafeRun() =>
        operation();
}

// C# permits generic and non-generic types to share a name.
// This companion lets type inference remove IO<T>.Delay noise.
public static class IO
{
    public static IO<T> Pure<T>(T value) =>
        IO<T>.Pure(value);

    public static IO<T> Delay<T>(Func<T> operation) =>
        IO<T>.Delay(operation);

    public static IO<Unit> Delay(Action action)
    {
        ArgumentNullException.ThrowIfNull(action);

        return IO<Unit>.Delay(() =>
        {
            action();
            return Unit.Value;
        });
    }

    public static IO<T> Flatten<T>(IO<IO<T>> nested)
    {
        ArgumentNullException.ThrowIfNull(nested);
        return nested.FlatMap(inner => inner);
    }

    public static IO<TResult> Bracket<TResource, TResult>(
        IO<TResource> acquire,
        Func<TResource, IO<TResult>> use,
        Func<TResource, IO<Unit>> release)
    {
        ArgumentNullException.ThrowIfNull(acquire);
        ArgumentNullException.ThrowIfNull(use);
        ArgumentNullException.ThrowIfNull(release);

        return Delay(() =>
        {
            TResource resource = acquire.UnsafeRun();

            try
            {
                IO<TResult>? useComputation = use(resource);

                if (useComputation is null)
                {
                    throw new InvalidOperationException(
                        "Bracket use function returned null.");
                }

                return useComputation.UnsafeRun();
            }
            finally
            {
                IO<Unit>? releaseComputation = release(resource);

                if (releaseComputation is null)
                {
                    throw new InvalidOperationException(
                        "Bracket release function returned null.");
                }

                releaseComputation.UnsafeRun();
            }
        });
    }
}
```

`Map` and `FlatMap` call `UnsafeRun()` only inside the delegate stored by the returned `IO`, so invoking either combinator constructs another cold value. A `FlatMap` continuation is also deferred until execution.

The wrapper does not memoize: each `UnsafeRun()` invokes its stored delegate again, so its effects and result may differ between runs.

## The monad laws for effects

`Pure` and `FlatMap` form the monadic core:

```text
Left identity:   IO.Pure(a).FlatMap(f)              ≡ f(a)
Right identity:  m.FlatMap(IO.Pure)                 ≡ m
Associativity:   m.FlatMap(f).FlatMap(g)             ≡
                 m.FlatMap(x => f(x).FlatMap(g))

Coherence:       m.Map(f)                           ≡
                 m.FlatMap(x => IO.Pure(f(x)))
```

Here, `≡` cannot mean `Equals` or reference equality. The two sides wrap different closure objects. It means **observational equivalence under `UnsafeRun()`**: executing either side produces equal results and the same effects in the same order.

The laws hold when continuations purely construct non-null `IO` values and observation ignores allocation, identity, timing, and stack traces. Associativity then permits composition--including nested `from` clauses--to be regrouped without changing the effect sequence.

C# cannot enforce that purity. If `f` performs an effect while constructing its result, `IO.Pure(a).FlatMap(f)` defers the call while `f(a)` does not, making left identity observably false. Effectful transforms and nested forcing create similar escapes, so application code should keep callbacks pure and call `UnsafeRun()` only at the boundary. The laws also do not guarantee coldness, non-memoization, or stack behavior; those require separate contracts.

## Compose first, run later

Suppose `ParseOrder` returns an order with `ProductId`, `Quantity`, and `TaxRate`. We want to read the order, fetch its current price, calculate the total, render a report, and write it to disk:

```csharp
public static IO<string> ReadAllTextIO(string path)
{
    ArgumentNullException.ThrowIfNull(path);
    return IO.Delay(() => File.ReadAllText(path));
}

public static IO<Unit> WriteAllTextIO(
    string path,
    string contents)
{
    ArgumentNullException.ThrowIfNull(path);
    ArgumentNullException.ThrowIfNull(contents);

    return IO.Delay(
        () => File.WriteAllText(path, contents));
}
```

The `Action` overload of `IO.Delay` supplies `Unit.Value` for write-shaped operations. `Unit` is roughly `void` represented as a value, but `IO<T>` can return any result its caller needs.

The following query expression uses the `Select` and `SelectMany` methods already included in `IO<T>`:

```csharp
public static IO<Unit> LoadOrderAndWriteReport(
    IRemotePriceApi remotePriceApi,
    string orderPath,
    string reportPath)
{
    return
        from contents in ReadAllTextIO(orderPath)
        let order = ParseOrder(contents)
        from unitPrice in FetchCurrentPriceIO(
            remotePriceApi,
            order.ProductId)
        let total = CalculateLineTotal(
            order.Quantity,
            unitPrice,
            order.TaxRate)
        let report = RenderReport(
            order,
            unitPrice,
            total)
        from completion in WriteAllTextIO(
            reportPath,
            report)
        select completion;
}
```

Constructing the returned `IO<Unit>` does not invoke the delegates stored by the read, fetch, or write actions. During `UnsafeRun()`, the file is read before parsing, the price is fetched after the product ID is available, and the report is written last. The expressions in the `let` clauses are intended to be pure in this example; the compiler does not verify that convention.

The [C# specification](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/language-specification/expressions#12233-query-expression-translation) translates `from` to `SelectMany`, `let` to `Select`, and the final `select` into the last result selector. Query syntax requires no interface; its coldness and sequencing come entirely from the matching `IO<T>` methods.

## Expected failures and resource lifetime

Exceptions normally propagate from `UnsafeRun()`. `Attempt<TException>` turns one selected, expected exception type into the `Result` value from Part 2 while keeping execution deferred:

```csharp
IO<Result<string, IOException>> attemptedRead =
    ReadAllTextIO(path)
        .Attempt<IOException>();
```

Do not routinely use `Attempt<Exception>`. Programming errors, fatal failures, and cancellation should normally retain their semantics. Converting an exception into `Result` also does not make an operation transactional: an external operation may partially succeed before throwing.

Resources need an explicit lifetime that spans the deferred use. Returning an unscoped `IO<Stream>` can leave the caller with an open handle and no structured release. `Bracket` keeps acquire, use, and release in one larger computation:

```csharp
IO<string> firstLine =
    IO.Bracket(
        acquire: IO.Delay(
            () => File.OpenText(path)),
        use: reader => IO.Delay(
            () => reader.ReadLine() ?? string.Empty),
        release: reader => IO.Delay(
            reader.Dispose));
```

`release` runs if resource acquisition succeeded, even when `use` fails. This tiny `Bracket` has deliberately simple failure semantics: if both `use` and `release` fail, the release exception replaces the earlier exception. Production effect libraries preserve richer error information.

No generic `IO<T>` can roll back an arbitrary email, file write, or remote command. Rollback requires an operation-specific transaction or compensating action.

## Conclusion

Returning `IO<T>` changes a helper from "perform an effect and return `T`" to "construct a cold value whose stored delegate can later produce `T`." `Pure` and `FlatMap` supply the monadic structure, `Delay` introduces suspended work, derived combinators give policies names, and `UnsafeRun()` marks the synchronous execution boundary.

Keep pure transformations as ordinary functions, construct effects through `Delay`, compose without forcing them, and call `UnsafeRun()` at the application boundary. Calls inside `FlatMap` and `Bracket` implement that larger boundary rather than separate application-level escapes; async and batch policies require richer designs.
