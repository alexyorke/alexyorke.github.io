---

title: "List is a monad (part 2)"
date: 2025-06-30
---

# **Monads in C# (Part 2): Result (aka Either) with practical, everyday examples**

In Part 1 you built `Maybe` to transform a value if present, and `Bind` (aka `FlatMap`) to chain steps that may not produce a value. This part keeps that **same shape** but lets the “no value” branch carry **a reason**. We’ll introduce a `Result<T, TErr>`, and walk through real‑world examples (config, files/JSON, and sequential API calls).

*If you think in LINQ:* `Map` ≈ `Select`, `Bind`/`FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

**What you’ll build:**

1. Introduce `Result<T, TErr>` (aka Either).
2. Apply it to **config parsing**, **file+JSON**, and **sequential API calls**.
   **Mental model:** `Map` ≈ LINQ `Select`; `Bind` ≈ `SelectMany`; use `Match` at the boundary.

---

## **Result (aka Either): when “missing” needs a reason**

`Maybe<T>` tells us **whether** a value exists. Sometimes, we need **why** it doesn’t exist. We keep the same straight‑line composition:

* **`Map`** - transform the **success** value
* **`Bind`** - chain a function returning another `Result<...>`

...and add a failure branch that carries an **error**.

Think of it like:

* `Ok(value)` -> like `Some(value)`
* `Err(message)` -> like `None()`, **but with a reason**

---

## **Scenario: Parse & validate configuration (pure, in‑memory)**

We’ll assume the configuration key/values are in memory (e.g., a `Dictionary<string,string>`). These variants illustrate where `Result<T, TErr>` fits.

> **Framing note (avoid conflation):** The point here isn’t that “.NET is inconsistent.” The BCL deliberately uses *exceptions* for exceptional conditions and **Try\*** patterns (`TryParse`, `TryGetValue`) for expected failures. The problem for *composition* is that **mixing shapes** (throwing vs. booleans/nulls/status codes) forces call sites to write glue code. A `Result` gives you a **single, composable shape** for error flow, independent of what the underlying APIs do.

### **Example 1,  Baseline exceptions (sync, pure)**

**Function:**

```csharp
public enum Mode { Development, Staging, Production }
public sealed record AppConfig(int MaxRetries, int TimeoutSeconds, Mode Mode);

