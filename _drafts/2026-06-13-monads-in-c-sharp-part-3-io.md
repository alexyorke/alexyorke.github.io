---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO turns interactions with the world into values that can be composed and sequenced before execution."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

In the previous articles, calls to `Map` and `FlatMap` looked almost procedural. One transformation appeared to happen, then the next:

```csharp
Result<int, ConfigError> totalRetries =
    configResult.Map(GetTotalRetries);
```

The code reads from top to bottom, but `GetTotalRetries` is not called directly. It is passed to `Result.Map`, and `Result` decides whether to call it. A successful result applies the function; an error skips it.

That distinction did not seem especially dramatic in the earlier examples because the functions were ordinary calculations and the implementations were eager. The same style of composition becomes more significant when a function reads a file, queries a service, writes data, or describes work that will happen later.

This article develops that problem toward `IO<T>`. The examples use C#-style code to keep the discussion concrete. They are teaching examples, not an argument that C# applications should adopt an IO monad.

## Pure functions and effects

Assume `Config` is an immutable value: once a `Config` has been created, its retry counts do not change.

```csharp
public static int GetTotalRetries(
    Config config)
{
    return config.BaseRetries
        + config.ExtraRetries;
}
```

`GetTotalRetries` is pure. Its output is determined by its input, and calling it does nothing else that the rest of the program can observe.

Conceptually, a pure function behaves like a lookup table. The same immutable input selects the same output every time. Looking up the answer twice does not write anything, consume anything, advance a cursor, or change what a later lookup means.

Now consider a file-reading function:

```csharp
public Config LoadConfig(
    string path)
{
    var json =
        File.ReadAllText(path);

    return Config.Parse(json);
}
```

Even when `path` is the same constant string, two calls can produce different results:

```csharp
var first =
    LoadConfig("pricing.json");

var second =
    LoadConfig("pricing.json");
```

The file may have changed or disappeared between the calls. The function depends on more than its visible argument.

For this article, an **effect** is an observable interaction with state that is not fixed by immutable input values. Reading a file, querying a database, observing the current time, calling a remote service, writing a log entry, and changing shared state are effects in this sense.

One way to expose the missing input is to imagine an extra `World` parameter:

```csharp
public Config LoadConfig(
    string path
    /*, World world */)
{
    var json =
        File.ReadAllText(path);

    // Conceptually:
    // var json = world.ReadAllText(path);

    return Config.Parse(json);
}
```

`World` is not a proposed C# class. It is a model for the file system, databases, clocks, services, mutable objects, and other state available when the operation runs. The real shape is closer to:

```text
(Path, World)
    -> (Config or failure, World')
```

`World'` represents the world after the interaction. A read may advance a stream, populate a cache, consume quota, or simply occur after more time has passed.

If the complete world were available as an immutable input and the transition were deterministic, both the result and the next world could in principle be predicted. Ordinary code does not receive that complete value. Calling the operation establishes a particular observation of the world at that point in the program.

## Passing a function transfers invocation

In procedural code, the sequence of direct calls is explicit:

```csharp
var config =
    LoadConfig(path);

var totalRetries =
    GetTotalRetries(config);

SaveRetrySummary(totalRetries);
```

The configuration is loaded, the total is calculated, and the summary is saved in that order.

With `Map`, the caller passes a function rather than invoking it:

```csharp
Result<int, ConfigError> totalRetries =
    configResult.Map(
        GetTotalRetries);
```

`Result.Map` calls `GetTotalRetries` only when `configResult` contains a successful `Config`. This is not temporal deferral: `Result` is choosing a branch. The function may run immediately, or it may not run at all.

`List.Map` has another rule:

```csharp
List<int> totals =
    configs.Map(
        GetTotalRetries);
```

The `List` implementation applies the function to each represented `Config`.

The earlier examples still looked sequential because their implementations performed the required work eagerly. Even so, control had already moved. The receiving operation decided whether and how to invoke the function supplied by the caller.

That transfer is easy to tolerate for `GetTotalRetries`. Skipping or repeating a pure calculation creates no additional event in the world. Once the supplied function performs an effect, its invocation policy becomes observable.

## Sorting makes the transfer obvious

Sorting is not a monad, but it is a clear example of the same higher-order relationship.

```csharp
static int CompareByPriority(
    Customer left,
    Customer right)
{
    return left.Priority.CompareTo(
        right.Priority);
}

customers.Sort(
    CompareByPriority);
```

