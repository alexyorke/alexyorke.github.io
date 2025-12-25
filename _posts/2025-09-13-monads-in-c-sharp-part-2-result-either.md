---
title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use Map/Bind/Match to compose fail-fast workflows with explicit errors (plus notes on async and API boundaries)."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/a-list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In **Part 1**, we used `List<T>` to contrast `Map` vs `flatMap`, and built `Maybe<T>` to chain optional steps. Now, we model **fallible** outcomes with a reason: `Result<TSuccess, TError>`.

Think of `Result` like `Maybe`, but the negative branch carries data. While `Maybe` represents *absence* (`None`), `Result` represents *failure* (`Error`).

The Result monad allows you to represent a computation's outcome as success or failure and to sequence computations so failures propagate automatically. This saves you from writing nested `if` statements (or "arrow code") or relying on `try`/`catch` for control flow.

#### The Problem: The "If" Ladder
Without `Bind` (or any chainable abstraction), dependent steps create deep nesting or require early returns that clutter the logic:

```csharp
// Imperative: Hard to read, easy to mess up error propagation
var idResult = ParseId(inputId);
if (!idResult.Success) return ShowError(idResult.Error);

var userResult = FindUser(idResult.Value);
if (!userResult.Success) return ShowError(userResult.Error);

var activeResult = Deactivate(userResult.Value);
if (!activeResult.Success) return ShowError(activeResult.Error);

return "User deactivated";
```

#### The Solution: Chaining
`Result` sequences these steps using `Bind`. This keeps the "happy path" readable: the first failure short-circuits the chain, and that error flows to the end automatically.

```csharp
// Declarative: Focuses on the "Happy Path"
Result<User, Error> result =
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(Deactivate);

// Handle the final outcome in one place
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

> **Note:** `Result` is designed to **short-circuit** (stop at the first error). If you need to **accumulate** multiple errors (e.g., validating a form where you want to show all missing fields at once), use an *Accumulating Validation* type instead.

#### Example: Deactivating a user
We want to deactivate a user given an `id` **string** from an HTTP request.[^id] The steps are sequential:
1.  **Parse:** `string` → `int`
2.  **Find:** user must exist in the database.
3.  **Logic:** user must currently be active.
4.  **Action:** persist `IsActive = false`.

#### The Status Quo (`Try` Pattern)
The strongest standard C# alternative is `Try...out`. It is fast, but it is "stringly typed" regarding failure—returning `false` destroys the "why" (was it a bad ID? Or just already inactive?).

```csharp
public static bool TryDeactivateUser(IUserRepo repo, string inputId, out User? user)
{
    // It's easy to mix up parsing logic, db lookups, and business rules here.
    if (int.TryParse(inputId, out int id)
        && repo.TryFind(id, out var found)
        && found.IsActive)
    {
        found.IsActive = false;
        repo.Save(found);
        user = found;
        return true;
    }

    user = null;
    return false; // Why did it fail? We don't know anymore.
}
```

#### The Result Approach
Here is the same workflow as a pipeline. Because every step can fail, we use `Bind` to chain them together.

```csharp
public Result<User, Error> DeactivateUser(string inputId) =>
    ParseId(inputId)       // Returns Result<int, Error>
        .Bind(FindUser)    // Returns Result<User, Error>
        .Bind(Deactivate); // Returns Result<User, Error>
```

Callers can now immediately see that this operation might fail, and the specific error (InvalidInput, NotFound, or AlreadyInactive) is preserved.

If a step **cannot** fail (it just transforms data), use `Map` instead:

```csharp
// Extract just the ID from the result
var userIdResult = DeactivateUser(inputId).Map(u => u.Id);
```

### Why bother?
Using `Result` over exceptions or `bool` returns has specific benefits:
*   **Honest Signatures:** You don't have to read the source code to know a method can fail.
*   **No Sentinels:** No more `return null` or `-1` to represent errors.
*   **Testability:** Tests assert on `Ok` vs `Fail` states rather than `ExpectedException` attributes.

### When `Result` is the wrong tool
`Result` is for **domain logic** failures. It is not a silver bullet.

1.  **Infrastructure:** If the DB is down or you run out of memory, let the exception bubble to your middleware. Do not catch generic exceptions just to wrap them in `Result.Fail`.
2.  **Bugs:** If a method receives a `null` argument that should never be null, throw `ArgumentNullException`. That is a bug, not a business outcome.
3.  **Accumulation:** As mentioned earlier, `Bind` short-circuits. For form validation (where you want 10 errors, not just the first one), you need "Applicative Validation," not monadic binding.

> **Performance Note:** If you are in a hot path, watch your allocations. This tutorial uses a class for `Result`, but highly optimized libraries often use `readonly struct` to minimize GC pressure.

### Introducing `Result<TSuccess, TError>`

Naming: in FP you’ll often see this called `flatMap` (LINQ: `SelectMany`). I’m using `Bind` here to keep it distinct from `Map` and to match Part 1.

If you like the FP lens: `Ok` is `return` and `Bind` is `>>=`.

```csharp
using System;

