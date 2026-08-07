---
title: "Monads in C# (Part 3): Composing Deferred Effects with a Tiny IO"
date: 2026-06-13
description: "A tiny synchronous IO<T> turns effectful work into a cold value. FlatMap composes those values, while UnsafeRun() marks the execution boundary."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/) and [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result/)

The first two parts introduced the same small pattern in different contexts:

| Context | Lift a value | Compose a dependent step | What the context decides |
|---|---|---|---|
| `List<T>` | a one-element list | `FlatMap` / `SelectMany` | how many values flow onward |
| `Maybe<T>` | `Some` | `FlatMap` / `Bind` | `None` skips the next function |
| `Result<TSuccess, TError>` | `Ok` | `FlatMap` / `Bind` | `Error` skips the next function |

**`IO` is one way to sequence effects in functional programming.**

An effect is an interaction with the world: reading or writing a file, asking for input, calling an API, drawing to the screen, or changing shared state. Programs need effects to be useful. The challenge is to control whether they happen, how often they happen, and in what order.

The reason why this is a challenge, is because, well, effects are awkward. So far, in the previous articles, we've dealt with pure functions, those that do not change the world. Pure functions have some nice properties, like being referentially transparent (substituting the value of an expression with its value with no change to program behavior), equational reasoning, etc. They behave very consistently: every input yields the same output.

Effectful functions cannot guarantee that. If I read a file at a certain file path, I am not guaranteed to get the same output each time, it depends on the file. Similarly, I cannot substitute the expression ReadFile(...) + ReadFile(...) with 2 * ReadFile(...) because the file's contents may have changed in between reads. Similarly, you may realize that the order of operations is important in effectful functions, especially since running them multiple times changes the output. If I call an HTTP API for example, it returns X, call it again it returns Y. It also depends on the world, that is, say if I call another HTTP API in the middle, then sure, maybe the result Y is different this time. But if I run a pure function 100 times, it doesn't matter, it will always return the same result (provided the input is the same.) The same cannot be said for effectful functions.

But, this doesn't really specify why effects are complicated, or special, why can't I just stick them in a function and run them? It has to do with how programs are sequenced in functional programming vs. procedural programming.

With procedural programming, statements are run one after the other, including effectful statements, even if you throw out the output. Sometimes there is no output (e.g., void methods) albeit it could throw exceptions. Programs dutifully run each line one by one and are sequenced by the semicolon.

With functional programming, we shift to a more equational reasoning approach, closer to algebra. This changes sequencing. We get a lot of niceties with this, referential transparency, etc. which, in some cases, can make it easier to reason about the programs because functions are pure by default unless you explicitly use IO.

There is a bit to unpack here: why are these "effects" special, and what does it mean to sequence them? Why do we need to sequence them?

In procedural C#, statement order provides an obvious sequence:

```csharp
File.WriteAllText(path, "first");
File.AppendAllText(path, "second");
```

The first statement runs before the second. Their return values are not the point--both methods return `void`--but executing them changes the file. Reversing, repeating, or skipping either statement changes the program's observable behavior. C# can express pure functions too; the distinction here is between pure calculations and side-effectful operations, not simply between programming languages. The semi colon sequences statements.

It's important that writing to the file occurs _before_ appending the text to the other file. Sequence is important. Since they run one after the other, the programmer is responsible for ordering statements (with semicolons) to sequence these effects so that the right output occurs.

Pure functional code has a different reasoning model. Consider these equations (recall the days from high school algebra):

```text
x = 5 + 1
y = 4 + 9 - 2
w = y + x
z = y + y + x
```

It does not matter whether `x` or `y` is evaluated first. I could say y = 4 + 9 - 2 and x = 5 + 1, it doesn't matter, the result of z when evaluted will be the same. Because `w` does not contribute to `z`, it need not be evaluated at all. Once we know that `y` is `11`, we may replace either occurrence of `y` with `11`, or rewrite `z` as `2y + x`, without changing the answer.

This property is called **referential transparency**, and it supports **equational reasoning**: replacing equals with equals preserves meaning. Evaluation order may affect cost, but it does not affect the result or change the world.