public static AppConfig BuildConfigBasic(IReadOnlyDictionary<string, string> cfg)
{
    // Will throw if missing key or parse fails (KeyNotFoundException, FormatException, ArgumentException)
    var maxRetries = int.Parse(
        cfg["MaxRetries"],
        System.Globalization.NumberStyles.Integer,
        System.Globalization.CultureInfo.InvariantCulture);

    var timeoutSeconds = int.Parse(
        cfg["TimeoutSeconds"],
        System.Globalization.NumberStyles.Integer,
        System.Globalization.CultureInfo.InvariantCulture);

    var mode = Enum.Parse<Mode>(cfg["Mode"], ignoreCase: true);

    if (maxRetries is < 0 or > 10)
        throw new FormatException("MaxRetries must be between 0 and 10.");
    if (timeoutSeconds is < 1 or > 300)
        throw new FormatException("TimeoutSeconds must be between 1 and 300.");

    return new AppConfig(maxRetries, timeoutSeconds, mode);
}
```

**Caller vignette (where control flow actually matters):**

```csharp
public static void RenderDashboard(IReadOnlyDictionary<string, string> cfg)
{
    try
    {
        var app = BuildConfigBasic(cfg); // any missing/invalid field throws here
        SaveConfigToCache(app);
        UpdateUI(app);
    }
    catch (Exception ex) // KeyNotFoundException, FormatException, ArgumentException, ...
    {
        ShowError($"Could not build config: {ex.Message}");
        return; // avoid continuing the flow on failure
    }

    Log("Dashboard updated.");
}
```

A common step is to convert a raw configuration dictionary (e.g., from a file) into a strongly typed `AppConfig`. With exceptions, control jumps to the `catch`; with `null` or status codes, you must branch explicitly. **Neither shape composes by itself** when you string multiple steps together; the calling code must coordinate the control flow.

> *Note on compile-time checks:* C#’s definite‑assignment analysis prevents some misuse (e.g., using an unassigned local). The issue here isn’t uninitialized variables; it’s that *error flow is implicit and scattered*, so each call site must manually orchestrate try/catch and early returns.

---

### **Example 2,  Try‑pattern as a tuple (fast‑fail without throwing on content)**

```csharp
public static (bool Success, AppConfig Config, string? Error)
    TryBuildConfig(IReadOnlyDictionary<string, string> cfg)
{
    if (!cfg.TryGetValue("MaxRetries", out var maxRetriesText))
        return (false, default!, "Missing key: MaxRetries");
    if (!int.TryParse(maxRetriesText,
            System.Globalization.NumberStyles.Integer,
            System.Globalization.CultureInfo.InvariantCulture,
            out var maxRetries))
        return (false, default!, $"Invalid integer for MaxRetries: \"{maxRetriesText}\"");
    if (maxRetries is < 0 or > 10)
        return (false, default!, "MaxRetries must be between 0 and 10.");

    if (!cfg.TryGetValue("TimeoutSeconds", out var timeoutText))
        return (false, default!, "Missing key: TimeoutSeconds");
    if (!int.TryParse(timeoutText,
            System.Globalization.NumberStyles.Integer,
            System.Globalization.CultureInfo.InvariantCulture,
            out var timeoutSeconds))
        return (false, default!, $"Invalid integer for TimeoutSeconds: \"{timeoutText}\"");
    if (timeoutSeconds is < 1 or > 300)
        return (false, default!, "TimeoutSeconds must be between 1 and 300.");

    if (!cfg.TryGetValue("Mode", out var modeText))
        return (false, default!, "Missing key: Mode");
    if (!Enum.TryParse<Mode>(modeText, ignoreCase: true, out var mode))
        return (false, default!, $"Invalid Mode: \"{modeText}\" (Development|Staging|Production)");

    return (true, new AppConfig(maxRetries, timeoutSeconds, mode), null);
}
```

**Caller:**

```csharp
var (ok, app, err) = TryBuildConfig(cfg);
if (!ok) { ShowError(err!); return; }
SaveConfigToCache(app);
UpdateUI(app);
```

This reads linearly and avoids throwing for expected input errors. But as soon as you chain multiple steps, you recreate repetitive `if (!ok)` plumbing, an ad‑hoc `Result`. The tuple type also **permits invalid states** (“`Success == false` but `Config` is read anyway”), because the compiler can’t enforce you to check `ok` before using `Config`.

---

## **Scenario: File + JSON (pure, deterministic “source”)**

**Intent:** Compose a config from a deterministic source (no I/O talk here), returning only `Result<AppConfig, string>`.

We’ll use a `Result` abstraction (as found in many languages and libraries) so we can focus on composition rather than re‑implementing plumbing. The goal is to build an `AppConfig` from a deterministic source (e.g., a read‑only dictionary). For concreteness, we’ll show how the internal validate/parse step might work, though callers don’t need those details.

Instead of throwing or returning null (or other behavior), functions return `Result`: `Ok(value)` on success or `Err(error)` on failure (using `Ok/Err` to avoid left/right terminology). This keeps control flow predictable: successful values flow through `Map`/`Bind`, while failures short‑circuit and carry the error without exceptions or null checks. Because `Result` has a common shape, APIs that return it **compose naturally** regardless of their internals. At the boundary, typically once, the caller handles the final outcome and can inspect any error produced by the pipeline.

```csharp
using System;
using System.Collections.Generic;
using System.Globalization;

// Domain (kept identical to earlier examples)
public enum Mode { Development, Staging, Production }
public sealed record AppConfig(int MaxRetries, int TimeoutSeconds, Mode Mode);

