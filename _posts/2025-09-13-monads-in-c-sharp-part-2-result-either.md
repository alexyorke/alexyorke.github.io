---

title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

In Part 1 you built `Maybe` to transform a value if present, and `Bind` (aka `FlatMap`) to chain steps that may not produce a value. This part keeps that **same shape** but lets the “no value” branch carry **a reason**. We’ll introduce a `Result<T, TErr>`, and walk through real‑world examples (config and sequential API calls).

*If you think in LINQ:* `Map` ≈ `Select`, `Bind`/`FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

**What you’ll build:**

1. Introduce `Result<T, TErr>` (aka `Either`).
2. Apply it to **config parsing** and **sequential API calls**.
   **Mental model:** `Map` ≈ LINQ `Select`; `Bind` ≈ `SelectMany`; use `Match` at the boundary.

> **Language note:** In FP libraries you’ll often see this called **Either** (usually `Either<Err, T>`). Here we name it `Result<T, TErr>` for readability in C#. The principles are the same; the C# version is just more explicit/verbose than languages with built‑in typeclasses and `do`‑notation.

---

## Result (aka Either): when “missing” needs a reason

`Maybe<T>` tells us **whether** a value exists. Sometimes, we need **why** it doesn’t exist. We keep the same straight‑line composition:

* **`Map`**, transform the **success** value
* **`Bind`**, chain a function returning another `Result<...>`

...and add a failure branch that carries an **error**.

Think of it like:

* `Ok(value)` → like `Some(value)`
* `Err(message)` → like `None()`, **but with a reason**

> **Why this matters:** In multi‑step flows (config → parse → validate → use), a single composable shape for expected failures keeps control‑flow linear and avoids repetitive `if (!ok) return;` or broad `try/catch` scaffolding.

---

## Scenario: Parse & validate configuration (pure, in‑memory)

We’ll assume the configuration key/values are in memory (e.g., a `Dictionary<string,string>`). These variants illustrate where `Result<T, TErr>` fits.

> **Framing note (avoid conflation):** The point here isn’t that “.NET is inconsistent.” The BCL deliberately uses *exceptions* for exceptional conditions and 'Try' patterns (`TryParse`, `TryGetValue`) for expected failures. The problem for *composition* is that **mixing shapes** (throwing vs. booleans/nulls/status codes) forces call sites to write glue code. A `Result` gives you a **single, composable shape** for error flow, independent of what the underlying APIs do.

### Example 1: Baseline exceptions (sync, pure)

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

This converts a raw configuration dictionary (e.g., from a file) into a strongly typed `AppConfig`. With exceptions, control jumps to the `catch`; with null or status codes, you must branch explicitly. **Neither shape composes by itself** when you string multiple steps together; the calling code must coordinate the control flow. **We are responsible for managing the control flow via try/catch/return.**

---

### Example 2: Try‑pattern as a tuple

```csharp
public static (bool Success, AppConfig Config, string? Error)
    TryBuildConfig(IReadOnlyDictionary<string, string> cfg)
{
    // Single setting to illustrate the pattern concisely.
    if (!cfg.TryGetValue("MaxRetries", out var text))
    {
        return (false, default, "Missing key: MaxRetries");
    }

    if (!int.TryParse(text, out var retries) || retries is < 0 or > 10)
    {
        return (false, default, $"MaxRetries must be an integer 0-10 (got '{text}').");
    }

    return (true, new AppConfig(retries, [...]), null);
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

## Example 3: The Try/out Pattern

Another approach is to use the **Try** pattern: the function returns a `bool` indicating success, and writes the result to an `out` parameter. On success (`true`), the `out` value contains the result; on failure (`false`), the common convention is to assign a default value (for reference types, typically `null`).

```csharp
public static bool TryBuildPlan_AllTry(
    [NotNullWhen(true)] out RefreshPlan? plan) // non-null when the method returns true
{
    if (TryGetUserConfig(out var cfg)
        && TryComputeJwtExpiry(cfg, out var remaining)
        && TryEnsureMinimumLifetime(remaining, out var p))
    {
        plan = p;
        return true;
    }

    // Assign the out parameter on the failure path (conventionally a default/null for reference types)
    plan = null;
    return false;
}
```

This style composes nicely: the chained `&&` calls short‑circuit, you can thread the `out` variables, and `[NotNullWhen(true)]` tells the compiler’s nullable flow analysis that `plan` is non‑null only when the method returns `true`. That enables warnings if you dereference `plan` on paths where the result wasn’t checked or was `false`.

Although it’s concise and easy to follow, there’s still some ceremony: you must **assign the `out` parameter on every return path** (the language rule), ensure success paths return `true`, and thread the `out` value correctly through your control flow. The typical convention is to set a sensible default (e.g., `null` for reference types) on failure. Although there are IDE warnings if you use the `NotNullWhen` annotation, there's nothing forcing you to check the return value and to use the `out` variable accordingly.

Finally, the `Try` pattern doesn’t convey a failure reason. If you need diagnostics, you can add a secondary `out` (e.g., an error code or message) or provide an exception‑throwing counterpart (like `Parse`) for the detailed case. ([Microsoft Learn][1])

> **Note on analysis limits:** Nullable flow analysis is conservative and attribute‑driven. When it can’t prove a value is non‑null, it **emits a warning** rather than silently missing one; attributes like `NotNullWhen` (and related ones) help the compiler reason more precisely about your APIs. ([Microsoft Learn][1])

[1]: https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/attributes/nullable-analysis "Attributes interpreted by the compiler: Nullable static analysis"

---

## Introducing `Result<T, TErr>`

Below is a minimal `Result<T, TErr>` implementation with `Map` and `Bind`.

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
}
```

> **Key idea:** `Bind` short‑circuits: once you hit `Err`, the error flows through unchanged and downstream steps don’t run. This is the same control‑flow you used with `Maybe`, now with an error attached.

---

## Example: Sequential API calls (auth -> user -> orders)

**Intent:** Compose three dependent calls and return either a **numeric total** or an **error**, still with no side effects.

```csharp
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

    // Collapsed presentation: format success into a string.
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

