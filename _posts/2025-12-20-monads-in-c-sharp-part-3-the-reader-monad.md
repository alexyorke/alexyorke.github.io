---
title: "Monads in C# (Part 3): The Reader Monad"
date: 2025-12-20 09:00:00 +0000
---

## Monads in C# (Part 3): The Reader Monad

The Reader monad [0] lets you sequence and compose computations that depend on an immutable environment (context) without manually threading that environment through every call. It also lets you run a sub-computation under a modified view of that environment (via `Local`). In practice, this avoids “parameter drilling” by passing the environment once at the boundary and letting the composed pipeline carry it.

## Problem: parameter drilling

```csharp
static string GenerateCheckoutSummary(PricingEnv env, Cart cart) =>
    var total = CalculateCartTotal(env, cart)
    var priceFormatted = FormatPrice(env, total);
    return $"Final Amount: {priceFormatted}";
```

## Solution: return a Reader

```csharp
// No 'env' parameter
static Reader<PricingEnv, string> GenerateCheckoutSummary(Cart cart) =>
    CalculateCartTotal(cart)
        .Bind(FormatPrice)
        .Map(text => $"Final Amount: {text}");
```

You supply the environment once with `Run(env)`. `Bind`/`SelectMany` passes step results forward.
If your call chain is short, Reader may be unnecessary, see the section “When not to use Reader”.

## Reader in one sentence

Conceptually, `Reader<Env, T>` is `Func<Env, T>` plus a few combinators:
- `From`: Defines a step that requires access to the environment.
- `SelectMany` (`Bind`/flatMap): Sequences steps. It runs the first step, gets the result, and passes it to the next step, while passing the Environment along.
- `Select` (`Map`): Transforms the final result (e.g., formatting a decimal to a string).
- `Local`: Temporarily modifies the environment for a specific step.
(Pure/Unit exists too; we’ll defer it to the Appendix.)
You build the computation as a value (a pipeline you can pass around and test), and only run it once you have an env, typically at an application boundary [2].
Important: While the Reader pattern treats the environment as a fixed input for the pipeline, it does not strictly enforce immutability on the objects stored inside it. If your environment contains a mutable object (like a `List<T>`), Reader won't stop you from modifying it, though doing so breaks the functional "pure dependency" model. [1]

## A note on Dependency Injection

Reader is sometimes called “functional DI,” but that analogy is limited.
- A DI container answers: “How do I construct object graphs and manage lifetimes?”
- Reader answers: “How do I propagate context through a computation without adding parameters everywhere?”
Reader is not a replacement for a DI framework, like `ASP.NET Core DI`. Treat this article as a way to understand the pattern and its tradeoffs, not a prescription for idiomatic production C#. Also note that Reader can allocate many delegates/closures, so it may be a poor fit for hot paths.

## The setup

We’ll use one running example: pricing and formatting a checkout summary.
Each item’s price depends on:
- the current time (flash sale window)
- whether the current user is VIP
- … and also there’s a correlation ID for logging
Some values come from the boundary of the system on each request (time, current user, locale, correlation id, logger). In typical C# code, these get passed as arguments, pulled from ambient context, or injected via DI.
Here, we’ll model them as a single immutable environment (`PricingEnv`), build a `Reader<PricingEnv, T>` pipeline, then run it once at the boundary by supplying the environment.

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

In this example `PricingEnv` includes both request data (time/user/locale/correlation id/etc) and a small capability (`ILogger`) to show that the environment can carry services too.

## Core use-case

Goal: compute a checkout summary while keeping deep functions free of a `PricingEnv` parameter.

### Step 1: price an item

We’ll start at the leaves: the business logic for pricing a single item is straightforward (just apply a discount), but it still needs an environment to calculate the discount. With Reader, we model that as an `Env -> decimal` computation, take the item now, and delay supplying env until we run the whole pipeline at the boundary.
Read `Reader<PricingEnv, decimal>` as “a computation that needs `PricingEnv` later to produce a decimal”.

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

