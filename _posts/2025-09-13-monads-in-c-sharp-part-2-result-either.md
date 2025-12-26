---
title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
description: "Build a small Result type in C# and use Map/Bind/Match to compose fail-fast workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In **Part 1**, we used `List<T>` to contrast `Map` vs `Bind` (aka `FlatMap`), and built `Maybe<T>` to chain optional steps.

The Result monad allows you to represent a computation's outcome as success or failure and to sequence computations so failures propagate until handled.

This transforms error handling from implicit control flow into an explicit return value. This allows errors to flow linearly, avoiding implicit throws and verbose defensive checking.

In practice, `Result` is usually **success-biased**: `Map`/`Bind` operate on the success value and propagate the error unchanged.

This turns error handling into an explicit value, so workflows stay linear and composable without hidden stack unwinding.

It’s like `Maybe<T>`, except the failure case carries a typed reason instead of just “no value”.

#### The Problem: Explicitness vs. Readability

In everyday C#, you tend to end up in one of two styles: rely on **Implicit Control Flow** (exceptions) or write **Verbose Validation** (guard clauses).

**Option A: Implicit Control Flow (Exceptions)**
This code is concise, but the method signature doesn't tell you what can go wrong. `DeactivateUser` returns `void`, yet it can throw parsing exceptions (`ArgumentNullException` / `FormatException` / `OverflowException`), and later failures may show up as runtime exceptions (e.g., `NullReferenceException` if `user` is null) or more specific exceptions (e.g., `InvalidOperationException` for a violated business rule).

```csharp
private readonly IUserRepo _repo;

public void DeactivateUser(string inputId)
{
    int id = int.Parse(inputId);

    var user = _repo.Find(id);

    if (!user.IsActive)
        throw new InvalidOperationException("User already inactive");

    user.IsActive = false;
    _repo.Save(user);
}
```

In a small snippet, the throw sites are obvious. In a real service, exceptions can come from almost anywhere (parsing, mapping, I/O, nulls), so once you start composing steps you end up wrapping a lot of code in `try/catch` scaffolding.

**Option B: Explicit Validation (Guard Clauses)**
If you want to keep exceptions for truly exceptional cases, you end up with guard clauses and early returns. The control flow stays linear and explicit, but the validation checks get interleaved with the work.

> **Aside:** Guard clauses are the bouncer at the door: efficient, reliable… and absolutely uninterested in your “happy path” skipping the line.

```csharp
private readonly IUserRepo _repo;

public string DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out var id))
        return "Invalid ID";

    var user = _repo.Find(id);
    if (user is null)
        return "User not found";

    if (!user.IsActive)
        return "User already inactive";

    user.IsActive = false;
    _repo.Save(user);
    return "Success";
}
```

At this point you either drop the reason (return `bool`) or invent a convention (tuples, out-params, strings). `Result` gives that convention a name and a shape.

#### The Solution: The Control Flow Spectrum

`Result` models **operation outcomes** (success/failure) as values, so you can compose fail-fast workflows without exceptions. It allows us to model **Recoverable Failure** as a first-class value.

> **Concept Check: The Control Flow Spectrum**
> 
> **1. Result (`Result<TSuccess, TError>`) → "Expected failure"**
> *   **Use when:** An operation can fail as part of normal business logic (e.g., "User Not Found" or "Validation Failed").
> *   **Control Flow:** Linear & Composable. You chain operations without `try/catch` blocks.
> 
> **2. Exception → "Panic / Abort"**
> *   **Use when:** Something unexpected happened and you can't continue locally (e.g., unexpected I/O failures, corrupted configuration, invariants being violated).
> *   **Control Flow:** **Jump.** It rips through the stack until caught.

> **Note on Nullable Types (`T?`)**
> 
> C#'s nullable reference types (`string?`, etc.) primarily help the **compiler** detect potential `NullReferenceException`s. They assist in modeling **anticipated absence**, i.e., situations where a value might legitimately be missing (like an optional middle name), or an API might return `null` when a record isn't found. The compiler provides warnings if you don't handle these potential nulls, offering a layer of safety.
> (They don’t change runtime behavior—`null` can still happen—so you still need checks or guards at runtime.)
> 
> Nullable reference types are related, but they solve a different problem:
> *   Focus on **data absence** (static state), not **operation failure** (action outcome).
> *   Primary protection is **compile-time analysis**, not runtime error propagation.
> *   Handled with explicit checks (`if (value is null)`) or operators (`??`), rather than chaining like `Bind`. `Result` gives you that kind of composition for **expected failures**.

> **Aside:** Nullable reference types are the compiler’s polite cough: “ahem… you sure about that?”

