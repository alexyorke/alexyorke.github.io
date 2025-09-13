---
title: "List is a monad (part 2)"
date: 2025-06-30
---

# **Monads in C# (Part 2): Result (aka Either) with practical, everyday examples**

In Part 1 you built `Maybe` to transform a value if present; `Bind` (aka `FlatMap`) to chain steps that may not produce a value. This part keeps that **same shape** but lets the “no value” branch carry **a reason**. We’ll finish the `Maybe` monad from Part 1, introduce a `Result<T, TErr>`, and walk through real‑world examples (files/JSON, sequential API calls, and validation).

*If you think in LINQ:* `Map` ≈ `Select`, `Bind`/`FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

**What you’ll build:**

1. Finish `Maybe<T>` with `Map`/`Bind`.
2. Introduce `Result<T, TErr>` (aka Either).
3. Apply it to **config parsing**, **file+JSON**, and **sequential API calls**.
   **Mental model:** `Map` ≈ LINQ `Select`; `Bind` ≈ `SelectMany`; use `Match` at the boundary.
---

## **Closing the loop on `Maybe`**

We’re making a few changes to the `Maybe` monad to give it a more official, ergonomic API. First, instead of letting callers construct the underlying representation directly, we’ll expose two *factory methods*: `Some` and `None`. Second, we’ll generalize map: instead of only mapping over integers, the monad will be generic so it can map any type. Finally, we’ll standardize the name to `Maybe<T>` (not “`MaybeMonad`”), which matches how monads are typically named in functional programming (e.g., `Maybe`, `Result`). Together, these tweaks clean things up and make the monad easier to use across more scenarios.

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

To wrap up the **`Maybe`** monad: it’s perfect when you only need to model “value or no value.” Often, we also need to know *why* a value is missing. Was the ID not found? Was the input malformed or out of range? Did a file read fail? Was a business rule violated? **`Maybe`** can’t carry that reason.

That’s where the **`Result`** (a.k.a. **Either**) **monad** fits. It’s like `Maybe`, except it allows setting an error `TErr` instead of just `None`. `Result<T, TErr>` is a practical generalization of `Maybe<T>` (aka Option): use `Maybe<T>` when “missing is fine,” and use `Result<T, TErr>` when you need a **reason** for failure.

---

## **Result (aka Either): when “missing” needs a reason**

`Maybe<T>` tells us **whether** a value exists. Sometimes, we need need **why** it doesn’t exist (invalid input, “not found,” rule failed). We keep the same straight‑line composition:

* **`Map`** — transform the **success** value
* **`flatMap`** — chain a function returning another `Result<…>`

…and add a failure branch that carries an **error**.

Think of it like:

* `Ok(value)` -> like `Some(value)`
* `Err(message)` -> like `None()`, **but with a reason**

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

### **Quick mental model for `Match` (and how it differs from `Map`)**

* Use **`Map`/`Bind`** while you’re still **composing** the success path. They run only on success and keep you inside `Result<…>`.
* Use **`Match`** once at the **boundary** to produce a final value or effect from either branch (render a message, choose an HTTP status, pick a fallback). `Match` is where you say “if success → do this, if error → do that.”

**Decision checklist**

* Use **`Result<T, TErr>`** when failure is **expected and meaningful to the caller** (invalid input, not found, rule failed) **and** you want to compose more steps.
* Use **`Maybe<T>`** when all you need to know is **presence/absence**, not the reason.

---

## **Scenario: Parse & validate configuration (pure, in‑memory)**

We’ll assume the configuration key/values are already in memory (e.g., a `Dictionary<string,string>`). The following code examples aren’t incorrect; rather, they illustrate where `Result<T, TErr>` fits.

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

This avoids throwing for expected input errors and reads linearly. But you’ve invented an ad‑hoc `Result`: `(bool, T, string?)`. As soon as you chain multiple steps/sections, you’ll write repetitive `if (!ok) return;` plumbing—manual composition work the `Result` pattern eliminates.

---

### **Example 3 — Composition pressure (multiple configs)**

```csharp
try
{
    // e.g., three independent config sources we need to validate
    var a = BuildConfigBasic(cfgA);
    var b = BuildConfigBasic(cfgB);
    var c = BuildConfigBasic(cfgC);

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

**Try‑tuple variant:**

```csharp
var r1 = TryBuildConfig(cfgA);
if (!r1.Success) { ShowError(r1.Error!); return; }

var r2 = TryBuildConfig(cfgB);
if (!r2.Success) { ShowError(r2.Error!); return; }

var r3 = TryBuildConfig(cfgC);
if (!r3.Success) { ShowError(r3.Error!); return; }

var globalMinTimeout =
    Math.Min(r1.Config.TimeoutSeconds, Math.Min(r2.Config.TimeoutSeconds, r3.Config.TimeoutSeconds));

UpdateUIWithCombined(r1.Config, r2.Config, r3.Config, globalMinTimeout);
```

You can “optimize” with an array of tuples and find the first failure—but that’s just a hand‑rolled list of `Result`s followed by a manual fold.

> **Aside — Why not raw error codes?**
> C‑style APIs return error codes/sentinels, making checks easy to forget and composition awkward:
>
> ```c
> FILE* f = fopen("data.txt", "r");
> if (!f) return ERR_OPEN;
> size_t n = fread(buf, 1, sz, f);
> if (n < sz && ferror(f)) return ERR_READ;
> ```
>
> `Result` encodes the branch in the type and composes.

---

### **Example 4 — Result (assume helpers exist)**

**Assume:**

* `FromDict(cfg) : Result<IReadOnlyDictionary<string,string>, ConfigError>`
* `GetIntInRange(cfg, key, min, max) : Result<int, ConfigError>`
* `GetEnum<TEnum>(cfg, key) : Result<TEnum, ConfigError>`
* `Ok(value)` constructs a success; `.Bind(...)` chains; `.Map(...)` transforms success.

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
public static Result<AppConfig, ConfigError> BuildConfigResult(
    IReadOnlyDictionary<string, string> cfg) =>
    FromDict(cfg)
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

var minAB  = CombineMinTimeout(a, b);
var minABC = minAB.Bind(min => c.Map(z => Math.Min(min, z.TimeoutSeconds)));

// Call site:
Console.WriteLine(minABC.IsSuccess
    ? $"GlobalMinTimeout={minABC.Value}"
    : $"Error: {minABC.Error}");
```

**Or via LINQ:**

```csharp
// To enable LINQ query syntax, you'd add:
/// public Result<U, E> Select<U>(Func<T, U> f) => Map(f);
/// public Result<V, E> SelectMany<U, V>(Func<T, Result<U, E>> bind, Func<T, U, V> project) => ...

var globalMinTimeout =
    from A in BuildConfigResult(cfgA)
    from B in BuildConfigResult(cfgB)
    from C in BuildConfigResult(cfgC)
    select Math.Min(A.TimeoutSeconds, Math.Min(B.TimeoutSeconds, C.TimeoutSeconds));
```

**What changed:**

* Success path stays flat; failure path is explicit and typed.
* Composition is declarative (combine `Result`s), not repetitive `if (!ok)` scaffolding.
* No non‑local jumps; no hidden second exit.

---

## **Scenario: File + JSON (sync)**

```csharp
public static Result<string, string> ReadAllText(string path) =>
    File.Exists(path)
        ? Result<string, string>.Ok(File.ReadAllText(path))
        : Result<string, string>.Err($"Missing file: {path}");

public static Result<T, string> ParseJson<T>(string json)
{
    try { return Result<T, string>.Ok(System.Text.Json.JsonSerializer.Deserialize<T>(json)!); }
    catch (Exception ex) { return Result<T, string>.Err($"JSON parse error: {ex.Message}"); }
}

public static Result<AppConfig, string> LoadConfigFromJsonFile(string path) =>
    ReadAllText(path)
        .Bind(ParseJson<Dictionary<string,string>>)
        .Bind(d => BuildConfigResult(d)); // reuse the Result-based config builder above

// Boundary:
LoadConfigFromJsonFile("appsettings.json").Match(
    ok: cfg => { UpdateUI(cfg); return 0; },
    err: msg => { ShowError(msg); return 1; });
```

---

## **Scenario: Sequential API calls (auth → user → orders)**

```csharp
public record Token(string Value);
public record User(string Id);
public record Order(string Id, decimal Amount);

public static Result<Token, string> GetToken() =>
    Result<Token, string>.Ok(new Token("abc"));

public static Result<User, string> GetUser(Token t) =>
    t.Value == "abc" ? Result<User, string>.Ok(new User("u-1"))
                     : Result<User, string>.Err("Unauthorized");

public static Result<IReadOnlyList<Order>, string> GetOrders(User u) =>
    Result<IReadOnlyList<Order>, string>.Ok(new[] { new Order("o-1", 42m) });

public static Result<decimal, string> GetTotal() =>
    GetToken().Bind(GetUser).Bind(GetOrders).Map(os => os.Sum(o => o.Amount));

// Boundary:
Console.WriteLine(
    GetTotal().Match(
        ok: total => $"Total: {total:C}",
        err: e     => $"Error: {e}"));
```

---

## **The punchline (and when exceptions are fine)**

* **Exceptions**: great at *UI/imperative edges* to abort an operation early and show an error—wrap the whole interaction in one `try/catch`. But inside your core logic, they make error flow implicit and non‑local.
* **Try‑pattern/tuples**: better locality than exceptions, but you’re rebuilding `Result<T, TErr>` without its ergonomics.
* **`Result`**: makes failure **part of the type**, forces conscious handling, and gives you **`Bind`/`Map`** to compose steps and files without boilerplate.