Next, we need to sum the prices. In a traditional design, `CalculateCartTotal` would require a `PricingEnv` parameter solely to pass it down to the child items. With Reader, we remove that noise. The function requires only a `Cart`; the dependency on the environment is encapsulated in the return type.
Aside: Because `Aggregate` isn’t monad-aware, the accumulator has to live inside Reader, which makes this look heavier than the underlying idea.

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

The signature stays small: `CalculateCartTotal(Cart cart)`. It does not accept `PricingEnv` as a parameter. It doesn't need to know about User Context or Loggers; it only needs to know how to sum up item prices.

### Step 3: format the total

Formatting depends on localization, so it’s also a Reader:

```csharp
static Reader<PricingEnv, string> FormatPrice(decimal amount) =>
    Reader.From<PricingEnv, string>(env =>
        amount.ToString("C", new System.Globalization.CultureInfo(env.CultureCode))
    );
```

### Step 4: compose the pipeline

You can compose these steps directly with `Bind` and `Map`. That works, but in C# it can get lambda-heavy as the pipeline grows:

```csharp
static Reader<PricingEnv, string> GenerateCheckoutSummary(Cart cart) =>
    CalculateCartTotal(cart)
        .Bind(FormatPrice)
        .Map(text => $"Final Amount: {text}");
```

The same pipeline is often more readable using LINQ query syntax:

```csharp
static Reader<PricingEnv, string> GenerateCheckoutSummary(Cart cart) =>
    from total in CalculateCartTotal(cart)
    from text in FormatPrice(total)
    select $"Final Amount: {text}";
```

If you are curious about the mechanics (or how Bind passes the result to the next step), check the Appendix for the full implementation of these operators.

## Run at the boundary

Up to this point, we’ve only built `Reader<PricingEnv, T>` values. Evaluation is deferred until you call `Run(env)` at the boundary.

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

That’s the whole pattern: compose in the functional core, then supply env once at the boundary and get a normal return value back.

## Local: the upsell / “what-if” feature

`Local` lets you reuse the same pipeline while temporarily changing the environment for just one sub-computation.

For example, suppose we want to tell the user how much they’d save if they were a VIP. We can compute the real total under the current environment, then compute a “what-if VIP” total by running the same calculation under a modified view of the environment:

```csharp
static Reader<PricingEnv, string> GenerateUpsellMessage(Cart cart) =>
    CalculateCartTotal(cart)
        .Bind(currentTotal =>
            CalculateCartTotal(cart)
                .Local(env => env with { IsVip = true })
                .Map(potentialTotal =>
                    currentTotal == potentialTotal
                        ? "You are getting the best price!"
                        : $"Upgrade to VIP to save {(currentTotal - potentialTotal):C}!"
                )
        );
```

The same idea is often clearer in LINQ query syntax:

```csharp
static Reader<PricingEnv, string> GenerateUpsellMessage(Cart cart) =>
    from currentTotal in CalculateCartTotal(cart)
        // Run the *same* calculation, but with a modified environment (VIP = true)
    from potentialTotal in CalculateCartTotal(cart).Local(env => env with { IsVip = true })
    select currentTotal == potentialTotal
        ? "You are getting the best price!"
        : $"Upgrade to VIP to save {(currentTotal - potentialTotal):C}!";
```

We avoid adding an extra isVip parameter or duplicating the pricing logic, it's the same computation, just evaluated under a modified environment for that one branch.

## Ask: reading the environment explicitly

Here, `Ask()` returns the current environment as a value inside the pipeline, so you can read fields from it at the point where it’s most convenient.

Most of the time you don’t need `Ask`, because you can just use `Reader.From(env => ...)`. But `Ask()` is a nice way to make the “Reader reads from the environment” idea explicit, especially when you want to pull a single value out of `PricingEnv` and use it later in a query.
For example, we can include the correlation id in the final summary without changing any function signatures:

```csharp
static Reader<PricingEnv, string> GenerateCheckoutSummary(Cart cart) =>
    from total in CalculateCartTotal(cart)
    from formatted in FormatPrice(total)
    from env in Reader.Ask<PricingEnv>()
    select $"Final Amount: {formatted} (Request={env.CorrelationId})";
```