Now you can rewrite Option B as a pipeline: each step either produces the next value or stops with an error.

We'll use a simple custom error payload in the examples below (this is **not** part of `Result` itself):

```csharp
public record Error(string Code, string Message);
```

```csharp
string inputId = /* from request */;
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(DeactivateDecision);

string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

> **Note:** `Result` is designed to **short-circuit** (stop at the first error). If you need to **accumulate** multiple errors (e.g., validating a form where you want to show all missing fields at once), use an *Accumulating Validation* type instead.

### Implementing Result
Here’s a small teaching implementation. Don’t use it in production; if you’re shipping this, use a library instead (e.g., *LanguageExt*, *CSharpFunctionalExtensions*, or *FluentResults*).

This teaching version assumes you don’t call `Ok(null)` / `Fail(null)` for reference types.

```csharp
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess? _value;
    private readonly TError? _error;

    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;

    private Result(TSuccess? value, TError? error, bool isSuccess)
    {
        IsSuccess = isSuccess;
        _value = value;
        _error = error;
    }

    public static Result<TSuccess, TError> Ok(TSuccess value)
    {
        return new Result<TSuccess, TError>(
            value,
            default!,
            true);
    }

    public static Result<TSuccess, TError> Fail(TError error)
    {
        return new Result<TSuccess, TError>(
            default!,
            error,
            false);
    }

    // MAP: Transforms the data if successful. If the Result is a Failure, this is skipped entirely.
    // The "Magic Trick": If this Result is already a Failure, the function 'f' never runs,
    // and the existing error is passed along (which is great, because failing is plenty of work already).
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            return Result<U, TError>.Ok(f(_value!));
        }

        return Result<U, TError>.Fail(_error!);
    }

    // BIND: Chains an operation that *also* returns a Result.
    // If the previous step failed, we stop immediately and propagate the error.
    // Note: the function 'f' provides the *new* success OR the *new* failure.
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value!);
        }

        return Result<U, TError>.Fail(_error!);
    }

    // MATCH: Unwraps the final value.
    // This forces you to handle both cases to get the data out.
    // Typically used at the boundary to convert into a public-facing output (HTTP response, UI state, etc.).
    public TResult Match<TResult>(Func<TSuccess, TResult> ok, Func<TError, TResult> err)
    {
        if (IsSuccess)
        {
            return ok(_value!);
        }

        return err(_error!);
    }
}
```

### Handling the Final Outcome
> **Boundary:** the point where your code meets the outside world. Parse/refine inputs, run your logic, then translate the outcome into public outputs.
> Use `Match` at the boundary to convert an internal `Result` into DTOs/status codes/`ProblemDetails`/UI state. Don’t serialize `Result` directly—clients will start depending on its internal shape.

```csharp
Result<int, string> result = Result<int, string>.Ok(42);

string output = result.Match(
    ok:  value => $"Success: {value}",
    err: error => $"Error: {error}"
);
```

#### Why Serialization Breaks the Pattern
A major risk of the `Result` pattern is the temptation to return the object directly to a generic JSON serializer. When you do this, you leak your internal representation into a public contract (and clients start depending on it), which makes refactors and error-shape changes painful.

> **Aside:** A generic serializer is like a toddler with a marker: it will eagerly “help” by drawing *every property it can reach* onto your public API.

Many `Result` implementations expose `Value`/`Error` (and flags like `IsSuccess`) as public properties. A generic serializer will happily turn that internal shape into your public API—it just sees public properties and emits them (often with a camelCase naming policy), e.g.:

```json
{
  "isSuccess": true,
  "isFailure": false,
  "error": null,
  "value": { "id": 123, "isActive": false }
}
```

That wrapper is awkward, and it’s also brittle: now your public contract includes `isSuccess`/`isFailure` and your internal error/value shape. Unwrap at the boundary with `Match`, and return something that’s meant to be public (DTOs, status codes, `ProblemDetails`, etc.).

### Key Benefits
What do you get for returning `Result` instead of throwing or using sentinels?
*   **Explicit Signatures:** `Result<User, Error>` tells you up front that failure is on the table.
*   **Fewer ad-hoc conventions:** No `-1`, no `null`, no “special string means error.”
*   **Testability:** Tests can assert the outcome *and* the specific error (`Code`, type, message) without exception scaffolding.

### Scope & Limitations
`Result` works best for **domain logic**: failures you expect and want to handle. It doesn’t replace exceptions; it just keeps them in their lane.

1.  **Infrastructure:** For technical failures (DB/network outages, timeouts, unexpected I/O errors), exceptions handled at the boundary (middleware/logging/global handlers) are often a good fit.
2.  **Bugs:** Violated preconditions are programmer errors—throw (`ArgumentNullException`, `ArgumentException`, etc.) rather than returning a domain `Result`.
3.  **Accumulation:** `Bind` stops at the first error. If you need to collect *all* validation errors, use a validation type that accumulates errors instead of short-circuiting.

### Putting it together: Unwrap at the boundary
#### Example: Deactivating a user
We want to deactivate a user given an `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