At some point, you do need to be able to read the error from `Result`, otherwise there’d be no point in having an error.

This is a bit different from the `Maybe` monad. With `Maybe`, the absence of a value is represented by `Nothing`, which serves purely as a control‑flow indicator (no error information). For `Result`, we have an error value to accompany the missing case. Similarly, you should not manually inspect a `Result` to pull out the error (or value) directly, just as you wouldn't with a `Maybe`:

```csharp
// Don't do this!

if (result.Value != null) {
    Console.WriteLine(result.Value);
} else {
    Console.WriteLine(result.Error);
}
```

This is a mess, because now we’re back to square one: treating `Result` as a simple container holding both success and failure, and manually branching. `Monads` are not just containers; they’re meant to be used through their composition methods. The monad itself should handle the control flow so you don’t have to explicitly branch at each step.

**Aside:** But wait, my programming language of choice has a `GetUnsafeValue()` on its `Result` type! Such methods exist as escape hatches or for interop, used only in rare cases. For now, pretend they do not exist.

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

---

## Match at the boundary

With `Result<T, TErr>`, since an error type is explicitly specified, the **error matters**, you’ll usually want to surface it at the edge (UI, logs, HTTP response, etc.). That’s what `Match` is for: it’s where you *unwrap* the result and handle **both** branches explicitly.

*What `Match` guarantees:*

* **Exhaustive by construction.** You must provide handlers for both `Ok` and `Err`. There are no surprises when a function returns an error; the signature `Result<..., TErr>` itself signals that possibility. You’re forced (at compile time) to handle it or propagate it.
* **No invalid states.** In the success handler you only have a `T`; in the error handler you only have a `TErr`. There’s no way to “peek” at the other branch, the other value simply doesn’t exist in that context.