The caller provides a comparison function. The sorting function decides which pairs to compare, in what order, and how often. That transfer of control is what makes `Sort` reusable: the caller does not implement the sorting algorithm.

Now make the comparison depend on a service:

```csharp
int CompareByCurrentRisk(
    Customer left,
    Customer right)
{
    var leftScore =
        riskService.GetCurrentScore(
            left.Id);

    var rightScore =
        riskService.GetCurrentScore(
            right.Id);

    return leftScore.CompareTo(
        rightScore);
}

customers.Sort(
    CompareByCurrentRisk);
```

The sorting algorithm now controls the service calls. It may score the same customer repeatedly, and it may request scores in an order the caller cannot predict. If scores change during the sort, repeated comparisons may no longer describe a stable ordering.

A write inside the comparer would have the same problem. The sorting algorithm would determine how many writes occur and in what order.

Writing a custom sorting algorithm could restore control over every call, but it would discard the reusable abstraction. A cleaner design performs the effects in a separate phase:

```csharp
var scoredCustomers =
    new List<ScoredCustomer>();

foreach (var customer in customers)
{
    var score =
        riskService.GetCurrentScore(
            customer.Id);

    scoredCustomers.Add(
        new ScoredCustomer(
            customer,
            score));
}

scoredCustomers.Sort(
    (left, right) =>
        left.Score.CompareTo(
            right.Score));
```

The program has chosen one observation per customer before sorting. Retry, throttling, caching, and validation can be placed around that phase. Sorting then operates on stable values.

The service can still change while the scores are collected. The program controls the placement and number of its own observations; it does not control the entire external world.

## Deferred execution makes timing visible

C#'s `IEnumerable<T>.Select` makes the timing issue concrete:

```csharp
IEnumerable<Config> configs =
    paths.Select(
        path => LoadConfig(path));

PublishConfigsLoadedEvent();
```

The returned sequence behaves like an iterator. It remembers how to produce values, but the selector runs only when the sequence is enumerated:

```csharp
foreach (var config in configs)
{
    Use(config);
}
```

Enumerating it again can read the files again.

Materializing the sequence chooses an observation boundary:

```csharp
List<Config> configs =
    paths.Select(
        path => LoadConfig(path))
    .ToList();

PublishConfigsLoadedEvent();
```

`ToList` performs the reads at that point and stores the resulting values.

Choosing that point does not prove that the external world is in one objectively correct state. It says that these are the observations this operation will use. The application may still need to validate versions, freshness, or consistency with other data.

An IO-based version makes another distinction:

```csharp
List<IO<Config>> reads =
    paths.Select(
        path => LoadConfigIO(path))
    .ToList();
```

This materializes a list of computations. It does not itself read the files.

## `IO<T>` stores a computation

An immediate file-reading function returns a `Config` after performing the read:

```text
string -> Config
```

An IO-producing function returns a value representing the read:

```text
string -> IO<Config>
```

Here is a small synchronous implementation:

```csharp
public sealed class IO<T>
{
    private readonly Func<T> operation;

    public IO(Func<T> operation)
    {
        this.operation = operation;
    }

    public T Run()
    {
        return operation();
    }

    public static IO<T> Pure(T value)
    {
        return new IO<T>(() =>
        {
            return value;
        });
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
            IO<TResult> nextOperation =
                next(value);

            return nextOperation.Run();
        });
    }
}
```

This is teaching code, not a production effect library. `Pure` and `FlatMap` are common monadic names; `Pure` is also called `Return`, and `FlatMap` is also called `Bind`.

A file read can now be stored without being performed:

```csharp
public IO<Config> LoadConfigIO(
    string path)
{
    return new IO<Config>(() =>
    {
        return LoadConfig(path);
    });
}
```

Calling `LoadConfigIO` captures the path and returns an `IO<Config>`. The file is read when `Run` invokes the stored function.

`Pure` is for a value that is already available:

```csharp
IO<int> answer =
    IO<int>.Pure(42);
```

It does not defer evaluation of its argument. This still reads the file before `Pure` is called:

```csharp
IO<Config> config =
    IO<Config>.Pure(
        LoadConfig(path));
```

Storing the computation requires the lambda used by the constructor.

## Composing the sequence

`Map` applies a pure calculation to the value an effect will eventually produce:

```csharp
IO<int> totalRetries =
    LoadConfigIO("pricing.json")
        .Map(GetTotalRetries);
```

No file has been read yet.

`FlatMap` handles a following operation that also interacts with the world:

