---

title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use Map/Bind/Match to compose fail-fast workflows with explicit errors (plus notes on async and API boundaries)."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In Part 1 you built `Maybe` and used `Bind`/`FlatMap` to chain optional steps. Here we add an error branch: `Result<TSuccess, TError>`.

`Result` lets you chain fallible steps without an `if` ladder or `try`/`catch` for expected outcomes:

```csharp
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(Deactivate);

string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

If you think in `LINQ`: `Map` ≈ `Select`, `Bind`/`FlatMap` ≈ `SelectMany`. We’ll stick to method style here to keep focus on the flow rather than syntax.

### Result: when “missing” needs a reason

`Maybe<T>` tells us whether a value exists. `Result` adds *why* it doesn’t:

*   **Unit (`Ok`)**: lift a raw value into Success.
*   **Map**: transform the Success value.
*   **Bind**: chain a function that returns `Result`.

Key behavior: **Bind is fail-fast**. After the first failure, downstream steps don’t run.

Think of it like:
*   `Ok(value)` -> like `Some(value)`
*   `Fail(error)` -> like `None()`, but with a reason

### Scenario: The "Deactivate User" Pipeline

We want to deactivate a user given an `id` **string** from an HTTP request. We parse it to `int`, load the user, ensure they’re active, then persist `IsActive = false`.[^id]

The steps are sequential:

1.  **Parse:** `string` → `int`.
2.  **Find:** user must exist.
3.  **Rule:** user must be active.

> **Quick note: Result vs. `T?` (optional)**
>
> Use `T?` when a value might be missing and you don’t care why (e.g., middle name).
>
> Use `Result<TSuccess, TError>` when absence needs a reason (e.g., user lookup: `NotFound` vs `PermissionDenied` vs `DatabaseError`).

These steps are sequential: step 2 depends on step 1. `Result` models this fail-fast flow.

### When NOT to use `Result`
`Result` is great for **expected, domain-level failures**. It’s a poor fit in a few common scenarios:

- **System failures:** DB down, OOM, null refs → let exceptions bubble to global middleware.
- **Bugs / invariant violations:** throw (e.g., `ArgumentNullException`); that’s a caller bug, not a domain outcome.
- **Hot paths:** if allocations matter, `Result`-as-class may be too costly; prefer `try`/`out` or structs.
- **Validation that must accumulate errors:** monadic chaining is fail-fast; use an accumulator.
- **Shotgun validation:** parse once at the boundary into strong types; don’t return `Result` everywhere for primitive checks.
- **Side-effect-only chains:** avoid “monadifying” effects; keep writes at the boundary or use explicit orchestration.
- **Partial success / batch work:** prefer per-item outcomes over all-or-nothing `Result<List<T>, E>`.
- **Effect stacking:** if you’re drowning in `Task<Result<...>>` glue without async combinators, the cost may outweigh the benefits.

### Comparison: The Status Quo
The strongest C# alternative is `Try`/`out`: it’s fast, but `false` loses the reason for failure.

```csharp
public static bool TryDeactivateUser(
    IUserRepo repo,
    string inputId,
    [System.Diagnostics.CodeAnalysis.NotNullWhen(true)] out User? user) // non-null when the method returns true
{
    if (int.TryParse(inputId, out int id)
        && repo.TryFind(id, out var found)
        && found.IsActive)
    {
        found.IsActive = false;
        repo.Save(found);
        user = found;
        return true;
    }

    // Assign the out parameter on the failure path (conventionally a default/null for reference types)
    user = null;
    return false;
}
```


#### The Result Monad
Goal: linear flow with explicit errors as values.

```csharp
// The goal: a linear pipeline that short-circuits on failure.
// (Helper methods ParseId/FindUser/Deactivate are shown below.)
public Result<User, Error> DeactivateUser(string inputId) =>
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(Deactivate);
```

### Introducing Result<TSuccess, TError>

> *Note on Naming:* In functional programming, this operation is called `flatMap` (or `SelectMany` in LINQ). We use the name **`Bind`** here to keep it distinct from `Map` and to match the convention established in Part 1.

```csharp
// Structured error type (avoid `string` errors).
public record Error(string Code, string Message);

