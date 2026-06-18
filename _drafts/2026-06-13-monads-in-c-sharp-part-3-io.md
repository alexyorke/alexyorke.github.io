---
title: "Monads in C# (Part 3): IO"
date: 2026-06-13
description: "IO lets code describe an effect before deciding where and how to run it."
permalink: 2026/06/13/monads-in-c-sharp-part-3-io/
---

**Previously in the series**: *List is a monad (Part 1)* and *Monads in C# (Part 2): Result*

This article is not an argument that C# programs should adopt an IO monad. I am using C#-style code as a familiar procedural setting. The focus is the part I find most useful in code review: who owns the decision to call an effectful operation, and under what policy.

In the previous parts, we looked at `List<T>`, `Maybe<T>`, and `Result<TSuccess, TError>`. Through `Map`, `Bind`, and `SelectMany`, these types take a function from us and decide how to apply it: once per list item, maybe not at all, or only after success.

This raises a question:

> What kind of function can I safely hand over?

The answer changes when the function is **effectful**. In this article, an effectful function is one that observes or changes something outside its explicit arguments and return value. Reading a file, querying a database, calling an HTTP service, observing the current time, writing a log entry, and mutating shared state are all effects in this sense.

Effects are ordinary parts of useful programs. The question is how much control we keep when an effectful operation is passed into another abstraction. `IO` is one way to keep the operation composable until the part of the program that owns the calling strategy is ready to run it.

## Direct calls and handed-over calls

In ordinary direct-style code, the programmer usually owns the calling strategy.

```csharp
var config = LoadConfig(path);
var summary = RenderConfigSummary(config);

File.WriteAllText(summaryPath, summary);
```

Assume `LoadConfig` reads and parses a configuration file, and `RenderConfigSummary` formats an already-loaded `Config`. The order is visible: read, render, write. If the read or write needs special handling, the caller can place that policy around the exact step.

A callback changes that relationship. Instead of invoking the function directly, we give it to something else, and that other code decides when to call it.

Consider a `foreach` loop over an in-memory collection:

```csharp
var configs = new List<Config>();

foreach (var path in configPaths)
{
    configs.Add(LoadConfig(path));
}

PublishConfigsLoadedEvent();
```

The call to `LoadConfig` appears exactly where it runs. Assuming the loop completes, all config files have been read before the event is published.

Now compare that with `Select`:

```csharp
var configs = configPaths.Select(path =>
    LoadConfig(path));

PublishConfigsLoadedEvent();
```

`Enumerable.Select` uses deferred execution. The assignment creates an enumerable that remembers the source and selector; it does not cache the loaded configs, and the selector does not run until the result is enumerated. Enumerating the result again may call the selector again.

At the point where the event is published, no config files may have been read.

We can force evaluation:

```csharp
var configs = configPaths
    .Select(path => LoadConfig(path))
    .ToList();

PublishConfigsLoadedEvent();
```

The distinction is control. In the loop, we invoked the function directly. With `Select`, we described a transformation and handed invocation to another abstraction. That transfer is useful, but it makes the function's contract matter.

## Sorting makes the handoff obvious

Sorting is an even clearer example because the algorithm, not the programmer, decides which calls to make.

```csharp
static int CompareByPriority(
    Customer left,
    Customer right)
{
    if (left.Priority == right.Priority)
    {
        return 0;
    }

    if (left.Priority < right.Priority)
    {
        return -1;
    }

    return 1;
}

customers.Sort(CompareByPriority);
```

`Sort` is a higher-order function in a concrete sense: the programmer supplies a comparison function, and the sorting algorithm owns the call schedule. The comparer contract has to tolerate that freedom. Depending on the values and implementation, the algorithm may skip pairs, compare the same values more than once, or use a different abstraction that caches keys or comparison results. The caller has handed over invocation.

That fits the usual comparer contract when the function answers a value question:

```text
Does left come before, after, or at the same position as right?
```

Now consider an effectful comparer:

```csharp
int CompareByRiskScore(
    Customer left,
    Customer right)
{
    _audit.Record($"Compared {left.Id} and {right.Id}");

    var leftScore = _riskService.GetScore(left.Id);
    var rightScore = _riskService.GetScore(right.Id);

    return leftScore.CompareTo(rightScore);
}

customers.Sort(CompareByRiskScore);
```

This compiles, and it may even appear to work. The awkward part is that the sorting algorithm now controls more than ordering. It also controls how many audit records are written, which pairs are audited, how many service calls are made, and whether the same customer is scored repeatedly. Those concerns belong to the calling strategy around the service and audit operations.

You could take back control by writing a custom sorting routine that performs scoring exactly where you want it. That makes call order explicit, but gives up the reusable abstraction that made `Sort` useful. The higher-order function is valuable because sorting logic is shared; the price is that the function you hand over must tolerate the sorting implementation's call schedule.