Now, this isn't always the case. What if the fact that we said x = 6 and y = 11, defining them in that order, would have a different result than defining y = 11 and x = 6 first? Would be weird, right? This would make algebra a lot more fragile, and you might not even be able to rely on simplifications, e.g., y + y is not equal to 2y because whenever you evaluate y, you might get a different result. I agree, yeah, that would be weird. But side effectful functions are just that.

Side effects break that model. Consider a stateful counter:

```csharp
private static int count = 0;

public static int Next()
{
    count++;
    return count;
}
```

Starting from zero, `Next() + Next()` evaluates to `1 + 2`, or `3`. The familiar algebraic rewrite `2 * Next()` invokes the counter once and produces `2`. Reordering, duplicating, or eliminating an effectful expression can change both its returned value and the world around it. Two calls to `ReadNumberFromFile(...)` have the same problem: the file may change between reads.

Lazy evaluation makes the mismatch especially visible. In a non-strict language such as Haskell, an expression is evaluated only when its value is needed:

```haskell
main = print result
  where
    a = 10
    unused = undefined
    b = 20
    result = a + b
```

Evaluating `undefined` would fail, but `unused` is never demanded, so this program prints `30`. Skipping an unused pure expression only avoids unnecessary work. Skipping an unused file write, however, means the file is never written. Effect execution therefore cannot safely depend on when an ordinary expression happens to be forced.

`IO<T>` addresses this by separating **describing** an operation from **performing** it. Instead of writing a file immediately, a function returns an `IO<Unit>` value that describes the write. `Unit` plays the role of `void`: there is no interesting result to carry forward, but the operation still matters. A file read that produces a useful value might return `IO<int>`.

Because these descriptions are values, they can be composed before anything happens:

```text
current : IO<A>
next    : A -> IO<B>

current.FlatMap(next) : IO<B>
```

`FlatMap` creates one larger `IO<B>` that describes a sequence: perform `current`, give its result to `next`, then perform the `IO<B>` returned by `next`. Constructing the larger value performs neither effect.

The final program is one composed `IO` value. In Haskell, that value is ultimately exposed as `main`, and the runtime performs the actions it describes. Simon Peyton Jones and Philip Wadler describe this design in [*Imperative functional programming*](https://www.microsoft.com/en-us/research/publication/imperative-functional-programming/). In this article's small C# model, the application passes the value to an explicit `UnsafeRun()` boundary.

C# already evaluates eagerly and specifies expression order, so this wrapper is not repairing C#'s evaluation semantics or enforcing purity. It makes effectful operations explicit, defers them, and preserves their order through composition. Despite its name, this tiny `IO<T>` can suspend any synchronous operation, including in-memory mutation; it does not statically distinguish I/O from other effects.

The central guarantee is conditional: **if the composed `IO` program is run, its effects are performed in the sequence encoded by `FlatMap`.**

That raises the practical question: why can the effectful code not remain an ordinary function? Why not call it inside `Map` or `Select`, just as we do with pure functions? C# accepts that code. `Enumerable.Select` makes clear what reasoning power is lost.

> **Scope:** This is a teaching model, not a recommendation to replace normal C# application structure or the Task-based Asynchronous Pattern (TAP). The examples target C# 10 and .NET 6 or later.

## Why not compose the function directly?

First consider a pure price calculation:

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
        CalculateLineTotal(
            quantity,
            unitPrice: 19.99m,
            taxRate: 0.13m));
```

`Select` controls when and how often it invokes the function. With this pure calculation, that changes when work occurs, but not what the work means. Each quantity still determines the same total, and enumeration does not change anything outside the calculation.

Now try the same shape with an effectful function. Part 1 used `Map` as pseudocode and did not define whether that operation was eager, so this example uses C#'s concrete `Enumerable.Select`:

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

If nobody enumerates the sequence, no request is sent. If code enumerates it twice, the calls happen twice. If the source itself is lazy or mutable, each enumeration may even see different inputs. `IEnumerable<T>` provides deferral, but it does so as part of a many-value traversal protocol. It does not mark one explicit effect boundary or promise exactly one result.

Both functions compose with `Select` in the mechanical sense. For the pure selector, enumeration policy affects when calculation happens. For the effectful selector, that policy becomes part of the program's meaning: enumeration decides whether the requests happen, when they happen, and how many times they happen. We have built a deferred sequence, but not a value whose explicit contract is "this is one effectful action."

A `foreach` loop makes the traversal policy visible:

```csharp
var pricesProcedural = new List<decimal>();

