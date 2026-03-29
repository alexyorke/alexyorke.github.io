---
title: "Monads in C# (Part 3): The Reader Monad"
date: 2025-12-20 09:00:00 +0000
description: "Introduces the Reader monad in C# to avoid parameter drilling by threading a shared environment through composed computations, with a minimal implementation and examples."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

In Part 2 you built `Result<TSuccess, TError>` to model failures explicitly: `Map`/`Bind` for composition, and `Match` to unwrap at the boundary (e.g., HTTP/UI) without leaking `Result` into serialization.

The Reader monad lets you sequence and compose computations that depend on a shared environment (typically treated as immutable) without manually threading that environment through every call. The computation doesn't run until you call `Run(env)`, so it’s closer to a blueprint, or a recipe.

It also lets you run a sub-computation under a modified view of that environment (via `Local`). In practice, this avoids "parameter drilling" by passing the environment once at the boundary and letting the composed pipeline carry it.

It also helps to **let go of the “monads are containers” mental model**.
That framing sort of works for `Maybe<T>` and `Result<TSuccess, TError>` because they *look* like they “contain” a value (or not). But it stops being a good fit pretty quickly: Reader doesn’t “contain” a value, it *delays* a computation until you provide some context.

So what is a monad, really? It’s not a magic list of blessed types; it’s a **pattern**: a type that gives you `Unit`/`Pure` (lift a value), `Bind`/`SelectMany` (a.k.a. flatMap, sequence computations), and that obeys the monad laws (so refactoring doesn’t change meaning). The point is **composability**: you get to chain steps without re-implementing the plumbing each time.

## Problem: parameter drilling

```csharp
static string GenerateQuoteSummary(PricingEnv env, string serviceName)
{
    var basePrice = GetBasePrice(env, serviceName);
    var discounted = ApplyDiscount(env, basePrice);
    var withTax = AddTax(env, discounted);
    var result = FormatResult(env, withTax);

    return $"Quote for {serviceName}: {result}";
}
```

Notice how `env` gets threaded through every call. The same thing happens with logging, telemetry, time, localization, correlation IDs, request context, etc.

## Solution: return a Reader

```csharp
// No `env` parameter
static Reader<PricingEnv, string> GenerateQuote(string serviceName) =>
    from basePrice in GetBasePrice(serviceName)
    from discounted in ApplyDiscount(basePrice)
    from withTax in AddTax(discounted)
    from result in FormatResult(withTax)
    select $"Quote for {serviceName}: {result}";
```

You supply the environment once with `Run(env)`. `Bind`/`SelectMany` passes step results forward.
If your call chain is short, Reader may be unnecessary, see the section "When not to use Reader".

## Reader in one sentence

Conceptually, `Reader<TEnv, T>` is `Func<TEnv, T>` plus a few combinators:
- `From`: Define a step that needs access to the environment.
- `SelectMany` / `Bind`: When you call `Run(env)`, sequence steps while forwarding the same environment.
- `Local`: Run one step under a transformed view of the environment.

You build the computation as a value, then run it once you have an environment (typically at an application boundary).

Important: Reader doesn’t enforce immutability—it’s just conventional to treat the environment as immutable (and avoid mutating things stored inside it).

## A note on Dependency Injection

Reader is sometimes called “functional DI,” but it’s not a replacement for a DI container. It’s a way to propagate context through a computation without turning every method signature into “and also pass `env`.”

## The setup

We’ll use one running example: generating a quote for a single service subscription using request-ish context (time, VIP flag, locale, correlation ID, logger). We’ll bundle that into `PricingEnv`, build a `Reader<PricingEnv, T>` pipeline, then run it at the boundary.

```csharp
internal sealed class ConsoleLogger : ILogger
{
    public void Log(string msg) => Console.WriteLine(msg);
}

public interface IUserContext { bool IsVip { get; } }
public interface ILocalization { string CultureCode { get; } }
public interface ILogger { void Log(string msg); }
public interface IRequestContext { string CorrelationId { get; } }

public sealed record PricingEnv(
    DateTime Now,
    bool IsVip,
    string CultureCode,
    ILogger Logger,
    string CorrelationId
) : IUserContext, ILocalization, IRequestContext;
```

In this example `PricingEnv` includes both request data (time/user/locale/correlation ID/etc) and a small capability (`ILogger`) to show that the environment can carry services too.

## Core use-case

This is a common friction point: if you try to “iterate over a collection” inside Reader, you quickly run into the **Traversable** problem.

Combining a `List<Reader<...>>` into a `Reader<List<...>>` (or combining into a sum) requires `Sequence`/`Traverse`, and implementing that in C# tends to look like an intimidating `Aggregate`/fold.

That’s a perfectly valid topic, but it’s a side quest. The main point of Reader is **implicit context**.

So instead, we’ll use a multi-step *linear* pipeline: generate a quote for a single service.

### Step 1–4: the building blocks

We’ll build small steps that each produce a `Reader<PricingEnv, ...>`. Some steps are pure (“no environment needed”), but we still lift them into Reader to keep the pipeline shape consistent.

