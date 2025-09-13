---

title: "List is a monad (part 2)"
date: 2025-06-30
---

# **Monads in C# (Part 2): Result (aka Either) with practical, everyday examples**

In Part 1 you built `Maybe` to transform a value if present; `Bind` (aka `FlatMap`) to chain steps that may not produce a value. This part keeps that **same shape** but lets the “no value” branch carry **a reason**. We’ll finish the `Maybe` monad from Part 1, introduce a `Result<T, TErr>`, and walk through real‑world examples (config, files/JSON, and sequential API calls).

*If you think in LINQ:* `Map` ≈ `Select`, `Bind`/`FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

**What you’ll build:**

1. Finish `Maybe<T>` with `Map`/`Bind`.
2. Introduce `Result<T, TErr>` (aka Either).
3. Apply it to **config parsing**, **file+JSON**, and **sequential API calls**.
   **Mental model:** `Map` ≈ LINQ `Select`; `Bind` ≈ `SelectMany`; use `Match` at the boundary.

---

## **Closing the loop on `Maybe`**

We’re making a few changes to the `Maybe` monad to give it a more official, ergonomic API. First, instead of letting callers construct the underlying representation directly, we’ll expose two *factory methods*: `Some` and `None`. Second, we’ll generalize map: instead of only mapping over integers, the monad will be generic so it can map any type. Finally, we’ll standardize the name to `Maybe<T>`. Together, these tweaks clean things up and make the monad easier to use across more scenarios.

```diff
- public class MaybeMonad {
-     private int value;
-     private bool hasValue;
+ public sealed class Maybe<T>
+ {
+     private readonly bool _has;
+     private readonly T _value;

-     public MaybeMonad(int value) {
-         this.value = value;
-         this.hasValue = true;
-     }
+     private Maybe(T value)
+     {
+         _has = true;
+         _value = value;
+     }

-     public MaybeMonad() {
-
-     }
+     private Maybe()
+     {
+         _has = false;
+         _value = default(T);
+     }
+     public static Maybe<T> Some(T value) => new Maybe<T>(value);
+     public static Maybe<T> None() => new Maybe<T>();

-     public MaybeMonad Map(Func<int, int> func) {
-         if (hasValue) {
-             return new MaybeMonad(func(value));
-         }
-         return this;
-     }
- }
+     public Maybe<U> Map<U>(Func<T, U> f) =>
+         _has ? Maybe<U>.Some(f(_value)) : Maybe<U>.None();
+
+     public Maybe<U> Bind<U>(Func<T, Maybe<U>> f) => // aka FlatMap
+         _has ? f(_value) : Maybe<U>.None();
+ }
```

To wrap up **`Maybe`**: it’s perfect when you only need to model “value or no value.” Often, we also need to know *why* a value is missing (not found, invalid input, business‑rule violation). **`Maybe`** can’t carry that reason.

---

## **Result (aka Either): when “missing” needs a reason**

`Maybe<T>` tells us **whether** a value exists. Sometimes, we need **why** it doesn’t exist. We keep the same straight‑line composition:

* **`Map`** — transform the **success** value
* **`Bind`** — chain a function returning another `Result<…>`

…and add a failure branch that carries an **error**.

Think of it like:

* `Ok(value)` → like `Some(value)`
* `Err(message)` → like `None()`, **but with a reason**

---

## **Scenario: Parse & validate configuration (pure, in‑memory)**

We’ll assume the configuration key/values are in memory (e.g., a `Dictionary<string,string>`). These variants illustrate where `Result<T, TErr>` fits.

### **Example 1 — Baseline exceptions (sync, pure)**

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
    }
    Log("Dashboard updated.");
}
```

A common step is to convert a raw configuration dictionary (e.g., from a file) into a strongly typed `AppConfig`. When the input is invalid, typical options are to throw an exception or return `null`. Each affects control flow differently: exceptions transfer execution to a `catch` block, while `null` results require checks and possible early returns. To use the parsed config outside a `try/catch`, it’s often declared before the `try`, which means subsequent code proceeds as if parsing succeeded. If a `return` is omitted in a `catch`, an exception is swallowed, or a check is missed, execution may continue with an uninitialized or invalid configuration. Repeated across settings, this pattern can lead to duplicated error-handling logic. Also, it is not clear how BuildConfigBasic will fail, i.e., if it'll throw an exception, return null, etc., although it can be documented, there is nothing at compile time that enforces a particular way to use this.

---

### **Example 2 — Try‑pattern as a tuple (fast‑fail without throwing on content)**