foreach (string productId in productIds)
{
    decimal price =
        remotePriceApi.GetCurrentPrice(productId);

    pricesProcedural.Add(price);

    // Delays, retries, or stop-on-error policy would live here.
}
```

The loop is not inherently non-composable; it can be packaged in a helper or strategy object. The useful change in this article is that the helper postpones the loop, returns the whole batch as a value, and gives its policy a reusable name.

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

This implementation sends no request while it constructs the returned value. The return type alone cannot guarantee that every method returning `IO<T>` is equally disciplined; C# still permits effects before `IO.Delay` is called.

The returned value is **cold**: constructing and composing it does not invoke the delegate stored by `IO<T>`. Calling `UnsafeRun()` invokes that delegate. The word "unsafe" marks the point where described work becomes observable.

```text
effectful function   IO.Delay       Map / FlatMap        UnsafeRun
   () -> T        ->   IO<T>     ->    IO<TResult>    ->  result + effects
                         construction      composition          execution
```

```csharp
IO<decimal> request =
    FetchCurrentPriceIO(remotePriceApi, productId);
// This implementation has not sent the request.

decimal price = request.UnsafeRun();
// UnsafeRun invokes the stored delegate synchronously here.
```

Here, `Delay` means **defer evaluation**. It neither pauses a thread nor behaves like `Task.Delay`. The names `Pure` and `Delay` follow precedents such as [Cats Effect's `IO.pure` and delayed effect construction](https://typelevel.org/cats-effect/docs/datatypes/io). F# readers should note that a [computation-expression builder's `Delay`](https://learn.microsoft.com/en-us/dotnet/fsharp/language-reference/computation-expressions) has a different shape: it commonly receives `unit -> M<'T>`, a delayed whole computation, rather than this article's `Func<T>` value producer.

Passing an effectful call to `Pure` is already too late because C# evaluates method arguments before making the call:

```csharp
IO<decimal> notSuspended =
    IO.Pure(
        remotePriceApi.GetCurrentPrice(productId));
// GetCurrentPrice ran before Pure received the decimal.
```

`Pure` lifts an already available value. `Delay` is the effect-introduction boundary:

| Role | Operation |
|---|---|
| Monadic core | `Pure`, `FlatMap` |
| Derived from the core | `Map`, `Flatten`, `Then`, `Zip` |
| Effect introduction, on the honor system | `Delay` |
| Effect execution | `UnsafeRun` |

In actual C# signatures, the central operations are:

```text
IO<T>.Pure(T)                                  -> IO<T>
IO<T>.Delay(Func<T>)                           -> IO<T>
io.Map(Func<T, TResult>)                       -> IO<TResult>
io.FlatMap(Func<T, IO<TResult>>)               -> IO<TResult>
io.UnsafeRun()                                 -> T
IO.Flatten(IO<IO<T>>)                          -> IO<T>
```

`Map` can be defined as `FlatMap` followed by `Pure`, and `Flatten` can be defined as `FlatMap` with the identity function. `Delay` and `UnsafeRun` are specific to this effect type; they are not operations every monad must provide.

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

The `new IO<TResult>(...)` call inside `IO<T>` is legal even though the constructor is private. Accessibility is determined by the generic type declaration, not by each closed construction; `IO<T>` and `IO<TResult>` are not different declaring types for private access.

Immediate argument validation treats a null delegate as API misuse at composition time. A `FlatMap` continuation cannot be checked until it is invoked, so returning null from it fails during `UnsafeRun()`. `Pure(null)` remains valid when the chosen `T` permits null.

The wrapper proves its central behavior with a call counter:

```csharp
int calls = 0;

IO<int> program =
    IO.Delay(() => ++calls)
        .Map(value => value * 10);

System.Diagnostics.Debug.Assert(calls == 0);

int first = program.UnsafeRun();
System.Diagnostics.Debug.Assert(first == 10 && calls == 1);

int second = program.UnsafeRun();
System.Diagnostics.Debug.Assert(second == 20 && calls == 2);
```

The wrapper does not memoize. Each `UnsafeRun()` invokes its stored delegate again, but that does not promise identical effects or results: the delegate may observe mutable state, perform its own memoization, or call code that behaves differently each time.

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

The laws hold for this model when continuations are pure constructors of non-null `IO` values, and when observation ignores allocation, object identity, precise timing, stack traces, and other implementation details. `FlatMap` then only nests delegates and invokes each step once in a fixed order. Associativity says that changing the grouping does not change that sequence.

C# cannot enforce the precondition. A continuation that performs an effect while constructing its returned `IO` makes left identity observably false:

```csharp
int constructions = 0;

IO<int> F(int value)
{
    constructions++;
    return IO.Pure(value);
}

IO<int> left = IO.Pure(1).FlatMap(F);
// F has not run because the continuation is suspended.

IO<int> right = F(1);
// constructions is already 1.
```

Likewise, nothing stops a transform passed to `Map` from performing an effect, or arbitrary code from calling `UnsafeRun()` inside `Delay`. That is this model's `unsafePerformIO`-style escape hatch. Library combinators such as `FlatMap`, `Bracket`, and traversal call `UnsafeRun()` internally to implement one larger boundary; application code should not use nested forcing as a substitute for structured composition.

The laws do not specify every useful runtime property. A memoized implementation could still satisfy the monad laws while no longer repeating its stored operation on each run. Coldness, non-memoization, and stack behavior therefore need their own documented contracts.

The laws also explain why LINQ syntax is more than mechanical sugar. Associativity permits nested `from` clauses to be regrouped without changing the sequence, while `Select`/`SelectMany` coherence keeps `let` steps consistent with `Map` and `FlatMap`.

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

Binding `completion` only to return it is ceremony. Haskell would commonly use its sequence-and-discard operator, `>>`. The `Then` method above provides that operation when the second computation does not depend on the first result, but C# query syntax still requires a final `select` or `group`.

### What the query becomes

