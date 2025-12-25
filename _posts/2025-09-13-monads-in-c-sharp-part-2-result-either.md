---

title: "Monads in C# (Part 2): Result"
date: 2025-09-13
description: "Build a small Result type in C# and use Map/Bind/Match to compose fail-fast workflows with explicit errors (plus notes on async and API boundaries)."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/a-list-is-a-monad/)

> _Note_: This post was substantially rewritten on 2025-12-21.

In Part 1 we used List<T> to go over Map vs flatMap, then built Maybe<T> to chain optional steps. Now we shift focus: instead of handling multiple values or optional values, we model fallible outcomes that capture the reason for failure: Result<TSuccess, TError>.

The Result monad allows you to represent a computation's outcome as success or failure, and to sequence computations so failures propagate until handled.

(Note: For scenarios where you need to collect multiple errors at once—like validating a form with five fields—Result is less suitable because it stops at the first error. That pattern is typically handled by a 'Validation' structure instead.)

Result is optimized for fail-fast operations like I/O or single-step checks. When accumulating independent failures—for example, validating a form with numerous fields—use validation abstractions such as Validation<E, T>, EitherNel<E, T>, or a schema library to model error accumulation using an applicative combinator, generating a single, structured error object for UI display and reducing manual aggregation within a Result.

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

For the next few sections, you can think of `ParseId`, `FindUser`, and `Deactivate` as small functions in scope; later I’ll show them as methods on a `UserService` to make the example more realistic.

You likely use this pattern already.
If you use LINQ, you know this flow: `Map` is just `Select`, and `Bind` is just `SelectMany`. We are simply applying that same chainable logic to single outcomes instead of lists.

Terminology note: I’ll call it `Result<TSuccess, TError>` in this post. In other languages/libraries you’ll often see `Either<L, R>` (Left/Right). By convention, Right is success and Left is the error.

In FP terms, that’s a two-case “sum type” (a discriminated union). C# doesn’t have that shape built-in, so we either implement it ourselves or lean on a library.

Also, most `Either` implementations in C# are “right-biased”, which just means `Map`/`Bind` operate on the Right (success) branch.

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

We want to deactivate a user given an `id` **string** from an HTTP request. We parse it to `int`, load the user, ensure they’re active, then persist `IsActive = false`.[^id]

The steps are sequential:

1.  Parse: `string` → `int`
2.  Find: user must exist
3.  Rule: user must be active

> **Quick note: Result vs. `T?` (optional)**
>
> Use `T?` when a value might be missing and you don’t care why (e.g., middle name).
>
> Use `Result<TSuccess, TError>` when absence needs a reason (e.g., user lookup: `NotFound` vs `PermissionDenied` vs `DatabaseError`).

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

Most libraries also include helpers like `MapError` / `BindError` to transform errors, and `Tap` / `TapError` to run side effects without changing the shape.

### Introducing `Result<TSuccess, TError>`

Naming: in FP you’ll often see this called `flatMap` (LINQ: `SelectMany`). I’m using `Bind` here to keep it distinct from `Map` and to match Part 1.

If you like the FP lens: `Ok` is `return` and `Bind` is `>>=`. Informally, the laws say `Ok(x).Bind(f)` behaves like `f(x)`, `m.Bind(Ok)` behaves like `m`, and chaining is associative—as long as your functions don’t throw and you keep `TError` fixed across the chain.

```csharp
// Structured error type (instead of `string`).
public record Error(string Code, string Message);

// A tiny teaching implementation of Result<TSuccess, TError>.
// It skips some edge-case checks on purpose; use a well-tested library in production.
// This version uses a single private constructor to avoid overload collisions
// when TSuccess == TError on constructed generic types.
public sealed class Result<TSuccess, TError>
{
    // Only one of these is populated at a time.
    // They're nullable to keep the sample friendly to C# nullable reference types (NRT).
    private readonly TSuccess? _value;
    private readonly TError? _error;

    // This implementation relies on the invariant that `_value` is only read when `IsSuccess` is true.
    // Nullable analysis can’t prove that here, so you may see warnings in a real project (fine for a toy sample).

    // Single private constructor ensures a valid state without risking signature collisions
    // on constructed generic types where TSuccess == TError.
    private Result(TSuccess? value, TError? error, bool isSuccess)
    {
        IsSuccess = isSuccess;
        _value = value;
        _error = error;
    }

    // The "Unit" operation (lifts a value into the Monad).
    // We name it 'Ok' to follow standard C# conventions (similar to 'Some' in Part 1).
    public static Result<TSuccess, TError> Ok(TSuccess value) => new Result<TSuccess, TError>(value, default, true);
    public static Result<TSuccess, TError> Fail(TError error) => new Result<TSuccess, TError>(default, error, false);

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
            // Explicitly call the factory.
            return Result<U, TError>.Ok(f(_value));
        }

        // Propagate the existing error
        return Result<U, TError>.Fail(_error);
    }

    // Bind: Chain operation (TSuccess -> Result<U, TError>)
    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        // No magic: This is just the "if (success)" check abstracted into a method.
        if (IsSuccess)
        {
            return f(_value);
        }

        return Result<U, TError>.Fail(_error);
    }

    // ------------------------------------------------------------
    // LINQ query syntax support (Select/SelectMany)
    // ------------------------------------------------------------
    public Result<U, TError> Select<U>(Func<TSuccess, U> f) => Map(f);

    public Result<V, TError> SelectMany<U, V>(
        Func<TSuccess, Result<U, TError>> bind,
        Func<TSuccess, U, V> project) =>
        Bind(t => bind(t).Map(u => project(t, u)));

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

> **Side note: LINQ / query syntax**
> C# query syntax requires methods named `Select` and `SelectMany` (instance methods or extension methods). In the tutorial `Result` above, they’re thin wrappers around `Map`/`Bind`, so query syntax works too:

```csharp
string inputId = "123";

