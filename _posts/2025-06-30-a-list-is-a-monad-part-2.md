---
title: "A list is a monad (part 2)"
date: 2025-06-30
---

# **Monads in C\# (Part 2): Result (aka Either) with practical, everyday examples**

In Part 1 you built `Maybe` to transform a value if present; `FlatMap` (bind) to chain steps that may not produce a value. This part keeps that **same shape** but lets the “no value” branch carry **a reason**. We’ll finish the `Maybe` monad from Part 1, introduce a `Result<T,TErr>`, walk through real‑world examples (files/JSON, sequential API calls, and validation).

*If you think in LINQ:* `Map` ≈ `Select`, `FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

**What you’ll build:**

1.  Finish `Maybe<T>` with `Map`/`FlatMap`.
2.  Introduce `Result<T, TErr>` (aka Either).
3.  Apply it to **config parsing**, **file+JSON**, and **sequential API calls**.
    **Mental model:** `Map` ≈ LINQ `Select`; `FlatMap`/`Bind` ≈ `SelectMany`; use `Match` at the boundary.

## **Closing the loop on `Maybe` — proper monad, minimal diff**

We’re making a few changes to the Maybe monad to give it a more official, ergonomic API. First, instead of letting callers construct the underlying representation directly, we’ll expose two constructors: Some and None. Second, we’ll generalize map: instead of only mapping over integers, the monad will be generic so it can map any type. Finally, we’ll standardize the name to Maybe (not “MaybeMonad”), which matches how monads are typically named in functional programming (e.g., Maybe, Result). Together, these tweaks clean things up and make the monad easier to use across more scenarios.

```diff
- public class MaybeMonad {
-     private int value;
-     private bool hasValue;
+ public sealed class MaybeMonad<T>
+ {
+     private readonly bool _has;
+     private readonly T _value;

-     public MaybeMonad(int value) {
-         this.value = value;
-         this.hasValue = true;
-     }
+     private MaybeMonad(T value)
+     {
+         _has = true;
+         _value = value;
+     }

-     public MaybeMonad() {
-
-     }
+     private MaybeMonad()
+     {
+         _has = false;
+         _value = default(T);
+     }
+     public static MaybeMonad<T> Some(T value)
+     {
+         return new MaybeMonad<T>(value);
+     }
+
+     public static MaybeMonad<T> None()
+     {
+         return new MaybeMonad<T>();
+     }

-     public MaybeMonad Map(Func<int, int> func) {
-         if (hasValue) {
-             return new MaybeMonad(func(value));
-         }
-         return this;
-     }
- }
+     public MaybeMonad<U> Map<U>(Func<T, U> f)
+     {
+         if (_has)
+         {
+             U mapped = f(_value);
+             return MaybeMonad<U>.Some(mapped);
+         }
+         else
+         {
+             return MaybeMonad<U>.None();
+         }
+     }
+
+     public MaybeMonad<U> FlatMap<U>(Func<T, MaybeMonad<U>> f) // aka Bind
+     {
+         if (_has)
+         {
+             return f(_value);
+         }
+         else
+         {
+             return MaybeMonad<U>.None();
+         }
+     }
+ }
```

To wrap up the **Maybe monad**: it’s perfect when you only need to model “value or no value.” Sometimes, we often need to know *why* a value is missing. Was the ID not found in the database? Was the input malformed or out of range? Did a file read fail? Was a business rule violated? **Maybe** can’t carry that reason.

That’s where the **Result** (a.k.a. **Either**) **monad** fits. It’s like the Maybe monad, except it allows setting an error TErr instead of just None for the Maybe monad. Result<T, TErr> is a practical generalization of Maybe<T> (aka Option): use Maybe<T> when “missing is fine,” and use Result<T, TErr> when you need a reason for failure.

---

## **Result (aka Either): when “missing” needs a reason**

`Maybe<T>` tells us **whether** a value exists. Real code often needs **why** it doesn’t (invalid input, “not found,” rule failed). We keep the same straight‑line composition:

*   **`Map`** — transform the **success** value
*   **`FlatMap`** — chain a function returning another `Result<…>`

…and add a failure branch that carries an **error**.

Think of it like:

*   `Ok(value)` ⇢ like `Some(value)`
*   `Error(message)` ⇢ like `None()`, **but with a reason**

## Introducing Result\<T, Err\>

Below is the implementation for a Result\<T,Err\> monad. I’ve added the differences between the Maybe monad in the comments.

```csharp
public sealed class Result<T, TErr>
{
    // Like Maybe: keep a flag indicating which branch we are on.
    private readonly bool _isOk;

    // Like Maybe's 'value' field, but generic.
    private readonly T _value;

    // NEW vs Maybe: carry an error value for the failure branch.
    private readonly TErr _error;

    // Success constructor (like Maybe's "Some")
    private Result(T value)
    {
        _isOk = true;
        _value = value;
        _error = default; // unused when success
    }

    // Error constructor (like Maybe's "None", but with a reason)
    private Result(TErr error)
    {
        _isOk = false;
        _value = default; // unused when error
        _error = error;
    }