We'll use the same `Error` payload from earlier (this is **not** part of `Result` itself).

```csharp
public record User(int Id, bool IsActive);

public sealed class UserService
{
    private readonly IUserRepo _repo;
    public UserService(IUserRepo repo)
    {
        _repo = repo;
    }

    public Result<User, Error> DeactivateUser(string inputId)
    {
        return ParseId(inputId)
            .Bind(FindUser)
            .Bind(DeactivateDecision);
    }

    public string HandleDeactivateRequest(string inputId)
    {
        Result<User, Error> result = DeactivateUser(inputId);

        return result.Match(
            ok: user =>
            {
                _repo.Save(user);
                return "User deactivated";
            },
            err: e => $"Deactivate failed: {e.Code} - {e.Message}");
    }

    private static Result<int, Error> ParseId(string inputId) =>
        int.TryParse(inputId, out var id)
            ? Result<int, Error>.Ok(id)
            : Result<int, Error>.Fail(new Error("Parse", "Invalid ID format"));

    private Result<User, Error> FindUser(int id)
    {
        var user = _repo.Find(id);
        return user is null
            ? Result<User, Error>.Fail(new Error("NotFound", $"User {id} not found"))
            : Result<User, Error>.Ok(user);
    }

    private static Result<User, Error> DeactivateDecision(User user)
    {
        if (!user.IsActive)
            return Result<User, Error>.Fail(new Error("Domain", "User is already inactive"));

        return Result<User, Error>.Ok(user with { IsActive = false });
    }
}
```

The idea: compute a `Result<User, Error>` in your internal workflow, then unwrap it once at the boundary in `HandleDeactivateRequest`.

### The Async Reality (Async composition friction)

In modern .NET apps, most I/O APIs follow the Task-based async pattern (`Task` / `Task<T>`).[^tap] This creates a "wrapping problem": your return types become `Task<Result<User, Error>>`.

One way to think about it: `Task<T>` composes too. `await` + projection looks like `Map`, and `await` + returning another task looks like `Bind`.[^task-monad]

The friction happens when you stack them. If you try to mix the `Task` monad (awaiting) and the `Result` monad (failure handling), you end up needing to `await` manually before every step—and you can't just `await` your way out of the structure, because `await` unwraps the `Task`, not the `Result`. This brings back the indentation you tried to kill.

### How to fix it (Combinators)
If you need async + `Result` composition, don’t hand-roll helpers. Use a library that provides **async-aware combinators** (often `Bind`/`Map` overloads for `Task<Result<...>>`; some libraries also expose `BindAsync`/`MapAsync`):

> **Aside:** The library authors have already stepped on the rakes here so you don’t have to.

- **CSharpFunctionalExtensions**: Closest to the code in this post.
- **LanguageExt**: Strict functional style ("Haskell for C#").
- **FluentResults**: Object-oriented features.

> **Either bias note:** Most `Either`/`Result` APIs are **right-/success-biased**: `Map`/`Bind` operate on the success branch and propagate the error branch unchanged. If you’re using an `Either` type, double-check which side your library treats as “success.”

With a library, the async pipeline stays linear.

Assume `ParseIdAsync : string -> Task<Result<int, Error>>` and `FindUserAsync : int -> Task<Result<User, Error>>`.

```csharp
private static Task<Result<User, Error>> DeactivateDecisionAsync(User user) =>
    Task.FromResult(DeactivateDecision(user));

public Task<Result<User, Error>> DeactivateUserAsync(string inputId) =>
    ParseIdAsync(inputId)
        .Bind(FindUserAsync)
        .Bind(DeactivateDecisionAsync);
```

### Wrap-up

`Result` keeps “expected failure” in-band, as data.

1.  **Chain** with `Map`/`Bind`.
2.  **Handle** `Task<Result<...>>` using async combinators.
3.  **Decide** once at the edge with `Match`.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.
[^tap]: See Microsoft Learn: [Task asynchronous programming model](https://learn.microsoft.com/en-us/dotnet/csharp/asynchronous-programming/task-asynchronous-programming-model).
[^task-monad]: `Task<T>` behaves *monad-like* (it supports `Map`/`Bind`-shaped composition), but it isn’t pure: work may start eagerly, timing/scheduling matters, and exceptions/cancellation are part of the semantics. For this post, the useful point is just: **it composes**.