// Structured error type (instead of `string`).
public record Error(string Code, string Message);

// A tiny teaching implementation of Result<TSuccess, TError>.
// (Use a library in production.)
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess? _value;
    private readonly TError? _error;

    private Result(TSuccess? value, TError? error, bool isSuccess)
    {
        IsSuccess = isSuccess;
        _value = value;
        _error = error;
    }

    public static Result<TSuccess, TError> Ok(TSuccess value) => new Result<TSuccess, TError>(value, default, true);
    public static Result<TSuccess, TError> Fail(TError error) => new Result<TSuccess, TError>(default, error, false);

    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;

    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            return Result<U, TError>.Ok(f(_value));
        }

        return Result<U, TError>.Fail(_error);
    }

    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value);
        }

        return Result<U, TError>.Fail(_error);
    }

    // Optional: LINQ query syntax support (Select/SelectMany)
    public Result<U, TError> Select<U>(Func<TSuccess, U> f) => Map(f);

    public Result<V, TError> SelectMany<U, V>(
        Func<TSuccess, Result<U, TError>> bind,
        Func<TSuccess, U, V> project) =>
        Bind(t => bind(t).Map(u => project(t, u)));

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

> **Side note: LINQ / query syntax**
> C# query syntax looks for `Select` and `SelectMany`. In the tutorial `Result` above, they’re thin wrappers around `Map`/`Bind`, so this works:

```csharp
string inputId = "123";

var result =
    from id in ParseId(inputId)
    from user in FindUser(id)
    select user;
```

I’m using explicit method chaining (`Bind`) in most examples because it makes the short-circuiting behavior obvious.

### Unwrapping with `Match` (at the boundary)
At the boundary, unwrap with `Match`.

```csharp
Result<int, Error> result = Result<int, Error>.Ok(1);
var message = result.Match(
    ok:  v => $"Ok({v})",
    err: e => $"Fail({e.Code}: {e.Message})");
```

Compose and unwrap once (with `Match`) at the boundary.

### Putting it together: the Deactivate User pipeline
Here’s the workflow as small steps:

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

        // Pragmatic note: ORMs often mutate tracked entities.
        user.IsActive = false;
        return Result<User, Error>.Ok(user);
    }
}
```

Do reads/rules in the pipeline; do writes at the boundary (the “functional core, imperative shell” idea).

In a real app, this boundary usually lives in an application service/transaction.

### The Async Reality (Async composition friction)

In modern C#, almost all I/O is asynchronous and returns `Task<T>`.
That means you often end up stacking effects: async (`Task`) and failure (`Result`).

A useful mental model: `Task<T>` composes too: `await` + projection is basically `Map`, and `await` + returning another task is basically `Bind`.[^task-monad]

The annoying case is `Task<Result<...>>`: you want to keep the same straight-line `Bind` flow, but you can’t without a couple helper methods.

Libraries usually call these `BindAsync` / `MapAsync` / `SelectManyAsync`. Most `Result` libraries already have them.

### If you want this in real code
Async combinators need careful handling. If you need async + `Result` composition, pick a library and use its async helpers:
- ErrorOr (Simple, struct-based)
- FluentResults (Rich features)
- LanguageExt (Strict functional style)

With those, the pipeline stays linear:

```csharp
// What these libraries allow you to do:
public Task<Result<User, Error>> DeactivateUser(string inputId) =>
    ParseIdAsync(inputId)          // Task<Result<int, Error>>
        .BindAsync(FindUserAsync)  // Task<Result<User, Error>>
        .BindAsync(DeactivateAsync);
```

### Exiting the Monad (The API Boundary)
Treat `Result<TSuccess, TError>` as internal plumbing. At the boundary (API/UI), unwrap it with `Match` into your boundary type (`IActionResult`, `ProblemDetails`, view model, etc.) and map internal errors to stable public shapes.

### Testing Strategies
Assert on the returned `Result` instead of exceptions:

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

### Wrap-up

`Result` is just a way to keep “expected failure” in-band, as data. Compose with `Map`/`Bind`, and unwrap once at the edge with `Match`.

If you end up in `Task<Result<...>>` land, grab a library with async combinators rather than hand-rolling them.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.
[^task-monad]: In a strict sense, `Task<T>` isn’t a pure monad in the mathematical sense because it can complete before you bind it and can capture asynchronous execution effects. Still, for practical purposes in C#, treating `Task<T>` as monadic is a useful mental model for understanding async composition patterns.