    // "Constructors" users call (match Maybe's two ways to construct)
    public static Result<T, TErr> Ok(T value)
    {
        return new Result<T, TErr>(value);
    }

    public static Result<T, TErr> Err(TErr error)
    {
        return new Result<T, TErr>(error);
    }

    // Map: same idea as Maybe.Map — transform the success value, pass errors through unchanged
    public Result<U, TErr> Map<U>(Func<T, U> f)
    {
        if (_isOk)
        {
            return Result<U, TErr>.Ok(f(_value));
        }
        return Result<U, TErr>.Err(_error);
    }

    // Bind (aka FlatMap): same idea as Maybe.Bind — chain another Result-producing function
    public Result<U, TErr> Bind<U>(Func<T, Result<U, TErr>> next)
    {
        if (_isOk)
        {
            return next(_value);
        }
        return Result<U, TErr>.Err(_error);
    }

    // Match: NEW vs Maybe example — handle both branches once, when leaving the pipeline
    public R Match<R>(Func<T, R> ok, Func<TErr, R> err)
    {
        if (_isOk)
        {
            return ok(_value);
        }
        return err(_error);
    }
}
```

### **Quick mental model for `Match` (and how it differs from `Map`)**

*   Use **`Map`/`FlatMap`** while you’re still **composing** the success path. They run only on success and keep you inside `Result<…>`.
*   Use **`Match`** once at the **boundary** to produce a final value or effect from either branch (render a message, choose an HTTP status, pick a fallback). `Match` is where you say “if success → do this, if error → do that.”

**Decision checklist**

*   Use **`Result<T,TErr>`** when failure is **expected and meaningful to the caller** (invalid input, not found, rule failed) **and** you want to compose more steps.
*   Use **`Maybe<T>`** when all you need to know is **presence/absence**, not the reason.

### **Scenario: Parse & validate configuration (pure, in‑memory)**

We’ll assume the configuration key/values are already in memory (e.g., a `Dictionary<string,string>`). The following code examples aren’t incorrect; rather, I’m showing how `Result<T, TErr>` can be applied.

---

### **Example 1 — Minimal & idiomatic exceptions (sync, pure)**

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
        // Any missing/invalid field will throw **here**
        var app = BuildConfigBasic(cfg);
        SaveConfigToCache(app);  // impure vignette is fine
        UpdateUI(app);
    }
    catch (Exception ex) // KeyNotFoundException, FormatException, ArgumentException, ...
    {
        ShowError($"Could not build config: {ex.Message}");
        return; // non-local jump; everything below is skipped
    }
    Log("Dashboard updated.");
}
```

With multiple fields, exceptions can arise mid‑construction, so the caller must wrap the entire operation. That’s a non‑local jump in control flow: error handling is necessarily out‑of‑line.

---

### **Example 2 — Best practical exception patterns**

**“Throw on failure” core (explicit checks, still exceptions):**

```csharp
public static AppConfig BuildConfigOrThrow(IReadOnlyDictionary<string, string> cfg)
{
    if (!cfg.TryGetValue("MaxRetries", out var maxRetriesText))
        throw new KeyNotFoundException("Missing key: MaxRetries");
    if (!int.TryParse(maxRetriesText, out var maxRetries))
        throw new FormatException($"Invalid integer for MaxRetries: \"{maxRetriesText}\"");
    if (maxRetries is < 0 or > 10)
        throw new FormatException("MaxRetries must be between 0 and 10.");

    if (!cfg.TryGetValue("TimeoutSeconds", out var timeoutText))
        throw new KeyNotFoundException("Missing key: TimeoutSeconds");
    if (!int.TryParse(timeoutText, out var timeoutSeconds))
        throw new FormatException($"Invalid integer for TimeoutSeconds: \"{timeoutText}\"");
    if (timeoutSeconds is < 1 or > 300)
        throw new FormatException("TimeoutSeconds must be between 1 and 300.");

    if (!cfg.TryGetValue("Mode", out var modeText))
        throw new KeyNotFoundException("Missing key: Mode");
    if (!Enum.TryParse<Mode>(modeText, ignoreCase: true, out var mode))
        throw new FormatException($"Invalid Mode: \"{modeText}\" (Development|Staging|Production)");

    return new AppConfig(maxRetries, timeoutSeconds, mode);
}
```

Caller still needs a top‑level try/catch (as in Tier 1), because faults can occur mid‑construction.
**Point:** We kept the happy path straight, but the error path remains implicit and non‑local.

---

### **Example 3 — Try‑pattern as a tuple (fast‑fail without throwing on content)**

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

This avoids throwing for expected input errors and reads linearly. But you’ve invented an ad‑hoc Result: `(bool, T, string?)`. As soon as you chain multiple steps/sections, you’ll write repetitive `if (!ok) return;` plumbing—manual composition work the Result pattern eliminates.

---

### **Example 4 — Composition pressure (multiple configs)**