> **Aside: What’s a “boundary”?**
> A **boundary** is where your program needs to make a decision and *do something*, e.g., update the UI, return a result to an external caller, or log an error. Inside your core logic, you use `Map` and `Bind` to build up a pipeline of transformations. But at the boundary, you need to stop composing and **decide** what to do next. That’s where `Match` comes in: it forces you to handle both the success and error paths clearly. Boundaries are often the outer edges of your app (like `Main()`, web request handlers, or event callbacks), where decisions become actions. (These are also the places for side effects, a topic for a later part.)

**Example: turn a result into a message:**

```csharp
string ToMessage(Result<AppConfig, string> r) =>
    r.Match(
        ok  => $"Config OK (Mode={ok.Mode}, Retries={ok.MaxRetries})",
        err => $"Config error: {err}"
    );
```

> **Boundary sketch (HTTP):**
> `return result.Match(Ok, Problem);` – same idea: one place, both branches.

---

## Composition, composition, composition

Let’s compose two independent functions:

* `GetUserConfig` returns an optional `AppConfig` as `Maybe<AppConfig>`
* `ComputeJwtExpiry` takes a config and returns a `Result<TimeSpan,string>` (the remaining `JWT` lifetime or an error).
* Then we add a second step, `EnsureMinimumLifetime`, which **transforms** that `TimeSpan` into a different success type (`RefreshPlan`) or an error, showing that later steps don’t have to keep the exact same `T`.

```csharp
// Assume:
//   Maybe<AppConfig> GetUserConfig();
//   Result<TimeSpan,string> ComputeJwtExpiry(AppConfig cfg);
//   Result<RefreshPlan,string> EnsureMinimumLifetime(TimeSpan remaining);
//   sealed record RefreshPlan(TimeSpan RefreshIn, string Strategy);

var pipeline =
    GetUserConfig()
        .Map(ComputeJwtExpiry)                    // Maybe<Result<TimeSpan,string>>
        .Map(r => r.Bind(EnsureMinimumLifetime)); // Maybe<Result<RefreshPlan,string>> (type changes here)
```

Notice the final type is a `Result` nested inside a `Maybe`. This is a common and powerful pattern! It correctly models a situation where the entire operation might not apply (`Maybe`), and if it does, it can either succeed or fail (`Result`).

The configuration is optional, so `Maybe` controls whether any checks run at all. If there **is** a config, `Map` applies the pure `ComputeJwtExpiry` and yields a `Result` (no exceptions thrown—errors are returned as `Err`). The second `Map` then lifts a `Bind` that converts a successful `TimeSpan` into a different success type (`RefreshPlan`). We’re **not** calling `Match` here; the pipeline stays composable as a `Maybe<Result<RefreshPlan,string>>`, and you can handle it once at the boundary later.

---

## Why does this feel so complicated?

When you start using `Result<T, TErr>` pervasively, it might feel like there are suddenly *many* errors to handle. It’s not that you created more failure cases, you’ve simply made existing ones explicit and put them where you can see them.

In codebases that rely on exceptions (or nulls), failures are often latent: the happy path reads cleanly, but hidden branches can throw at runtime. If an exception isn’t caught in just the right place, it bubbles up, crashes the program, or triggers framework‑level behavior you didn’t intend. (Or you end up writing defensive `try/catch` blocks around everything.)

With `Result<T, TErr>`, those same possibilities are part of the type. That forces you either to handle them or to propagate them explicitly. Yes, this adds some cognitive overhead, but the trade‑off is fewer surprises and clearer control flow. Instead of hoping everything works, you design for the cases where it might not.

---

## Takeaways

* Keep composition **linear** with `Map`/`Bind`; let `Err` short‑circuit.
* Use `Match` **at the boundary** to turn a `Result` into effects or UI/HTTP responses.
* Prefer `Result` when you need **a reason** for expected failures; keep exceptions for exceptional conditions.
* In C#, this is a small amount of **intentional boilerplate** to get the same clarity benefits you’d see in FP‑first languages.

Part 3 coming soon.