// --- Small, pure decoders from an in-memory, deterministic source (e.g., JSON already parsed to a dictionary) ---
public static class ConfigDecoders
{
    public static Result<int, string> GetIntInRange(
        IReadOnlyDictionary<string, string> cfg,
        string key,
        int min,
        int max)
    {
        if (!cfg.TryGetValue(key, out var text))
            return Result<int, string>.Err($"Missing key: {key}");

        if (!int.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value))
            return Result<int, string>.Err($"Invalid integer for {key}: \"{text}\"");

        if (value < min || value > max)
            return Result<int, string>.Err($"{key} must be between {min} and {max}.");

        return Result<int, string>.Ok(value);
    }

    public static Result<TEnum, string> GetEnum<TEnum>(
        IReadOnlyDictionary<string, string> cfg,
        string key)
        where TEnum : struct, Enum
    {
        if (!cfg.TryGetValue(key, out var text))
            return Result<TEnum, string>.Err($"Missing key: {key}");

        if (!Enum.TryParse<TEnum>(text, ignoreCase: true, out var value))
        {
            var allowed = string.Join("|", Enum.GetNames(typeof(TEnum)));
            return Result<TEnum, string>.Err($"Invalid {key}: \"{text}\" ({allowed})");
        }

        return Result<TEnum, string>.Ok(value);
    }
}

// Optional validation (pure)
public static class AppConfigValidation
{
    public static Result<AppConfig, string> Validate(AppConfig cfg)
    {
        if (cfg.MaxRetries < 0 || cfg.MaxRetries > 10)
            return Result<AppConfig, string>.Err("MaxRetries must be between 0 and 10.");
        if (cfg.TimeoutSeconds < 1 || cfg.TimeoutSeconds > 300)
            return Result<AppConfig, string>.Err("TimeoutSeconds must be between 1 and 300.");
        return Result<AppConfig, string>.Ok(cfg);
    }
}

// Entry point for this scenario: compose from a deterministic, in-memory source.
// Note the consistent shape: takes IReadOnlyDictionary<string,string>, returns Result<AppConfig,string>.
public static class AppConfigComposition
{
    public static Result<AppConfig, string> LoadAppConfig(IReadOnlyDictionary<string, string> cfg)
    {
        var parsed =
            ConfigDecoders.GetIntInRange(cfg, "MaxRetries", 0, 10)
                .Bind(max =>
                    ConfigDecoders.GetIntInRange(cfg, "TimeoutSeconds", 1, 300)
                        .Bind(timeout =>
                            ConfigDecoders.GetEnum<Mode>(cfg, "Mode")
                                .Map(mode => new AppConfig(max, timeout, mode)))));

        return parsed.Bind(AppConfigValidation.Validate);
    }
}
```

You could write another function that takes an `AppConfig` and returns a `Result<AppConfig, string>` and drop it into this pipeline, no extra `if`/`try`/`return` boilerplate. This is the power of **monadic** composition: control‑flow and error propagation are “hoisted” into a reusable shape.

---

## **Scenario: Sequential API calls (auth -> user -> orders)**

**Intent:** Compose three dependent calls and return either a **numeric total** or an **error**, still no side effects.

```csharp
using System;
using System.Collections.Generic;

// Domain
public sealed class Token
{
    public string Value { get; }
    public Token(string value) { Value = value; }
}

public sealed class User
{
    public string Id { get; }
    public User(string id) { Id = id; }
}

public sealed class Order
{
    public string Id { get; }
    public decimal Amount { get; }
    public Order(string id, decimal amount) { Id = id; Amount = amount; }
}

// --- Assumed existing Result-returning functions (provided elsewhere) ---
// Result<Token, string> GetToken();
// Result<User, string> GetUser(Token token);
// Result<IReadOnlyList<Order>, string> GetOrders(User user);