```csharp
public IO<string> ReadTemplateIO(
    string path)
{
    return new IO<string>(() =>
    {
        return File.ReadAllText(path);
    });
}

IO<string> page =
    LoadConfigIO("pricing.json")
        .FlatMap(config =>
            ReadTemplateIO(
                config.TemplatePath)
            .Map(template =>
                RenderPage(
                    config,
                    template)));
```

When `page` runs, it loads the configuration, uses that result to choose a template, reads the template, and renders the page.

Conceptually, `FlatMap` threads the world through the sequence:

```text
World0
    -> load configuration
    -> World1
    -> read template
    -> World2
```

`FlatMap` still owns a callback. Its rule is now explicit: run the first computation, pass its value to the callback, and run the computation returned by that callback.

The external world may change between the reads. IO composition guarantees their relative order and data dependency, not an atomic snapshot. Transactions, version checks, validation, and immutable resource identifiers provide stronger consistency when required.

`Result` remains useful here. The two types describe different concerns: `IO` describes when an interaction occurs, while `Result` can describe an expected success or failure. A realistic signature might therefore be:

```csharp
IO<Result<Config, ConfigError>>
```

Running the same `IO<T>` twice performs the interaction twice:

```csharp
IO<Config> operation =
    LoadConfigIO("pricing.json");

Config first =
    operation.Run();

Config second =
    operation.Run();
```

Each execution may observe a different world. Assignment does not imply caching, memoization, or one-time execution.

## How this differs from `Task<T>`

A .NET `Task<T>` can look similar because it represents work that produces a value. The comparison is limited.

A task created with a public constructor has not yet been scheduled:

```csharp
var task =
    new Task<Config>(() =>
    {
        return LoadConfig(path);
    });

task.Start();

Config config =
    await task;
```

Creation and execution are separated here, but a `Task` is scheduled through a task scheduler and can be started only once.

More commonly, `Task.Run` queues the work immediately:

```csharp
Task<Config> task =
    Task.Run(() =>
    {
        return LoadConfig(path);
    });
```

`Task.Factory.StartNew` also creates and starts a task. These operations are only loosely analogous to `IO.Run`: they initiate scheduled work and return a `Task`, while the toy `Run` method executes the stored computation synchronously and can be called again.

`Task<T>` represents one asynchronous operation and its eventual state. The toy `IO<T>` represents a computation that can be interpreted each time `Run` is called. Production effect libraries usually provide their own asynchronous and cancellation models rather than treating `Task<T>` as identical to `IO<T>`.

## Running at the boundary

A larger program can remain stored until a boundary chooses to run it:

```csharp
IO<string> program =
    BuildConfigPageProgram(
        "pricing.json");

string page =
    program.Run();
```

Before `Run`, surrounding code can still decide whether the program should execute and which retry, validation, logging, or caching policy should surround it.

Calling `Run` inside a helper gives that decision to the helper. Returning `IO<T>` leaves it with the caller.

The toy type does not automatically provide asynchronous execution, typed errors, retry, transactions, cancellation, resource safety, or dependency replacement. C# also cannot enforce that callbacks passed to `Map` are pure or that a function returning `IO<T>` performs no immediate effect while constructing it. The type supplies a boundary and a composition rule; the code must follow the intended discipline.

## Putting it together

The earlier `List` and `Result` examples looked like ordinary sequential code, but they had already transferred invocation to `Map` and `FlatMap`. `Result` could skip a supplied function on error. `List` could apply it to several values.

Pure calculations tolerate that transfer because their immutable inputs determine their outputs, and evaluating them creates no additional event in the world.

Functions that read or change the world have a larger contract:

```text
(Input, World)
    -> (Output or failure, World')
```

Their output can depend on when they run. Repeating them can produce another observation or another change. Skipping or reordering them can alter everything that follows.

Sorting exposes the danger when an algorithm controls an effectful callback. Deferred `Select` shows how an apparently simple assignment can postpone an observation until enumeration. Materializing with `ToList` chooses when the observations occur, while validation and consistency mechanisms determine whether those observations are useful.

`IO<T>` represents the interaction as a value before it happens. `FlatMap` composes those values under a clear rule: perform the first interaction, use its result to construct the next, and perform the next afterward.

That makes one distinction visible:

```text
a value of type T
```

is different from:

```text
a computation that may later produce T
by interacting with the world
```

Keeping them separate lets the part of the program that owns execution decide when and under what policy those interactions should occur.