The usual repair is to obtain the scores under an explicit calling strategy before sorting:

```csharp
var customersWithRiskScores = new List<CustomerWithRiskScore>();

foreach (var customer in customers)
{
    var score = RetryThrottled(() =>
        _riskService.GetScore(customer.Id));

    customersWithRiskScores.Add(
        new CustomerWithRiskScore(customer, score));
}
```

The sort can then compare ordinary values:

```csharp
static int CompareByScore(
    CustomerWithRiskScore left,
    CustomerWithRiskScore right)
{
    return left.Score.CompareTo(right.Score);
}

customersWithRiskScores.Sort(CompareByScore);
```

The service calls can now be cached, throttled, logged, or otherwise handled in a visible phase. Sorting is just an easy place to see the handoff: whenever another API calls our function, that API owns some part of when and how the function runs.

## The hidden input

Effectful callbacks care about calling strategy because the call itself may observe or change something outside the argument list.

A pure function can be understood as a mapping from explicit inputs to an output:

```text
Input -> Output
```

For this article, a function is pure enough when replacing a call with its result would not change the program's observable behavior.

```csharp
public static int Add(int left, int right) =>
    left + right;
```

The calculation receives everything it needs as values. `Add(1, 1)` produces `2` each time, because the result depends only on the two explicit inputs.

An effectful function has a larger real input:

```csharp
public Config LoadConfig(string path)
{
    var json = File.ReadAllText(path);

    return Config.Parse(json);
}
```

The signature suggests:

```text
string -> Config
```

The behavior is closer to:

```text
Path + World -> Config or failure + World'
```

`World` is a semantic model for hidden inputs and sequencing. In Haskell it belongs to explanation rather than the public `IO` API; in C#, it is only a way to make missing context visible. It stands for whatever surrounding state the function may observe: files, clocks, caches, databases, network state, configuration, or shared mutable state.

`World'` represents the world after the call. The operation may have consumed quota, written telemetry, populated a cache, changed a database, or affected an external system.

If we made that model explicit, a file read could look like this:

```csharp
public static (Config Config, World World) LoadConfig(
    string path,
    World world)
{
    var file = world.Files[path];
    var nextWorld = world.RecordRead(path);

    return (Config.Parse(file.Text), nextWorld);
}
```

The point is that the explicit argument list describes only part of the operation.

Two calls can therefore have the same visible input but different real inputs:

```csharp
var first =
    LoadConfig("pricing.json");

var second =
    LoadConfig("pricing.json");
```

Conceptually:

```text
Path + World0
    -> Config + World1

Path + World1
    -> FileNotFound + World2
```

Both calls use the same path, but the surrounding state can differ. The file may have changed, or it may no longer exist.

Once an effect appears inside a larger operation, the larger operation inherits it. A pure step cannot erase a file read, a clock read, or a write to shared state introduced elsewhere in the composition. With a file read, the caller may care whether the file is read now or later, whether it is read once or many times, whether the result is cached, and whether tests can replace the file system with a fixed value.

A generic function type rarely contains that information:

```csharp
Func<string, Config>
```

The type says that a string produces a `Config`. It does not say whether the function reads the file system every time, caches a previous read, logs the access, or can be replaced by a test version before the file is touched.

A generic function type can still be called just fine. It simply describes less than the real operational contract.

## Why immediate effects are awkward to compose

Consider the ordinary effectful helper from earlier:

```csharp
public Config LoadConfig(string path)
{
    var json = File.ReadAllText(path);

    return Config.Parse(json);
}
```

The effect happens as soon as `LoadConfig` is invoked.

If another function calls it internally:

```csharp
public static string RenderConfigSummary(Config config) =>
    $"Retries: {Add(config.BaseRetries, config.ExtraRetries)}";

public string BuildConfigSummary(string path)
{
    var config = LoadConfig(path);

    return RenderConfigSummary(config);
}
```

then `BuildConfigSummary` is also effectful. More importantly, the file has already been read before the caller gets the summary back.

The caller can still decide when to call `BuildConfigSummary`:

```csharp
var summary =
    BuildConfigSummary("pricing.json");
```

That may be fine for simple code. The limitation is that the caller receives the result after the file read. It cannot compose with the `Config` before the read happens, and it cannot replace just the file-reading step without changing the helper or wrapping the whole operation.

## `IO` as a deferred effect

An `IO<T>` type changes that contract.

A function can return a description of work that may later produce `T`. You can think of that value as a blueprint, a recipe, or a deferred computation. The point here is deferral rather than background work or concurrency: the call stores the effectful operation as a value, while the actual interaction with the world waits until some boundary explicitly says to run it.

To keep the shape visible, here is a toy synchronous implementation. This is teaching code, not a production library.