public static class OrderFlows
{
    // Keep the numeric shape as long as possible so downstream code can still compose arithmetically.
    public static Result<decimal, string> GetTotalAmount()
    {
        return GetToken()
            .Bind(token => GetUser(token))
            .Bind(user => GetOrders(user))
            .Map(orders =>
            {
                decimal sum = 0m;
                foreach (Order o in orders)
                {
                    sum += o.Amount;
                }
                return sum;
            });
    }

    // Collapsed presentation: formats success into a string.
    // NOTE: On error, Bind short-circuits and the error bubbles out unchanged.
    // That means the returned value is Result<string, string>:
    //   - Ok: contains the formatted message (e.g., "Total: $42.00")
    //   - Err: contains the error from whichever step failed
    // This looks convenient, but you've now lost the numeric total for further composition.
    public static Result<string, string> GetTotalMessage()
    {
        return GetTotalAmount()
            .Map(total => $"Total: {total:C}");
        // We could add MapError/Recover helpers later to transform errors.
    }
}
```

---

## **Introducing `Result<T, TErr>`**

Below is a minimal, complete `Result<T, TErr>` with `Map`, `Bind`, and `Match`. `FlatMap` is provided as an alias for those who prefer that name.

```csharp
public sealed class Result<T, TErr>
{
    // Track which branch we're on (mirrors Maybe's internal _has flag).
    private readonly bool _isOk;

    // Success value (when _isOk is true).
    private readonly T _value;

    // Error value (when _isOk is false).
    private readonly TErr _error;

    // Success constructor (parallel to Maybe.Some).
    private Result(T value)
    {
        _isOk = true;
        _value = value;
        _error = default;
    }

    // Error constructor (parallel to Maybe.None but with a reason).
    private Result(TErr error)
    {
        _isOk = false;
        _value = default!;
        _error = error;
    }

    // Factory methods (shape: static constructors like Maybe.Some/None).
    public static Result<T, TErr> Ok(T value)
    {
        return new Result<T, TErr>(value);
    }

    public static Result<T, TErr> Err(TErr error)
    {
        return new Result<T, TErr>(error);
    }

    // Map: transform the success value, pass errors through unchanged.
    public Result<U, TErr> Map<U>(Func<T, U> f)
    {
        if (_isOk)
        {
            return Result<U, TErr>.Ok(f(_value));
        }
        else
        {
            return Result<U, TErr>.Err(_error);
        }
    }

    // Bind (aka FlatMap): chain a function returning Result.
    public Result<U, TErr> Bind<U>(Func<T, Result<U, TErr>> next)
    {
        if (_isOk)
        {
            return next(_value);
        }
        else
        {
            return Result<U, TErr>.Err(_error);
        }
    }

    // Optional alias for those who prefer the name FlatMap.
    public Result<U, TErr> FlatMap<U>(Func<T, Result<U, TErr>> next)
    {
        return Bind(next);
    }
}
```

At some point, you do need to be able to read the error from `Result`, otherwise there would be no point setting the error.

This is a little bit different than using the `Maybe` monad, where the lack of a value is just Nothing where it's more of a control flow change only. For `Result`, we want the success value, and if that doesn't exist, then have the error value. And kind of similar in spirit to the `Maybe` monad, we don't want to interrogate or start to poke at the `Result` monad and try to grab out the error value if it exists:

```csharp
// Don't do this!