// Educational implementation of Result<TSuccess, TError>.
//
// Note: Use `readonly struct` in production to reduce allocations.
// Note: Null/default-state checks are intentionally omitted here; use a well-tested library in production.
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess _value;
    private readonly TError _error;

    // Private constructors ensure valid state
    private Result(TSuccess value)
    {
        IsSuccess = true;
        _value = value;
        _error = default;
    }

    private Result(TError error)
    {
        IsSuccess = false;
        _value = default;
        _error = error;
    }

    // The "Unit" operation (lifts a value into the Monad).
    // We name it 'Ok' to follow standard C# conventions (similar to 'Some' in Part 1).
    public static Result<TSuccess, TError> Ok(TSuccess value) => new Result<TSuccess, TError>(value);
    public static Result<TSuccess, TError> Fail(TError error) => new Result<TSuccess, TError>(error);

    // ------------------------------------------------------------
    // Queries (For domain logic, prefer Match over checking these)
    // ------------------------------------------------------------
    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;

    // Map: Transform the success value (TSuccess -> U)
    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            // Explicitly call the factory. Clear to Java/Rust/JS devs.
            return Result<U, TError>.Ok(f(_value));
        }

        // Propagate the existing error
        return Result<U, TError>.Fail(_error);
    }

    // Bind: Chain operation (TSuccess -> Result<U, TError>)
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value);
        }

        return Result<U, TError>.Fail(_error);
    }

    // Match: The only way to extract the value
    public TResult Match<TResult>(Func<TSuccess, TResult> ok, Func<TError, TResult> err)
    {
        if (IsSuccess)
        {
            return ok(_value);
        }

        return err(_error);
    }
}
```

> **Side note: LINQ**
> With `SelectMany` overloads, query syntax works too:

```csharp
var result = 
    from id in ParseId(input)
    from user in FindUser(id)
    select user;
```

> We are sticking to explicit method chaining (`Bind`) in this post to make the data flow visible, but production libraries usually support both.

> Production note: equality/default behavior omitted.
>
> **Exception policy:** `Bind` does not catch exceptions thrown inside `f(...)`. Treat bugs/system failures as exceptions.

### Unwrapping with `Match` (at the boundary)
At the boundary, unwrap with `Match`.

```csharp
Result<int, Error> result = Result<int, Error>.Ok(1);
var message = result.Match(
    ok:  v => $"Ok({v})",
    err: e => $"Fail({e.Code}: {e.Message})");
```

Prefer composing and unwrapping once at the boundary.

**On `IsSuccess` / `IsFailure`**
Flags are handy for quick checks or filtering, but prefer `Match` when you need the value so the error branch stays handled.

**Why no `.Value` property?**

This tutorial `Result` doesn’t expose a `public Value` property. That nudges you toward `Match` instead of manual inspection.

```csharp
// ⚠️ ANTI-PATTERN (hypothetical — not implemented in this tutorial)
// If Result exposed a public Value property, it would be tempting to do this:
//
// if (result.IsSuccess)
// {
//     // Depending on the implementation, this might throw or be null if you get it wrong.
//     var val = result.Value;
// }
```

Keeping the state private pushes you toward `Match`, so the error case stays handled.

Avoid adding helper methods like `ValueOrThrow()`: they reintroduce “exceptions as control flow.”

### Putting it together: the Deactivate User pipeline
Now the workflow is a few small steps, with persistence at the boundary:

```csharp
public sealed class User
{
    public int Id { get; init; }
    public bool IsActive { get; set; } = true;
}

public interface IUserRepo
{
    User? Find(int id);
    void Save(User user);
}

public sealed class UserService
{
    private readonly IUserRepo _repo;
    public UserService(IUserRepo repo) => _repo = repo;

    // Pipeline: validate + load + decide
    public Result<User, Error> DeactivateUser(string inputId) =>
        ParseId(inputId)
            .Bind(FindUser)
            .Bind(Deactivate);

    // Boundary: exit Result and perform effects (persistence, logging, etc.)
    public string DeactivateUserAndSave(string inputId) =>
        DeactivateUser(inputId).Match(
            ok: user =>
            {
                _repo.Save(user);
                return "User deactivated";
            },
            err: e => $"Deactivate failed: {e.Code} - {e.Message}");

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

    private static Result<User, Error> Deactivate(User user)
    {
        if (!user.IsActive)
            return Result<User, Error>.Fail(new Error("Domain", "User is already inactive"));

        // Functionally, we should return a new object (e.g., `user with { IsActive = false }`).
        // Pragmatically, we mutate the existing EF Core entity to simplify persistence.
        user.IsActive = false;
        return Result<User, Error>.Ok(user);
    }
}
```

> **A Note on I/O and Side Effects**
> Reads (`FindUser`) inside the pipeline are common in Railway-Oriented Programming. Writes stay outside: commit `_repo.Save` in the `Match` success branch (“functional core, imperative shell”).

> **Functional Purity Note:**
> FP would return a new user; ORMs like EF typically mutate tracked entities. We mutate here for pragmatism.

In a real app, this boundary usually lives in an application service/transaction.

### The Async Reality (Async composition friction)

Most I/O is async (`Task<T>`), which makes `Task<Result<...>>` composition awkward.

Without async bridges, you can’t chain `Task<Result<...>>` with the same linear flow — you end up manually `await`-ing and unwrapping each step.

To fix this, you need "Async Bridges" (e.g., `BindAsync` or `SelectManyAsync`).

We aren’t building those extensions here; production libraries (LanguageExt, FluentResults, CSharpFunctionalExtensions) provide them.

### A Warning on Implementation
Async combinators need careful handling (cancellation, exceptions). Writing your own `Result` is fine for learning; for production, use a library:
- ErrorOr (Simple, struct-based)
- FluentResults (Rich features)
- LanguageExt (Strict functional style)

Then you can write:

```csharp
// What these libraries allow you to do:
public Task<Result<User, Error>> DeactivateUser(string inputId) =>
    ParseIdAsync(inputId)          // Task<Result<int, Error>>
        .BindAsync(FindUserAsync)  // Task<Result<User, Error>>
        .BindAsync(DeactivateAsync);