var result =
    from id in ParseId(inputId)
    from user in FindUser(id)
    select user;
```

If you’re using a `Result` type you can’t modify, you can also supply the LINQ method names as extension methods:

```csharp
public static class ResultLinqExtensions
{
    public static Result<U, E> Select<T, U, E>(
        this Result<T, E> result,
        Func<T, U> map) =>
        result.Map(map);

    public static Result<U, E> SelectMany<T, U, E>(
        this Result<T, E> result,
        Func<T, Result<U, E>> bind) =>
        result.Bind(bind);

    // Required for query syntax translation (the "project" / result selector overload).
    public static Result<V, E> SelectMany<T, U, V, E>(
        this Result<T, E> result,
        Func<T, Result<U, E>> bind,
        Func<T, U, V> project) =>
        result.Bind(t => bind(t).Map(u => project(t, u)));
}
```

I’m using explicit method chaining (`Bind`) in most examples because it makes the short-circuiting behavior obvious. This tutorial type is intentionally minimal (equality/default-state handling omitted), and `Bind` does not catch exceptions thrown inside `f(...)`.

### Unwrapping with `Match` (at the boundary)
At the boundary, unwrap with `Match`.

```csharp
Result<int, Error> result = Result<int, Error>.Ok(1);
var message = result.Match(
    ok:  v => $"Ok({v})",
    err: e => $"Fail({e.Code}: {e.Message})");
```

Try to compose and unwrap once, at the boundary.

**On `IsSuccess` / `IsFailure`**
Flags are fine for quick checks, but reach for `Match` when you need the value so the error branch stays handled.

**Why no `.Value` property?**

This tutorial `Result` doesn’t expose a `public Value` property; `Match` is the unwrapping API.

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

Keeping state private makes unwrapping explicit: `Match` forces handling both branches.

Methods like `ValueOrThrow()` reintroduce “exceptions as control flow.”

### Putting it together: the Deactivate User pipeline
Here’s the workflow as small steps, with persistence at the boundary:

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

        // Functionally, we should return a new user instance (or make `User` an immutable record and use `with`).
        // Pragmatically, we mutate the existing EF Core entity to simplify persistence.
        user.IsActive = false;
        return Result<User, Error>.Ok(user);
    }
}
```

> **A Note on I/O and Side Effects**
> In Railway-Oriented Programming, reads (`FindUser`) often appear in the pipeline; keep writes outside it (call `_repo.Save` in the `Match` success branch — “functional core, imperative shell”).

> **Functional Purity Note:**
> FP would return a new user; ORMs like EF typically mutate tracked entities. This example mutates for pragmatic persistence.

In a real app, this boundary usually lives in an application service/transaction.

### The Async Reality (Async composition friction)

In modern C#, almost all I/O is asynchronous and returns `Task<T>`.
That means you often end up stacking effects: async (`Task`) and failure (`Result`).

A useful mental model: `Task<T>` composes too. `await` + projection is basically `Map`, and `await` + returning another task is basically `Bind`.[^task-monad]

The annoying case is `Task<Result<...>>`: you want to keep the same straight-line `Bind` flow, but you can’t without a couple helper methods.

Libraries usually call these things `BindAsync`, `MapAsync`, or `SelectManyAsync`. I’m not going to build them here (there are a lot of sharp edges around cancellation/exceptions/hot tasks), but most `Result` libraries already have them.

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

I treat `Result<TSuccess, TError>` as internal plumbing. At the boundary (API controller, UI, etc.), unwrap it (e.g., to `IActionResult`) using `Match`.

Usually avoid returning a raw `Result` object directly to the frontend. It’s a leaky abstraction: it forces your JavaScript client to learn about your internal C# architecture.
Also be careful not to leak internal error codes/messages directly to clients in sensitive domains; map to stable public error shapes and redact details where needed.

If you serialize `Result` directly, you’ll typically get wrapper JSON (often something like `{ "isSuccess": true, "value": ... }`).

In ASP.NET Core, `ProblemDetails` is the standard error shape, so mapping `Result` → `ProblemDetails` is usually a better fit than a custom `{ success: false, error: ... }` wrapper.

```csharp
// Treat Result as internal: unwrap it at the boundary into a standard response.

[HttpPost("users/{id}/deactivate")]
public IActionResult DeactivateUser(string id)
{
    Result<User, Error> result = _userService.DeactivateUser(id);

    // Use Match to map the Result into an HTTP response
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

### Wrap-up

`Result` is just a way to keep “expected failure” in-band, as data. Compose with `Map`/`Bind`, and unwrap once at the edge with `Match`.

If you end up in `Task<Result<...>>` land, grab a library with async combinators rather than hand-rolling them.

**A Note on Libraries:**
For production C#, prefer a mature library (e.g., **FluentResults**, **ErrorOr**, **LanguageExt**) rather than maintaining your own.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, an identifier is often better modeled as a domain type (e.g., `UserId`) rather than a bare number. This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.
[^task-monad]: Technically, `Task<T>` violates some monad laws due to eager evaluation and result caching (e.g., the right identity law can fail if the task has already completed). However, for practical purposes in C#, treating `Task<T>` as monadic is useful for understanding async composition patterns.