if (result.Value != null) {
  Console.WriteLine(result.Value);
} else {
  Console.WriteLine(result.Error);
}
```

This is kind of a mess, because now we're just back to square one, where we're just treating the `Result` monad as simply a container to hold the success value and the failure value. Monads are not just containers, they're much more than that. You have to use them in a way where they compose together. The monad itself is responsible for delegating that control flow.

> Aside: But wait, my programming language of choice has a `GetUnsafeValue()` on the `Result` monad! They exist as escape hatches, interop, and are typically used in few rare and specific situations. For now, pretend they do not exist.

This is where `Match` comes in.

```csharp
// Match at the boundary: collapse Ok/Err into a single value.
public TResult Match<TResult>(Func<T, TResult> ok, Func<TErr, TResult> err)
{
    if (_isOk)
    {
        return ok(_value);
    }
    else
    {
        return err(_error);
    }
}
```

## **`Match` at the boundary**

With `Result<T, TErr>`, since an error is explicitly specified the **error matters** and you’ll usually want to surface it at the edge (UI, logs, HTTP response). That’s what `Match` is for: it’s the one place you *unwrap* and handle **both** branches explicitly.

*What `Match` guarantees:*

* **Exhaustive by construction.** You must provide handlers for `Ok` and `Err`. There aren't any surprises when a function returns an error, assuming all APIs are written that way. The function signature `Result` indicates you have to handle it (somehow) and forces you to do so, otherwise it's a compile-time error.
* **No invalid states.** In the success handler you only have `T`; in the error handler you only have `TErr`. There’s no way to “peek” at the other branch. There is nothing to peek at, the other value simply doesn't exist.

> **Aside: What’s a “boundary”?**
> A **boundary** is where your program needs to make a decision and *do something*, like update the UI, return a result to a caller, or show an error. Inside your logic, you use `Map` and `Bind` to build up a pipeline. But at the boundary, you need to stop composing and **choose** what to do next. That’s where `Match` comes in: it forces you to handle both the success and the error path clearly. Boundaries are often the outer edges of your app, places like `Main()`, web handlers, or event callbacks, where decisions become actions. This is also where side-effects are run, but we'll go into this in a later part.


**Example, turn a result into a message and perform side effects:**

```csharp
var message =
    AppConfigComposition.LoadAppConfig(cfg).Match(
        ok  => { SaveConfigToCache(ok); UpdateUI(ok); return "Dashboard updated."; },
        err => { ShowError($"Could not build config: {err}"); return "Dashboard not updated."; }
    );

Log(message);
```

**Pure variant, format without side effects:**

```csharp
string ToMessage(Result<AppConfig, string> r) =>
    r.Match(
        ok  => $"Config OK (Mode={ok.Mode}, Retries={ok.MaxRetries})",
        err => $"Config error: {err}"
    );
```

## Composition, composition, composition

Recall that you can compose monads. In this case, say for example the user might provide a config, this could be modelled via Maybe<AppConfig>. Then, we could combine this with Result, which could run computations to do different things if a config is provided, e.g., enable certain features, which themselves could produce errors. The Maybe monad would be responsible for running the rest of the branch; if there is a config, then continue, otherwise, well, there is no config, so skip the subsequent steps.

## Why does this feel so complicated, why are there so many things I need to handle now?

When you start using Result pervasively, it can feel like there are suddenly a lot of errors to handle. It’s not creating more errors, it’s making existing failure cases explicit and putting them where you can see them.

In codebases that rely on exceptions (or nulls), failures are often latent: the happy path reads cleanly, but hidden branches can throw at runtime. If an exception isn’t caught in just the right place, it bubbles up, crashes the program, or triggers framework‑level behavior you didn’t intend. Or, you handle them yourself defensively.

With Result<E, T>, those same possibilities are part of the type. That forces you either to handle them or to propagate them explicitly. Yes, this adds some cognitive overhead. But the trade‑off is fewer surprises and clearer control flow. Instead of hoping everything works, you design for the cases where it might not.

## **In closing**

* **Exceptions**: great at *UI/imperative edges* to abort an operation early and show an error, wrap the whole interaction in one `try/catch`. But inside your core logic, they make error flow implicit and non‑local.
* **Try‑pattern/tuples**: better locality than exceptions, but you’re rebuilding `Result<T, TErr>` without its ergonomics or guarantees.
* **`Result`**: makes failure **part of the type**, nudges you to handle it consciously, and gives you **`Bind`/`Map`** to compose steps and **flows** without boilerplate.