## Testing
Reader gives you a built-in test seam: the pipeline is just a value that expects an environment.
No container setup or lifetime scoping required, tests simply supply a `PricingEnv`.
See the linked repository for more testing examples; code is omitted here for brevity.
## Optional: Capability Interfaces
If `PricingEnv` starts to feel too large, one refinement is to split it into smaller capability interfaces (Interface Segregation) so functions only depend on what they actually read.
In C#, this often isn’t worth the complexity: a minimal Reader like the one in this article can’t ergonomically combine different environment interfaces in one LINQ query (e.g., `Reader<IHasTax, ...>` with `Reader<IHasUser, ...>`), and type inference quickly gets painful.
### Why you don’t see `Pure` (Unit) much in this article
`Pure` (or Unit) lifts a plain value into a `Reader` that ignores the environment. It’s essential for the laws and for some combinators, but in day-to-day code you often start from a real environment-dependent step (`From(env => ...)`) and build outward.
You *do* see `Pure` show up when you need an identity/starting value, most commonly when folding/aggregating, where the accumulator has to start “inside” the monad (e.g., `Pure(0m)` in `Aggregate`).
In this article I call it `Pure`; the helper `Reader.Unit(...)` is just an alias for `Pure(...)`.

## When not to use Reader

Reader helps with parameter drilling, but it’s an extra abstraction that isn’t always worth it for smaller or straightforward call chains.
- The chain is short. For one or two calls, plain parameter passing is clearer.
- You’re already in DI-land. In `ASP.NET Core` services/controllers, inject what you need. Reader is most useful inside composed business-logic functions where you want to avoid manually threading an environment; it’s not a tool for object graph construction or lifetime management.
- You need mutable/evolving state. Reader is read-only. If state evolves through steps, you’re looking for state-threading (often modeled as State).
- You need very granular dependencies. If everything takes a giant Env, you can trade “parameter sprawl” for “environment coupling.” If Env grows into a god object, refactor toward narrower capabilities.

## Async in C#

Most apps have I/O. A practical default is to keep the Reader pipeline synchronous and do async work at the boundary. You *can* wrap `Task<T>` inside a `Reader`, but standard LINQ won’t await it, so the composition tends to get noisy, so you may end up having to write helpers like `BindAsync`.

### Recommended: Functional Core, Imperative Shell

Do async I/O to *build* the environment, run the Reader pipeline once (sync), then do async I/O to persist/emit results.
Flow: Fetch (async) → Run Reader (sync) → Persist (async)

## LanguageExt

While the implementation in the Appendix is perfect for understanding the mechanics, maintaining your own Monad library in a production codebase is generally discouraged.
If you plan to adopt this pattern extensively, I highly recommend looking at LanguageExt (by Paul Louth).

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

## Appendix: pipeline analogy

Think of `Bind` / `SelectMany` as a pipe connector:
- The same `PricingEnv` is supplied once at `Run(env)`.
- Each step runs under that same `env`.
- `Bind` passes the *result* of the current step into the next step.
If a step returned only a raw value, you couldn’t keep composing environment-dependent steps. Returning a `Reader` keeps the “pipe” composable.

## Footnotes

### [0] Why “monads are containers” breaks for Reader

The “container” metaphor works for `Maybe<T>` / `Result<T>` because their successful form literally contains a T; the other form represents “no value” or an error instead. `Reader<Env, T>` is different: it represents a computation `Env -> T` (a function waiting for context). There is literally no T to take out. Seeing Reader as a function also makes `Local` feel natural: it’s just running the same computation under a transformed environment.
[1] You can use Free Monads to separate IO Dead-Simple Dependency Injection - YouTube but this is outside the scope of this article.

### [2] “Boundary” definition

The boundary is also called an “edge”. The boundary is where your code touches the outside world (HTTP handlers, message handlers, UI events). It’s the place you gather request context, build `env`, and finally call `Run(env)` to produce plain values.
