---
title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use Map/Bind/Match to compose fail-fast workflows with explicit errors (plus notes on async and API boundaries)."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/a-list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In Part 1 we used `List<T>` to contrast `Map` vs `flatMap`, then built `Maybe<T>` to chain optional steps. Now we model *fallible* outcomes with a reason: `Result<TSuccess, TError>`.

`Result` sequences steps with `Bind`: the first failure short-circuits and its error flows to the end. If you need to **accumulate** many independent errors (like form validation), use an accumulating validation/applicative type instead.

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

For now, think of `ParseId`, `FindUser`, and `Deactivate` as small functions in scope; later I’ll show them as methods on a `UserService`.

If you use LINQ: `Map` is `Select`, and `Bind` is `SelectMany`.

Terminology: many libraries call this `Either<L, R>` (Left/Right). By convention, `Right` is success, `Left` is error, and `Map`/`Bind` usually operate on `Right` (aka “right-biased”).

### Result: when “missing” needs a reason

`Maybe<T>` tells us whether a value exists. `Result` adds why it doesn’t.

- `Ok(value)` means the operation succeeded (like `Some`).
- `Fail(error)` means the operation failed and carries error data (like `None`, but with a payload).
- `Bind` / `FlatMap` is the mechanism that chains the steps.
- `Map` / `Select` transforms the successful value without changing the error branch.
- `Match` is how you handle both cases (success vs failure) and get back to a normal value.

### Short-circuiting

`Result` is, well, a monad, so `Bind` only runs the next step if the previous one succeeded. It’s the same idea as `&&` short-circuiting.

- If `ParseId` fails, `FindUser` is skipped.
- If `FindUser` fails, `Deactivate` is skipped.
- The error produced by the first failure is passed all the way to `Match`.

This is fail-fast: you get the first error, not a list of everything that could have failed.

### Example: deactivating a user

We want to deactivate a user given an `id` **string** from an HTTP request. We parse it to `int`, load the user, ensure they’re active, then persist `IsActive = false`.

The steps are sequential:

1.  Parse: `string` → `int`
2.  Find: user must exist
3.  Rule: user must be active

Use `T?` when a value might be missing and you don’t care why; use `Result<TSuccess, TError>` when absence needs a reason.

### Why bother with `Result`?
Returning `Result<TSuccess, TError>` makes expected failure obvious in the type system instead of hiding it in `null` or the call stack.

It has a few practical upsides:

- Callers see “this can fail” up front (and you can carry a real error value, not just `false`).
- You don’t have to use sentinel values like `null` to mean “something went wrong.”
- You can reuse `ParseId`, `FindUser`, and rules without repeating the same checks everywhere.
- Tests can assert on `Ok` / `Fail` instead of catching exceptions.

### When `Result` is the wrong tool
`Result` is great for expected, domain-level failures. It’s not a replacement for exceptions, and it’s not something you want everywhere.

A few common gotchas:

- Infrastructure failures (DB down, OOM, null refs): let exceptions bubble to your global middleware.
- Bugs / invariant violations: throw (e.g., `ArgumentNullException`). That’s a caller bug, not a domain outcome.
- Form-style validation: `Bind` stops at the first error, but users usually want *all* validation errors at once; use an accumulating validation type (often called `Validation<TError, TSuccess>`) which composes via applicative rather than monadic chaining.
  If that distinction is new, the search term you want is “applicative validation”.

Also: if you’re in a hot path, watch allocations (this tutorial uses a class). And if you’re stacking effects (`Task<Result<...>>`), you’ll want async combinators or you’ll end up writing a lot of glue.

### The status quo
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
Here’s the same workflow written as a straight-line pipeline:

```csharp
public Result<User, Error> DeactivateUser(string inputId) =>
    ParseId(inputId)
        .Bind(FindUser)
        .Bind(Deactivate);
```

Every step here can fail, so we use `Bind` throughout. If a step can’t fail (it just transforms data), use `Map` instead.

Example of a non‑failing transform with `Map`:

```csharp
var userIdResult = DeactivateUser(inputId).Map(u => u.Id);
```

Most libraries also include helpers like `MapError`/`BindError` and `Tap`/`TapError`. This tutorial keeps the surface area small.

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

A useful mental model: `Task<T>` composes too: `await` + projection is basically `Map`, and `await` + returning another task is basically `Bind`.

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