```csharp
// ---------------------------------------------------------
// The Building Blocks
// ---------------------------------------------------------

// 1. Pure calculation (lifted into Reader)
static Reader<PricingEnv, decimal> GetBasePrice(string serviceName)
{
    // Simulating a database lookup or pure logic
    var price = serviceName == "ProPlan" ? 100m : 50m;
    return Reader.Unit<PricingEnv, decimal>(price);
}

// 2. Logic that depends on VIP status
static Reader<PricingEnv, decimal> ApplyDiscount(decimal price) =>
    Reader.From<PricingEnv, decimal>(env =>
    {
        if (env.IsVip) return price * 0.90m; // 10% off
        return price;
    });

// 3. Logic that depends on Time or Logging
static Reader<PricingEnv, decimal> AddTax(decimal price) =>
    Reader.From<PricingEnv, decimal>(env =>
    {
        // Example: Tax is higher after 5 PM (silly rule, but illustrates the point)
        decimal taxRate = env.Now.Hour > 17 ? 0.20m : 0.15m;

        env.Logger.Log($"Calculating tax at {taxRate:P0}");
        return price * (1.0m + taxRate);
    });

// 4. Formatting (Localization)
static Reader<PricingEnv, string> FormatResult(decimal finalPrice) =>
    Reader.From<PricingEnv, string>(env =>
        finalPrice.ToString("C", new System.Globalization.CultureInfo(env.CultureCode)));
```

### Step 5: compose the pipeline

This is the payoff: **clean linear composition** with implicit context. No passing `env` four times.

```csharp
static Reader<PricingEnv, string> GenerateQuote(string serviceName)
{
    return
        from basePrice in GetBasePrice(serviceName)
        from discounted in ApplyDiscount(basePrice)
        from withTax in AddTax(discounted)
        from result in FormatResult(withTax)
        select $"Quote for {serviceName}: {result}";
}
```

## Run at the boundary

Up to this point, we've only built `Reader<PricingEnv, T>` values. The environment-dependent evaluation is deferred until you call `Run(env)` at the boundary (HTTP handler, message handler, UI event).

```csharp
static string HandleQuote(string serviceName)
{
    // In a real app these come from the outside world:
    DateTime now = DateTime.UtcNow;
    bool isVip = false; // e.g., from the authenticated user
    string cultureCode = "en-US"; // e.g., from headers / user settings
    ILogger logger = new ConsoleLogger();
    string correlationId = Guid.NewGuid().ToString("N");

    var env = new PricingEnv(
        Now: now,
        IsVip: isVip,
        CultureCode: cultureCode,
        Logger: logger,
        CorrelationId: correlationId
    );

    // Build the computation (still just a value)
    Reader<PricingEnv, string> pipeline = GenerateQuote(serviceName);

    // Run it once to get a plain result
    string summary = pipeline.Run(env);

    return summary;
}
```

That's the whole pattern: compose in the functional core, then supply the environment once at the boundary and get a normal return value back.

## Local: the upsell / "what-if" feature

`Local` runs a sub-computation under a transformed view of the environment.

For example: compute the current quote, then re-run the same pipeline under `IsVip = true` to show a “what if you were VIP?” price.

```csharp
static Reader<PricingEnv, string> CompareVipPrice(string serviceName) =>
    from current in GenerateQuote(serviceName)
    // Run the WHOLE pipeline again, but pretend the user is VIP
    from prediction in GenerateQuote(serviceName)
                       .Local(env => env with { IsVip = true })
    select $"{current} (If you were VIP: {prediction})";
```

We avoid adding an extra `isVip` parameter or duplicating the pricing logic: it’s the same logic, recomputed under a modified environment for that one branch.

## Ask: reading the environment explicitly

Here, `Ask()` returns the current environment as a value inside the pipeline, so you can read fields from it at the point where it's most convenient.

Most of the time you don't need `Ask`, because you can just use `Reader.From(env => ...)`. But `Ask()` is a nice way to make the "Reader reads from the environment" idea explicit, especially when you want to pull a single value out of `PricingEnv` and use it later in a query.

For example, we can include the correlation ID in the final summary without changing any function signatures:

```csharp
static Reader<PricingEnv, string> GenerateQuoteWithCorrelation(string serviceName) =>
    from quote in GenerateQuote(serviceName)
    from env in Reader.Ask<PricingEnv>()
    select $"{quote} (Request={env.CorrelationId})";
```

## Testing
Reader makes dependency injection explicit in the input, so tests can supply a fake environment without a container.