```csharp
public sealed class IO<T>
{
    private readonly Func<T> _run;

    public IO(Func<T> run) =>
        _run = run;

    public T Run() =>
        _run();

    public static IO<T> Pure(T value) =>
        new IO<T>(() => value);

    public IO<TResult> Map<TResult>(
        Func<T, TResult> map) =>
        new IO<TResult>(() =>
            map(Run()));

    public IO<TResult> Bind<TResult>(
        Func<T, IO<TResult>> bind) =>
        new IO<TResult>(() =>
            bind(Run()).Run());
}
```

That is the basic mechanism. The constructor stores a function. `Run` invokes it. `Pure` builds an `IO<T>` that yields an already-available value when run and performs no new effect. `Map` and `Bind` build a new stored function around the old one.

Conceptually:

```csharp
public IO<Config> LoadConfigIO(string path)
{
    return new IO<Config>(() =>
        LoadConfig(path));
}
```

The exact API depends on the library. The important part is the type:

```text
string -> IO<Config>
```

The `T` is whatever the effect eventually produces. If the operation only performs work and has no interesting return value, examples often use a void-like `Unit`.

Calling `LoadConfigIO(path)` constructs a value describing an effect. The file read is still waiting inside that value. It runs only when the program eventually calls `Run`.

This toy wrapper preserves the pedagogical separation used when explaining Haskell's `IO`: actions can be defined and composed without being invoked immediately, and the `IO` operations provide sequential composition of those actions. Haskell's actual `IO` is an abstract runtime-supported type rather than this public `Func<T>` wrapper. ([Haskell][1])

Because the effect has not happened yet, the caller can still compose the value. `Map` keeps the same effect and transforms the value it will eventually produce:

```csharp
IO<string> summary =
    LoadConfigIO("pricing.json")
        .Map(RenderConfigSummary);
```

`Bind` (or flatMap) lets the value choose the next effectful operation and then combine both values:

```csharp
public IO<string> ReadTemplateIO(string path)
{
    return new IO<string>(() =>
        File.ReadAllText(path));
}

IO<string> page =
    LoadConfigIO("pricing.json")
        .Bind(config =>
            ReadTemplateIO(config.TemplatePath)
                .Map(template =>
                    RenderConfigPage(config, template)));
```

The natural question is how to get the `Config` out of `IO<Config>`. In the middle of a program, there is no general safe unwrap that lets the code continue as if no effect were involved. The options are to keep composing with `Map` and `Bind`, or return the `IO<Config>` outward until a boundary chooses to run it. The callback becomes part of the description, and the result remains an effect description until then.

`Map` and `Bind` build a larger description from smaller ones. Execution is still delayed.

That is why `IO` can be a monad even though running an action twice may observe two different worlds. For ordinary equational reasoning, the laws are about equivalence of composed descriptions; separate executions can still observe different external state.

The same point matters operationally. If an `IO<T>` describes a file read, interpreting the same description twice may read the file twice. Sharing, caching, and memoization should be explicit parts of the calling strategy; assignment alone is too vague to define those policies.

The eventual file read is still effectful. The useful property is that the **description** of the operation can be passed around, transformed, and composed as an ordinary value.

## Why executing at the edge matters

With `IO`, "move effects to the edge" means that interpretation happens at the boundary that owns the calling strategy. Code deeper in the program can still construct and combine `IO<T>` values:

```csharp
public IO<string> BuildConfigSummaryProgram(string path)
{
    return LoadConfigIO(path)
        .Map(RenderConfigSummary);
}
```

That function can itself be pure. Given the same path, it constructs the same description of a program.

The boundary operation interprets or runs the description:

```csharp
var program =
    BuildConfigSummaryProgram("pricing.json");

var summary =
    program.Run();
```

The boundary is valuable because it is the last point where the effect is still a value. Before `Run`, higher-level code can still decide whether the operation should run, whether it should be wrapped with logging, or whether it should be replaced by a test version.

After `Run`, the effect has already happened, and those policies cannot be applied retroactively. Calling `Run` inside a helper gives up that leverage:

```csharp
public string BuildConfigSummaryNow(string path)
{
    return LoadConfigIO(path)
        .Map(RenderConfigSummary)
        .Run();
}
```

The function has converted a composable effect description into an immediate world interaction. Returning the `IO` instead lets the caller decide how that effect should run as part of the rest of the program.

## Putting it together

Higher-order functions let another abstraction call our function on our behalf. That is valuable because it removes repetitive control flow and makes programs easier to compose.

Pure callbacks generally tolerate that handoff because the interesting behavior lies in the returned value. Effectful callbacks have a larger operational contract: timing, repetition, caching, replacement in tests, failure handling, and surrounding context can all matter.

`IO<T>` gives that operational contract room to be handled before the world is touched. The program can build a description, compose it with other descriptions, and run it at the boundary that owns the calling strategy.

[1]: https://www.haskell.org/tutorial/io.html "A Gentle Introduction to Haskell: IO"