The [C# specification](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/language-specification/expressions#12233-query-expression-translation) defines query translation as a syntactic rewrite performed before method binding. It requires no interface, `IEnumerable<T>`, or attribute; matching instance or extension methods are enough.

Ignoring compiler-generated names, the query above lowers to this shape:

```csharp
ReadAllTextIO(orderPath)
    .Select(contents =>
        new { contents, order = ParseOrder(contents) })
    .SelectMany(
        first => FetchCurrentPriceIO(
            remotePriceApi,
            first.order.ProductId),
        (first, unitPrice) =>
            new { first, unitPrice })
    .Select(second =>
        new
        {
            second,
            total = CalculateLineTotal(
                second.first.order.Quantity,
                second.unitPrice,
                second.first.order.TaxRate)
        })
    .Select(third =>
        new
        {
            third,
            report = RenderReport(
                third.second.first.order,
                third.second.unitPrice,
                third.total)
        })
    .SelectMany(
        fourth => WriteAllTextIO(
            reportPath,
            fourth.report),
        (fourth, completion) => completion);
```

The final `select completion` folds into the last `SelectMany` result selector; it does not add another `Select`. The three `let` clauses do require three `Select` calls. A complete execution creates seven query-generated wrapper objects: three `Map` wrappers from `Select`, two `FlatMap` wrappers from `SelectMany`, and two inner `Map` wrappers created by those `SelectMany` calls. The inner wrappers and their selected actions are built during execution, so not all seven exist when the outer program is constructed.

Query syntax is cold here only because these particular methods return delayed wrappers. The syntax itself does not imply laziness.

This `IO<T>` supports the query clauses that lower to its small algebra: `from`, `let`, and `select`. There is no natural `Where` for an exactly-one-result type because a false predicate needs a no-value or error case. `Maybe` and `Result` have such cases; this `IO<T>` does not. `join`, grouping, and ordering would likewise require additional methods and semantics. Which clauses a type supports is determined by its algebra, not by query syntax alone.

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

## Traversal makes the batch policy explicit

`FlatMap` sequences one dependent effect after another. Applying an effectful action to many inputs requires a separate batch policy.

This traversal snapshots the inputs during construction, then defers action creation and execution:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;

public static class IOTraversalExtensions
{
    public static IO<IReadOnlyList<TResult>>
        TraverseSequential<TSource, TResult>(
            this IEnumerable<TSource> source,
            Func<TSource, IO<TResult>> action)
    {
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(action);

        List<TSource> items = source.ToList();

        return IO.Delay<IReadOnlyList<TResult>>(() =>
        {
            var results =
                new List<TResult>(items.Count);

            foreach (TSource item in items)
            {
                IO<TResult>? computation = action(item);

                if (computation is null)
                {
                    throw new InvalidOperationException(
                        "Traversal action returned null.");
                }

                results.Add(computation.UnsafeRun());
            }

            return results;
        });
    }

    public static IO<IReadOnlyList<T>>
        SequenceSequential<T>(
            this IEnumerable<IO<T>> source)
    {
        return source.TraverseSequential(
            computation => computation);
    }
}
```

`TraverseSequential` and `SequenceSequential` are the conventional `Traverse` and `Sequence` operations with the execution policy made explicit in their names.

The expression producing `source` is evaluated before the extension method is called, and `ToList()` enumerates it immediately. That policy has a useful split:

* Input enumeration and any enumeration failure happen during construction.
* The input set and order are fixed by one snapshot.
* `action` is invoked only during the outer `UnsafeRun()`.
* Items run one at a time in snapshot order, and results preserve that order.
* If an action throws, later actions do not run and completed effects are not undone.
* Each outer `UnsafeRun()` invokes every action again against the same input snapshot.

For `SequenceSequential`, a lazy source of `IO` values is also materialized during construction. The wrappers may have been built earlier or produced by that enumeration, but the resulting set is fixed before execution.

```csharp
IO<IReadOnlyList<decimal>> batch =
    productIds.TraverseSequential(productId =>
        FetchCurrentPriceIO(
            remotePriceApi,
            productId));
// productIds has been snapshotted; no price action was created or run.

IReadOnlyList<decimal> prices =
    batch.UnsafeRun();
```

The imperative loop inside the combinator is intentional. Building the traversal as an `n`-element `FlatMap` fold would add `O(n)` synchronous call depth. The loop gives the policy a reusable value without adding one stack frame per item.

A different combinator could add pacing, selective retry, failure collection, or concurrency. With this synchronous type, bounded concurrency would occupy threads through an external scheduler; it is not the same as native asynchronous I/O. Retrying a read may be acceptable, while retrying a non-idempotent command may duplicate it.

## `IO<T>` compared with other deferred types

Coldness is only one axis. Memoization and result arity often matter more:

| Type | Work starts | Memoized by the wrapper? | Result arity |
|---|---|---:|---|
| `Func<T>` / this `IO<T>` | each invocation / `UnsafeRun()` | no | one per call |
| `Lazy<T>` | first `.Value` | yes | one for that instance |
| `Task<T>` returned by a TAP method | active when returned | yes | one completion per task |
| `Func<Task<T>>` | each function invocation | not across invocations | one task result per invocation |
| cold `IEnumerable<T>` / `IObservable<T>` | each enumeration / subscription | no | many |

Awaiting the same `Task<T>` twice observes the same task completion; it does not call the producer twice. That is why a task instance cannot directly express "run this operation again." An async analogue of this article's cold factory starts closer to `Func<CancellationToken, Task<T>>`, although a real async effect type also needs cancellation, scheduling, and resource semantics.

The TAP qualifier matters. [.NET's TAP guidance](https://learn.microsoft.com/en-us/dotnet/standard/asynchronous-programming-patterns/task-based-asynchronous-pattern-tap) says tasks returned by TAP methods are active, while a `Task` created with its public constructor can begin cold in `TaskStatus.Created`. Active also does not mean "running on another thread": an `async` method executes synchronously until its first incomplete `await`.

An arbitrary `ValueTask<T>` has different consumption rules. [.NET analyzer rule CA2012](https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/quality-rules/ca2012) says callers generally must assume a `ValueTask` returned by a member can be consumed only once.

`IO<Task<T>>` is not a complete async design. `IO.Pure(FetchAsync())` calls `FetchAsync` before `Pure`, and even `IO.Delay(() => FetchAsync())` only defers creation of a task. This `Map` and `FlatMap` do not await it. Blocking with `.Result` or `.GetAwaiter().GetResult()` is not a substitute for asynchronous composition.

Finally, `UnsafeRun()` is the opposite of `Task.Run`: `Task.Run` schedules work and returns a task, while `UnsafeRun()` directly invokes a delegate and returns its result. This `IO<T>` performs no scheduling.

## Runtime semantics and limitations

### What this model defines

* `UnsafeRun()` invokes the stored delegate synchronously on the caller's thread.
* The wrapper performs no scheduling and does not memoize the delegate's result.
* `Map` and `FlatMap` preserve suspension when their callbacks construct values without performing effects.
* `FlatMap`, `Then`, `Zip`, `Bracket`, and traversal define left-to-right sequencing.
* Exceptions propagate unless a combinator such as a selective `Attempt` converts them.
* Captured mutable state is read when the delegate runs, not necessarily when the `IO<T>` is constructed.

### What this model does not guarantee

* **Purity or honesty.** C# permits effects during argument evaluation, factory methods, `Map` transforms, and `FlatMap` continuations.
* **Introspection.** The stored `Func<T>` is opaque. The value gives positional control over when, whether, and how often work runs, but it cannot be inspected, logged as instructions, optimized, or interpreted against a test runtime.
* **Stack safety.** Composition recursively calls `UnsafeRun()` through closure layers. A sufficiently deep chain can cause a [`StackOverflowException` that application code cannot catch](https://learn.microsoft.com/en-us/dotnet/api/system.stackoverflowexception?view=net-10.0), terminating the process by default. A stack-safe design reifies `Pure`, `Delay`, and `FlatMap` as instruction data and interprets it with an explicit stack or trampoline. That instruction-ADT, free-monad-style design would also make programs inspectable.
* **Async execution, cancellation, backpressure, or native concurrency.** These require a different runtime and API.
* **Thread safety.** The wrapper is immutable, but its delegate and captured state may not be. Concurrent `UnsafeRun()` calls can race and duplicate effects.
* **Automatic resource safety, retry, transactions, or rollback.** Those require explicit combinators and operation-specific semantics.
* **Cheap allocation.** Every combinator allocates an `IO` object and usually a closure. A suspended value also keeps captured services, APIs, and buffers alive until the value becomes unreachable.
* **Variance.** `IO<T>` is a sealed class and remains invariant in `T`, even though its stored `Func<T>` has a covariant result type.

Opacity also limits the testing benefit. You still need an `IRemotePriceApi` fake to verify returned prices, failures, and request order. The narrower improvement is testable: a fake with a call counter can prove that constructing and composing the program did not invoke the stored request, and that each `UnsafeRun()` invokes it again.

## Conclusion

Returning `IO<T>` changes a helper from "perform an effect and return `T`" to "construct a cold value whose stored delegate can later produce `T`." `Pure` and `FlatMap` supply the monadic structure, `Delay` introduces suspended work, derived combinators give policies names, and `UnsafeRun()` marks the synchronous execution boundary.

Keep pure transformations as ordinary functions, construct effects through `Delay`, compose without forcing them, and call `UnsafeRun()` at the application boundary. Calls inside `FlatMap`, `Bracket`, and traversal are the implementation of one larger boundary, not separate application-level escapes.

A next step could replace `Func<T>` with an instruction data type and iterative interpreter for inspection and stack safety, or design an async effect around task factories, cancellation tokens, and structured resource handling. Production ecosystems explore those tradeoffs in libraries such as [LanguageExt](https://github.com/louthy/language-ext) for .NET, [Cats Effect](https://typelevel.org/cats-effect/) for Scala, and [ZIO](https://zio.dev/) for Scala.