No container setup or lifetime scoping required, tests simply supply a `PricingEnv`.
See the linked repository ([`alexyorke/ReaderMonad`](https://github.com/alexyorke/ReaderMonad)) for more testing examples; code is omitted here for brevity.

## Optional: Capability Interfaces
If `PricingEnv` starts to feel too large, you can split it into capability interfaces. In practice, you’ll usually still want a single shared `TEnv` (or adapter helpers) so your Readers compose cleanly.

## When not to use Reader

Reader helps with parameter drilling, but it's an extra abstraction that isn't always worth it for smaller or straightforward call chains.
- The chain is short. For one or two calls, plain parameter passing is clearer.
- You're already in DI-land. In `ASP.NET Core` services/controllers, inject what you need. Reader is most useful inside composed business-logic functions where you want to avoid manually threading an environment; it's not a tool for object graph construction or lifetime management.
- You need mutable/evolving state. Reader is read-only. If state evolves through steps, you're looking for state-threading (often modeled as `State`).
- You need very granular dependencies. If everything takes a giant `PricingEnv`, you can trade "parameter sprawl" for "environment coupling." Reader often improves call-site ergonomics, but it doesn’t eliminate dependency coupling—it just centralizes it. If `PricingEnv` grows into a god object, refactor toward narrower capabilities.

## Async in C#

Most apps have I/O. In C#, many people either (a) keep Reader pipelines pure/sync and do I/O at the boundary, **or** (b) use an async Reader (`Reader<TEnv, Task<T>>`) with `BindAsync`-style helpers.

LINQ query syntax won’t magically await; you’ll usually want async-specific combinators (`BindAsync` / a `SelectMany` that awaits internally) or a dedicated `ReaderAsync`.

## LanguageExt

If you plan to adopt this pattern extensively, consider [LanguageExt (by Paul Louth)](https://github.com/louthy/language-ext).

## Mechanics (short version)

Reader isn’t a “container monad.” It’s basically a function waiting for context: `Reader<TEnv, T>` ≈ `Func<TEnv, T>`.

So `Bind`/`SelectMany` doesn’t execute anything when you build a pipeline; it builds a new Reader that forwards the same `env` through the chain when you call `Run(env)`.

If you want to go further: [Dead-Simple Dependency Injection by Rúnar Óli Bjarnason](https://polyglot.jamie.ly/programming/2014/10/20/dead-simple-dependency-injection-r%C3%BAnar-%C3%B3li.html).


## Appendix: a minimal Reader implementation

```csharp
public sealed class Reader<TEnv, T>
    {
        private readonly Func<TEnv, T> _run;
        public Reader(Func<TEnv, T> run)
        {
            _run = run;
        }
        public T Run(TEnv env)
        {
            return _run(env);
        }

        // Unit / Pure: lifts a value into Reader (ignores the environment)
        public static Reader<TEnv, T> Pure(T value)
        {
            return new Reader<TEnv, T>(
                _ =>
                {
                    return value;
                }
            );
        }

        // Functor: Map transforms the eventual result
        public Reader<TEnv, TResult> Map<TResult>(Func<T, TResult> f)
        {
            return new Reader<TEnv, TResult>(
                env =>
                {
                    T a = _run(env);
                    TResult b = f(a);
                    return b;
                }
            );
        }

        // LINQ Select is just Map
        public Reader<TEnv, TResult> Select<TResult>(Func<T, TResult> f)
        {
            return Map(f);
        }

        // Monad: Bind sequences computations that depend on the same environment
        public Reader<TEnv, TResult> Bind<TResult>(Func<T, Reader<TEnv, TResult>> f)
        {
            return new Reader<TEnv, TResult>(
                env =>
                {
                    T a = _run(env);                    // run first computation
                    Reader<TEnv, TResult> next = f(a);   // choose next computation based on result
                    TResult b = next.Run(env);           // run next computation under the same env
                    return b;
                }
            );
        }

        // Enables LINQ query syntax: from x in ... from y in ... select ...
        public Reader<TEnv, TResult> SelectMany<TMid, TResult>(
            Func<T, Reader<TEnv, TMid>> bind,
            Func<T, TMid, TResult> project)
        {
            return Bind(
                a =>
                {
                    Reader<TEnv, TMid> rb = bind(a);

                    return rb.Map(
                        b =>
                        {
                            return project(a, b);
                        }
                    );
                }
            );
        }

        // Ask: returns the current environment
        public static Reader<TEnv, TEnv> Ask()
        {
            return new Reader<TEnv, TEnv>(
                env =>
                {
                    return env;
                }
            );
        }

        // Local: runs this Reader under a transformed environment
        public Reader<TEnv, T> Local(Func<TEnv, TEnv> transform)
        {
            return new Reader<TEnv, T>(
                env =>
                {
                    TEnv env2 = transform(env);
                    T result = _run(env2);
                    return result;
                }
            );
        }
    }

    // Static helpers for ergonomics (optional)
    public static class Reader
    {
        public static Reader<TEnv, T> Unit<TEnv, T>(T value)
        {
            return Reader<TEnv, T>.Pure(value);
        }

        public static Reader<TEnv, TEnv> Ask<TEnv>()
        {
            return Reader<TEnv, TEnv>.Ask();
        }

        public static Reader<TEnv, T> From<TEnv, T>(Func<TEnv, T> f)
        {
            return new Reader<TEnv, T>(f);
        }
    }
```