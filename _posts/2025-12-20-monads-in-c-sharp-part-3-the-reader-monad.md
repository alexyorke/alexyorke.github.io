---
title: "Monads in C# (Part 3): The Reader Monad"
date: 2025-12-20 09:00:00 +0000
description: "Introduces the Reader monad in C# to avoid parameter drilling by threading a shared environment through composed computations, with a minimal implementation and examples."
---

**Previously in the series**: [List is a monad (Part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/), [Monads in C# (Part 2): Result](https://alexyorke.github.io/2025/09/13/monads-in-c-sharp-part-2-result-either/)

In Part 2 you built `Result<TSuccess, TError>` to model failures explicitly: `Map`/`Bind` for composition, and `Match` to unwrap at the boundary (e.g., HTTP/UI) without leaking `Result` into serialization.

The Reader monad lets you sequence and compose computations that depend on a shared environment (typically treated as immutable) without manually threading that environment through every call. The computation doesn't run until you call `Run(env)`, so it’s closer to a blueprint, or a recipe.

It also lets you run a sub-computation under a modified view of that environment (via `Local`). In practice, this avoids "parameter drilling" by passing the environment once at the boundary and letting the composed pipeline carry it.

## Problem: parameter drilling

```csharp
static string GenerateCheckoutSummary(PricingEnv env, Cart cart)
{
    var total = CalculateCartTotal(env, cart);
    var priceFormatted = FormatPrice(env, total);
    return $"Final Amount: {priceFormatted}";
}
```

## Solution: return a Reader

```csharp
// No `env` parameter
static Reader<PricingEnv, string> GenerateCheckoutSummary(Cart cart) =>
    CalculateCartTotal(cart)
        .Bind(FormatPrice)
        .Map(text => $"Final Amount: {text}");
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

We’ll use one running example: pricing + formatting a checkout summary using request-ish context (time, VIP flag, locale, correlation ID, logger). We’ll bundle that into `PricingEnv`, build a `Reader<PricingEnv, T>` pipeline, then run it at the boundary.

```csharp
internal sealed class ConsoleLogger : ILogger
{
    public void Log(string msg) => Console.WriteLine(msg);
}

public sealed record Cart(IEnumerable<CartItem> Items);
public sealed record CartItem(decimal BasePrice, string Name);

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

Goal: compute a checkout summary while keeping deep functions free of a `PricingEnv` parameter.

### Step 1: price an item

Start at the leaves: pricing an item needs the environment (VIP/time/logger), so we model it as a `PricingEnv -> decimal` computation and supply `env` later.

```csharp
static Reader<PricingEnv, decimal> CalculateItemPrice(CartItem item) =>
    Reader.From<PricingEnv, decimal>(env =>
    {
        const decimal VipOrFlashSaleDiscountRate = 0.10m;
        const decimal NoDiscountRate = 0.00m;
        const decimal FullPriceMultiplier = 1.00m;

        bool isFlashSale = env.Now.Hour >= 17 && env.Now.Hour < 19;
        decimal discountRate = (env.IsVip || isFlashSale)
            ? VipOrFlashSaleDiscountRate
            : NoDiscountRate;
        decimal finalPrice = item.BasePrice * (FullPriceMultiplier - discountRate);
        env.Logger.Log(
            $"Item={item.Name} Base={item.BasePrice} DiscountRate={discountRate:P0} Final={finalPrice} Request={env.CorrelationId}"
        );
        return finalPrice;
    });
```

### Step 2: sum the cart

Sum the prices by folding item-price Readers.

```csharp
static Reader<PricingEnv, decimal> CalculateCartTotal(Cart cart)
{
    return cart.Items
        // Start with a Reader returning 0
        .Aggregate(Reader.Unit<PricingEnv, decimal>(0m),
            (accReader, item) =>
                // Combine the accumulator with the current item's price
                from currentTotal in accReader
                from itemPrice in CalculateItemPrice(item)
                select currentTotal + itemPrice
        );
}
```

The signature stays small: `CalculateCartTotal(Cart cart)`. The dependency is captured by the return type and handled by `CalculateItemPrice`.

### Step 3: format the total

Formatting depends on localization, so it's also a Reader:

```csharp
static Reader<PricingEnv, string> FormatPrice(decimal amount) =>
    Reader.From<PricingEnv, string>(env =>
        amount.ToString("C", new System.Globalization.CultureInfo(env.CultureCode))
    );
```

### Step 4: compose the pipeline

Compose directly with `Bind`/`Map`:

```csharp
static Reader<PricingEnv, string> GenerateCheckoutSummary(Cart cart) =>
    CalculateCartTotal(cart)
        .Bind(FormatPrice)
        .Map(text => $"Final Amount: {text}");
```

Or with LINQ query syntax:

```csharp
static Reader<PricingEnv, string> GenerateCheckoutSummary(Cart cart) =>
    from total in CalculateCartTotal(cart)
    from text in FormatPrice(total)
    select $"Final Amount: {text}";
```

## Run at the boundary

Up to this point, we've only built `Reader<PricingEnv, T>` values. The environment-dependent evaluation is deferred until you call `Run(env)` at the boundary (HTTP handler, message handler, UI event).

```csharp
static string HandleCheckout(Cart cart)
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
    Reader<PricingEnv, string> pipeline = GenerateCheckoutSummary(cart);

    // Run it once to get a plain result
    string summary = pipeline.Run(env);

    return summary;
}
```

That's the whole pattern: compose in the functional core, then supply the environment once at the boundary and get a normal return value back.

## Local: the upsell / "what-if" feature

`Local` runs a sub-computation under a transformed view of the environment.

For example: compute the real total, then recompute under `IsVip = true` to show potential savings.

```csharp
static Reader<PricingEnv, string> GenerateUpsellMessage(Cart cart) =>
    CalculateCartTotal(cart)
        .Bind(currentTotal =>
            CalculateCartTotal(cart)
                .Local(env => env with { IsVip = true })
                .Bind(potentialTotal =>
                    currentTotal == potentialTotal
                        ? Reader.Unit<PricingEnv, string>("You are getting the best price!")
                        : FormatPrice(currentTotal - potentialTotal)
                            .Map(savings => $"Upgrade to VIP to save {savings}!")
                )
        );
```

The same idea is often clearer in LINQ query syntax:

```csharp
static Reader<PricingEnv, string> GenerateUpsellMessage(Cart cart) =>
    from currentTotal in CalculateCartTotal(cart)
    // Run the *same* calculation, but with a modified environment (`IsVip = true`)
    from potentialTotal in CalculateCartTotal(cart).Local(env => env with { IsVip = true })
    from message in currentTotal == potentialTotal
        ? Reader.Unit<PricingEnv, string>("You are getting the best price!")
        : from savingsText in FormatPrice(currentTotal - potentialTotal)
          select $"Upgrade to VIP to save {savingsText}!"
    select message;
```

We avoid adding an extra `isVip` parameter or duplicating the pricing logic: it’s the same logic, recomputed under a modified environment for that one branch.

## Ask: reading the environment explicitly

Here, `Ask()` returns the current environment as a value inside the pipeline, so you can read fields from it at the point where it's most convenient.

Most of the time you don't need `Ask`, because you can just use `Reader.From(env => ...)`. But `Ask()` is a nice way to make the "Reader reads from the environment" idea explicit, especially when you want to pull a single value out of `PricingEnv` and use it later in a query.

For example, we can include the correlation ID in the final summary without changing any function signatures:

```csharp
static Reader<PricingEnv, string> GenerateCheckoutSummary(Cart cart) =>
    from total in CalculateCartTotal(cart)
    from formatted in FormatPrice(total)
    from env in Reader.Ask<PricingEnv>()
    select $"Final Amount: {formatted} (Request={env.CorrelationId})";
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