```

### Exiting the Monad (The API Boundary)

Treat `Result<TSuccess, TError>` as internal plumbing. At the boundary (API controller, UI, etc.), unwrap it (e.g., to `IActionResult`) using `Match`.

**Never return** a raw `Result` object directly to the frontend. It’s an internal plumbing tool, not a public data contract. Returning it is a **leaky abstraction**: it forces your JavaScript client to learn about your internal C# architecture.

In ASP.NET Core, **`ProblemDetails` is the standard error shape**, so mapping `Result` → `ProblemDetails` is usually better than a custom `{ success: false, error: ... }` wrapper.

**The "Russian Doll" risk**

If you return a `Result<...>` directly from a controller, you leak your internal abstraction to the frontend and create awkward wrapper JSON (often something like `{ "isSuccess": true, "value": ... }`).

Exposing `isSuccess` wrappers couples clients to server internals. Prefer status codes and `ProblemDetails`.

**The fix: unwrap at the boundary**
Treat `Result` as internal plumbing: use `Match` at the boundary to map it into standard HTTP responses.

```csharp
// Treat Result as internal: unwrap it at the boundary into a standard response.

[HttpGet("{id}")]
public async Task<IActionResult> GetUser(string id)
{
    Result<User, Error> result = await _userService.Get(id);

    // Use Match to unwrap the Result back into the "Real World"
    return result.Match<IActionResult>(
        ok: user => Ok(user),
        err: error => error.Code switch
        {
            "NotFound" => NotFound(new ProblemDetails { Title = error.Code, Detail = error.Message, Status = 404 }),
            "Parse" or "Validation" => BadRequest(new ProblemDetails { Title = error.Code, Detail = error.Message, Status = 400 }),
            // Avoid leaking internal details. For true "unexpected" failures, prefer centralized exception handling.
            _ => StatusCode(500, new ProblemDetails { Title = "Unexpected", Detail = "An unexpected error occurred.", Status = 500 })
        }
    );
}
```

### Testing Strategies

Assert on the returned `Result` instead of exceptions.

```csharp
[Fact]
public void DeactivateUser_ReturnsFailure_WhenUserNotFound()
{
    // Arrange
    var repo = new InMemoryUserRepo(); // empty repo => not found
    var service = new UserService(repo);

    // Act
    var result = service.DeactivateUser("123");

    // Assert
    Assert.True(result.IsFailure);
    
    // We inspect the error using Match to ensure it's the *correct* failure
    var errorCode = result.Match(
        ok => "UNEXPECTED_SUCCESS", 
        err => err.Code
    );
    Assert.Equal("NotFound", errorCode);
}
```

### Takeaways

1.  **One shape for error flow:** Use `Result<TSuccess, TError>` to keep sequential workflows linear via `Map`/`Bind` instead of nesting `if`s.
2.  **Fail-fast is the point:** `Bind` stops on the first failure. That's ideal for dependent pipelines (and not ideal for "collect all errors" validation).
3.  **Unwrap at the boundary:** Don't serialize `Result` to JSON or return `isSuccess` flags. Use `Match` at the edge to turn it into HTTP/UI responses.
4.  **Prefer established libraries:** For production, rely on maintained packages for async composition (`Task<Result<...>>`) and edge-case handling.

> **Further Reading (The "Railway" Metaphor):**
> This pattern is widely known in the .NET community as **"Railway Oriented Programming,"** a term coined by Scott Wlaschin. If you want to see this concept taken to its logical conclusion (including validation aggregation and parallel tracks), his site [F# for Fun and Profit](https://fsharpforfunandprofit.com/rop/) is the definitive resource.

**A Note on Libraries:**
For production C#, prefer a mature library (e.g., **FluentResults**, **ErrorOr**, **LanguageExt**) rather than maintaining your own.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.