```csharp
try
{
    // e.g., three independent config sources we need to validate
    var a = BuildConfigOrThrow(cfgA);
    var b = BuildConfigOrThrow(cfgB);
    var c = BuildConfigOrThrow(cfgC);

    // Some combined metric (purely illustrative)
    var globalMinTimeout = Math.Min(a.TimeoutSeconds, Math.Min(b.TimeoutSeconds, c.TimeoutSeconds));
    UpdateUIWithCombined(a, b, c, globalMinTimeout);
}
catch (Exception ex)
{
    // Which config? Which field? You need more structure to know.
    ShowError(ex.Message);
}
```

**Try‑tuple (2B):**

```csharp
var r1 = TryBuildConfig(cfgA);
if (!r1.Success) { ShowError(r1.Error!); return; }
var r2 = TryBuildConfig(cfgB);
if (!r2.Success) { ShowError(r2.Error!); return; }
var r3 = TryBuildConfig(cfgC);
if (!r3.Success) { ShowError(r3.Error!); return; }

var globalMinTimeout = Math.Min(r1.Config.TimeoutSeconds, Math.Min(r2.Config.TimeoutSeconds, r3.Config.TimeoutSeconds));
UpdateUIWithCombined(r1.Config, r2.Config, r3.Config, globalMinTimeout);```

You can “optimize” with an array of tuples and find the first failure—but that’s just a hand‑rolled list of Results followed by a manual fold.

---

### **Interlude: C‑style error codes (why Result \> raw codes)**

C (and similar) returns error codes/sentinels:

```c
FILE* f = fopen("data.txt", "r");
if (!f) return ERR_OPEN;      // easy to forget to check
size_t n = fread(buf, 1, sz, f);
if (n < sz && ferror(f)) return ERR_READ;
```

Problems: callers can forget checks; propagation is manual and repetitive; composition is awkward.

---

### **Example 5 — Result (assume helpers exist)**

**Assume:**

*   `FromDict(cfg) : Result<IReadOnlyDictionary<string,string>, ConfigError>`
*   `GetIntInRange(cfg, key, min, max) : Result<int, ConfigError>`
*   `GetEnum<TEnum>(cfg, key) : Result<TEnum, ConfigError>`
*   `Ok(value)` constructs a success; `.Bind(...)` chains; `.Map(...)` transforms success.

**Error type:**

```csharp
public abstract record ConfigError
{
    public sealed record Missing(string Key) : ConfigError;
    public sealed record Invalid(string Key, string Message) : ConfigError;
}
```

**Single config (pure, composable):**

```csharp
public static Result<AppConfig, ConfigError> BuildConfigResult(IReadOnlyDictionary<string, string> cfg) =>
    FromDict(cfg)                                   // Result<dict>
        .Bind(d => GetIntInRange(d, "MaxRetries", 0, 10)
        .Bind(max => GetIntInRange(d, "TimeoutSeconds", 1, 300)
        .Bind(timeout => GetEnum<Mode>(d, "Mode")
        .Map(mode => new AppConfig(max, timeout, mode)))));
```

**Multiple configs (simple & explicit):**

```csharp
var a = BuildConfigResult(cfgA);
var b = BuildConfigResult(cfgB);
var c = BuildConfigResult(cfgC);

static Result<int, ConfigError> CombineMinTimeout(
    Result<AppConfig, ConfigError> x,
    Result<AppConfig, ConfigError> y) =>
    x.Bind(xv => y.Map(yv => Math.Min(xv.TimeoutSeconds, yv.TimeoutSeconds)));

var minAB = CombineMinTimeout(a, b);
var minABC = minAB.Bind(min => c.Map(z => Math.Min(min, z.TimeoutSeconds)));

// Call site:
Console.WriteLine(minABC.IsSuccess
    ? $"GlobalMinTimeout={minABC.Value}"
    : $"Error: {minABC.Error}");
```

**Or via LINQ:**

```csharp
// To enable LINQ query syntax, you'd add:
// public Result<U, E> Select<U>(Func<T, U> f) => Map(f);
// public Result<V, E> SelectMany<U, V>(Func<T, Result<U, E>> bind, Func<T, U, V> project) => ...
var globalMinTimeout =
    from A in BuildConfigResult(cfgA)
    from B in BuildConfigResult(cfgB)
    from C in BuildConfigResult(cfgC)
    select Math.Min(A.TimeoutSeconds, Math.Min(B.TimeoutSeconds, C.TimeoutSeconds));
```

**What changed:**
Success path stays flat; failure path is explicit and typed.
Composition is declarative (combine `Result`s), not repetitive `if (!ok)` scaffolding.
No non‑local jumps; no hidden second exit.

---

## **The punchline (and when exceptions are fine)**

*   **Exceptions**: great at *UI/imperative edges* to abort an operation early and show an error—wrap the whole interaction in one `try/catch`. But inside your core logic, they make error flow implicit and non‑local.
*   **Try‑pattern/tuples**: better locality than exceptions, but you’re rebuilding `Result<T,TErr>` without its ergonomics.
*   **Result**: makes failure **part of the type**, forces conscious handling, and gives you **Bind/Map** to compose steps and files without boilerplate.
```