```csharp
public static (bool Success, AppConfig Config, string? Error)
    TryBuildConfig(IReadOnlyDictionary<string, string> cfg)
{
    if (!cfg.TryGetValue("MaxRetries", out var maxRetriesText))
        return (false, default!, "Missing key: MaxRetries");
    if (!int.TryParse(maxRetriesText, out var maxRetries))
        return (false, default!, $"Invalid integer for MaxRetries: \"{maxRetriesText}\"");
    if (maxRetries is < 0 or > 10)
        return (false, default!, "MaxRetries must be between 0 and 10.");

    if (!cfg.TryGetValue("TimeoutSeconds", out var timeoutText))
        return (false, default!, "Missing key: TimeoutSeconds");
    if (!int.TryParse(timeoutText, out var timeoutSeconds))
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

This reads linearly and avoids throwing for expected input errors, but as soon as you chain multiple steps, you create repetitive `if (!ok)` plumbing—an ad‑hoc `Result`. There's also nothing enforcing success to be true and the error to always be null, which could be confusing to handle from the caller's perspective. I can also still use the AppConfig, even though it may not be initialized or could be null.

---

## Scenario: File + JSON (pure, deterministic “source”)

**Intent:** Compose a config from a deterministic source (no I/O talk here), returning only `Result<AppConfig, string>`.

We’ll use an existing `Result` abstraction (as found in many languages and libraries) to focus on composition rather than re-implementing plumbing. The goal is to build an `AppConfig` from a deterministic source (e.g., a read-only dictionary). For concreteness, we’ll briefly show how the internal validate/parse step might work, though callers don’t need those details.

Instead of throwing or returning null (or other behavior), functions return `Result`: `Ok(value)` on success or `Err(error)` on failure (using `Ok/Err` to avoid left/right terminology). This keeps control flow predictable: successful values flow through `Map`/`FlatMap`, while failures short-circuit and carry the error without exceptions or null checks. Because `Result` has a common shape, APIs that return it compose naturally regardless of their internals. At the boundary—typically once—the caller handles the final outcome and can inspect any error produced by the pipeline. The example below illustrates this pattern.

You could write another function that takes in an AppConfig, returns a Result<AppConfig, string> and put it in this flatMap pipeline below, and it'll work, error handling and all. You don't need to check if it's null, or has a boolean success value, or throws an exception and manually return. This shows the power of mondaic composition: since this control-flow logic has been "hoisted", it allows multiple functions to seamlessly work together.

```csharp
using System;
using System.Collections.Generic;

// Domain
public sealed class AppConfig
{
    public int MaxRetries { get; }
    public int TimeoutSeconds { get; }
    public Mode Mode { get; }

    public AppConfig(int maxRetries, int timeoutSeconds, Mode mode)
    {
        MaxRetries = maxRetries;
        TimeoutSeconds = timeoutSeconds;
        Mode = mode;
    }
}

public enum Mode
{
    Development,
    Staging,
    Production
}

// --- Assumed existing Result-returning functions (provided elsewhere) ---
// Result<string, string> GetJson();
// Result<Dictionary<string, string>, string> ParseJsonToDict(string json);
// Result<int, string> GetIntInRange(Dictionary<string, string> d, string key, int min, int max);
// Result<TEnum, string> GetEnum<TEnum>(Dictionary<string, string> d, string key) where TEnum : struct, Enum;

// Optional validation (pure)
public static class AppConfigValidation
{
    public static Result<AppConfig, string> Validate(AppConfig cfg)
    {
        if (cfg.MaxRetries < 0 || cfg.MaxRetries > 10)
        {
            return Result<AppConfig, string>.Err("MaxRetries must be between 0 and 10.");
        }

        if (cfg.TimeoutSeconds < 1 || cfg.TimeoutSeconds > 300)
        {
            return Result<AppConfig, string>.Err("TimeoutSeconds must be between 1 and 300.");
        }

        return Result<AppConfig, string>.Ok(cfg);
    }
}

// Entry point for this scenario: compose a config from a deterministic source.
// No branching here; just Map/Bind and return Result<AppConfig, string>.
public static class AppConfigComposition
{
    public static Result<AppConfig, string> LoadAppConfig()
    {
        return GetJson()
            .Bind(json => ParseJsonToDict(json))
            .Bind(dict => GetIntInRange(dict, "MaxRetries", 0, 10)
                .Bind(max => GetIntInRange(dict, "TimeoutSeconds", 1, 300)
                    .Bind(timeout => GetEnum<Mode>(dict, "Mode")
                        .Map(mode => new AppConfig(max, timeout, mode)))))
            .Bind(cfg => AppConfigValidation.Validate(cfg));
    }
}
```

---

## Scenario: Sequential API calls (auth → user → orders)

**Intent:** Compose three dependent calls and return either a **numeric total** or an **error**—still no side effects.

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
        // There is no error formatting here because we haven't introduced MapError/Recover.
        // If any step fails, the Err branch is returned as-is.
    }
}
```

---

## Introducing `Result<T, TErr>`

Below is a complete `Result<T, TErr>` implementation.

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
            _error = default!;
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
        // Mirrors Maybe<T>.Map<U>(Func<T, U>).
        public Result<U, TErr> Map<U>(Func<T, U> f)
        {
            if (_isOk)
            {
                return Result<U, TErr>.Ok(f(_value));
            }

            return Result<U, TErr>.Err(_error);
        }

        // Bind (aka FlatMap): chain a function returning Result.
        // Mirrors Maybe<T>.Bind<U>(Func<T, Maybe<U>>) with the same control-flow shape.
        public Result<U, TErr> FlatMap<U>(Func<T, Result<U, TErr>> next)
        {
            if (_isOk)
            {
                return next(_value);
            }

            return Result<U, TErr>.Err(_error);
        }
    }
```

---

## **The punchline (and when exceptions are fine)**

* **Exceptions**: great at *UI/imperative edges* to abort an operation early and show an error—wrap the whole interaction in one `try/catch`. But inside your core logic, they make error flow implicit and non‑local.
* **Try‑pattern/tuples**: better locality than exceptions, but you’re rebuilding `Result<T, TErr>` without its ergonomics.
* **`Result`**: makes failure **part of the type**, forces conscious handling, and gives you **`Bind`/`Map`** to compose steps and files without boilerplate.
