---
title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
description: "Build a small Result type in C# and use `Map`/`Bind`/`Match` to compose short-circuiting workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: rewritten 2025-12-21.

In **Part 1**, we contrasted `Map` (`Select`) vs `Bind` (`SelectMany`) and built `Maybe<T>` for optional pipelines.

The `Result` monad sequences computations that could fail. Each step either produces a successful value or short-circuits with an `Error`, until you handle it. Use it when you want failures (and their reasons) to be explicit in the type.

This post applies the same pattern to failures with `Result<TSuccess, TError>`: like `Maybe`, but with an error value; it short-circuits until `Match`, keeping failures explicit and flow linear.[^checked-exceptions]

This post is a lot shorter than part 1, since most of the groundwork was laid in part 1.

### TL;DR
What it looks like (Error record is not part of Result):

```csharp
public record Error(string Code, string Message);

string inputId = inputIdFromRequest;
Result<User, Error> result =          // Result<User, Error>
    ParseId(inputId)                  // Result<int, Error>
        .Bind(FindUser)               // Result<User, Error>
        .Bind(DeactivateDecision);    // Result<User, Error>

// Unwrap once at the boundary:
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");

// Creating results:
Result<User, Error> okUser = Result<User, Error>.Ok(user);
Result<User, Error> failed = Result<User, Error>.Fail(new Error("NotFound", "User not found"));
```

Missing the intermediate `var`s? Here are the types:

- `ParseId : string -> Result<int, Error>`
- `FindUser : int -> Result<User, Error>`
- `DeactivateDecision : User -> Result<User, Error>`
- `Bind : Result<T, Error> -> (T -> Result<U, Error>) -> Result<U, Error>`

`Bind(FindUser)` == `Bind(id => FindUser(id))`: on success, `Bind` passes the inner value to the next step; on failure, it forwards the `Error`.

#### The problem: explicit vs. implicit

In C#, fallible work usually becomes either **implicit control flow** (exceptions) or **explicit checks** (guard clauses).

**Option A: Implicit Control Flow (Exceptions)**
Signatures rarely show failure.[^checked-exceptions] `DeactivateUser` returns `void`, but it can throw while parsing/loading, or later via `null`s and business rules.

```csharp
// The implicit "User" entity used in the examples below
public class User
{
    public int Id { get; set; }
    public bool IsActive { get; set; }
}
```

```csharp
private readonly IUserRepo _repo;

public void DeactivateUser(string inputId)
{
    int id;
    try
    {
        id = int.Parse(inputId);
    }
    catch (Exception ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: parse id", ex);
    }

    User user;
    try
    {
        user = _repo.Find(id);
    }
    catch (Exception ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: load user", ex);
    }

    if (user is null)
        throw new InvalidOperationException("User not found");

    if (!user.IsActive)
        throw new InvalidOperationException("User already inactive");

    user.IsActive = false;
    _repo.Save(user);
}
```

In small snippets, throw sites are obvious. In larger apps, exceptions can come from anywhere, pushing you toward `try/catch` scaffolding.

**The main point here is, you’re responsible for `null` checks, catching, initializing the user variable outside try/catch, and stopping the pipeline on failure—easy to repeat, noisy, boilerplate-y, and easy to get wrong.**

**Option B: Explicit Validation (Guard Clauses)**
To reserve exceptions for exceptional cases, you write guard clauses and early returns. It’s linear, but noisy. Basically defensive coding.

```csharp
private readonly IUserRepo _repo;

public enum DeactivateUserResult
{
    Success,
    InvalidId,
    NotFound,
    AlreadyInactive
}

public DeactivateUserResult DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out var id)) return DeactivateUserResult.InvalidId;

    var user = _repo.Find(id);
    if (user is null) return DeactivateUserResult.NotFound;

    if (!user.IsActive) return DeactivateUserResult.AlreadyInactive;

    user.IsActive = false;
    _repo.Save(user);
    return DeactivateUserResult.Success;
}
```

> **Note:** `User` is **mutable** here to keep focus on `Result`. Prefer immutability in real domain code.[^immutability]

At this point you might reach for `tuples` (e.g., `(bool Success, User? User, string Error)`).

However, tuples lack invariants. You can accidentally create a tuple with `Success = true` AND `Error = "Failed"`. You can also ignore the `Success` boolean and read the `User` property directly, causing `NullReferenceException`s.

`Result` makes invalid combinations unrepresentable.

#### The solution: short-circuiting, as data

Aside: You could model this with `OperationSuccess` / `OperationFailure` classes that inherit from an abstract class `OperationStatus`, but `Result` adds standardized composition (`Map`/`Bind`) and composes with other monads. It's also about control flow.

`Result` returns failure as data, not an exception jump. Errors stay on the return path and short-circuit deterministically.

Think of `Result` as a composable `Try...`.[^out-var] Instead of `bool` + `out`, return `Result<int, Error>` and chain.

Now each step either produces the next value or stops with an `Error`.

LINQ query syntax:

```csharp
Result<User, Error> result =
    from id in ParseId(inputId)
    from user in FindUser(id)
    from deactivated in DeactivateDecision(user)
    select deactivated;
```

If you find `Bind(FindUser)` hard to read, expand the method group into a lambda so you can “see the variable”:
`ParseId(inputId).Bind(id => FindUser(id))`.

### A tiny `Result` implementation
Teaching implementation (don’t ship it; use a library like *LanguageExt*, *CSharpFunctionalExtensions*, or *FluentResults*).
Assumes you don’t call `Ok(null)` / `Fail(null)` and uses `default` for the unused slot.

#### Where is the “Unit” / “Return” / “Pure” method?
In monad terms, **Unit** (also called **Return** or **Pure**) is “take a raw value and wrap it in the container.”

For this `Result`, that’s `Ok(...)`:

```csharp
Result<int, Error> ok = Result<int, Error>.Ok(123);
```

`Fail(...)` is the other constructor, but it’s not “Unit” — it injects an error value instead of a success value.

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
            default,
            true);
    }

    public static Result<TSuccess, TError> Fail(TError error)
    {
        return new Result<TSuccess, TError>(
            default,
            error,
            false);
    }

    public Result<U, TError> Map<U>(Func<TSuccess, U> f)
    {
        if (IsSuccess)
        {
            return Result<U, TError>.Ok(f(_value!));
        }

        return Result<U, TError>.Fail(_error!);
    }

    public Result<U, TError> Bind<U>(Func<TSuccess, Result<U, TError>> f)
    {
        if (IsSuccess)
        {
            return f(_value!);
        }

        return Result<U, TError>.Fail(_error!);
    }

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

#### `Map` vs `Bind`: a quick cheat sheet
Both `Map` and `Bind` run a function **only on success** and propagate failures unchanged.
The only difference is what your function returns:

- Use `Map` for `TSuccess -> U`
- Use `Bind` for `TSuccess -> Result<U, TError>`

Rule: **if the function returns a `Result`, use `Bind`**; otherwise use `Map`.

### Unwrap at the boundary
> **Boundary:** validate inputs, run domain logic, then `Match` into a public output (`DTO`s/status/`ProblemDetails`).
> Don’t ignore returned `Result`s—use an analyzer.[^unused-result]

```csharp
Result<int, string> result = Result<int, string>.Ok(42);

string output = result.Match(
    ok:  value => $"Success: {value}",
    err: error => $"Error: {error}"
);
```

#### Why you shouldn’t serialize `Result`
Don’t serialize `Result`: it leaks internal shape into your public contract. `Match` into `DTO`s/status/`ProblemDetails`.

Many `Result` types expose `Value`/`Error`/`IsSuccess`, so serializers emit the wrapper, e.g.:

```json
{
  "isSuccess": true,
  "isFailure": false,
  "error": null,
  "value": { "id": 123, "isActive": false }
}
```

Yikes. Now your contract includes `isSuccess`/`isFailure` plus internal error/value shapes. Unwrap with `Match` and return a real `DTO`/status/`ProblemDetails`.

### Why bother?
Why return `Result` instead of throwing or using magic values?
*   **Explicit Signatures:** `Result<User, Error>` tells you up front that failure is on the table.
*   **Fewer ad-hoc conventions:** No `-1`, no `null`, no “special string means error.”
*   **Testability:** Tests can assert the outcome *and* the specific error (`Code`, type, message) without exception scaffolding.

### Where `Result` fits (and where it doesn’t)
Rule of thumb: use `T?` for “missing data” (nullability operator); use `Result<TSuccess, TError>` for “this operation can fail with a reason.”

`Result` fits **domain logic** (expected failures you handle). It doesn’t replace exceptions.[^always-valid]

1.  **Infrastructure:** For technical failures (DB/network outages, timeouts, unexpected I/O errors), exceptions handled at the boundary (middleware/logging/global handlers) are often a good fit.
2.  **Bugs:** Violated preconditions are programmer errors—throw (`ArgumentNullException`, `ArgumentException`, etc.) rather than returning a domain `Result`.
3.  **Accumulation:** `Bind` stops at the first `Error`. If you need to collect *all* validation errors, use a validation type that accumulates errors instead of short-circuiting.

> **Note:** `Result` short-circuits on the first `Error`. For “collect all errors” validation, use a type that accumulates (e.g., `List<Error>`).

### Putting it together
#### Example: deactivate a user
We want to deactivate a user given an `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

We'll use the same `Error` payload from earlier (this is **not** part of `Result` itself).

```csharp
public class User
{
    public int Id { get; set; }
    public bool IsActive { get; set; }
}

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

        user.IsActive = false;
        return Result<User, Error>.Ok(user);
    }
}
```

Compute `Result<User, Error>` internally, then `Match` once at the boundary (`HandleDeactivateRequest`).
This example mutates `user.IsActive` to keep focus on the mechanics; prefer immutability in real domain code.[^immutability]

#### Why is `_repo.Save(user)` inside `Match`?
`Save` is I/O and often fails via exceptions (DB/network outages, timeouts). Here we keep those **infrastructure failures** as exceptions handled at the boundary, and use `Result` for **expected domain failures** (invalid ID, not found, already inactive).
### Async: the `Task<Result<...>>` nesting weirdness

Async often gives you `Task<Result<T, Error>>`. Without helpers you `await` then branch. For fluent pipelines, use a library with `Map`/`Bind` over `Task<Result<...>>`, e.g.:

- **[CSharpFunctionalExtensions](https://github.com/vkhorikov/CSharpFunctionalExtensions)**
- **[LanguageExt](https://github.com/louthy/language-ext)**

```csharp
public Task<Result<User, Error>> DeactivateUserAsync(string inputId) =>
    ParseIdAsync(inputId)
        .Bind(FindUserAsync)
        .Bind(user => Task.FromResult(DeactivateDecision(user)));
```

### Recap

`Result` keeps “expected failure” in-band, as data.

1.  **Chain** with `Map`/`Bind` (the universal monad pattern).
2.  **Handle** `Task<Result<...>>` using async extensions to fuse the effects.
3.  **Decide** once at the edge with `Match`.

Toolbox recap: `List` (many), `Maybe` (optional), `Result` (failure). Same core shape: `Bind`/`SelectMany`.

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, use a Strongly Typed ID (e.g., `UserId`) rather than a bare number to avoid "Primitive Obsession." This post uses `string` at the boundary and parses to `int` to keep the example focused on `Result` composition.
[^checked-exceptions]: Java has *checked exceptions*: methods can declare them with a `throws` clause and callers must catch/declare them. C# has no checked exceptions, so “what might throw” usually isn’t visible in the method signature unless it’s documented (e.g., XML `<exception>` docs).
[^immutability]: Mutating domain objects makes pipelines harder to reason about and test. Prefer immutable `record`s (and returning a new value) where you can; this post sticks to mutation to keep the focus on `Result` composition.
[^out-var]: C# supports inline `out` variable declarations (C# 7): e.g., `if (int.TryParse(input, out var id)) { ... }`. This makes a single `Try...` step fairly composable inside an `if`, but it doesn’t scale to multi-step pipelines the way `Result` + `Bind` does.
[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).
[^unused-result]: C# lets you ignore return values, so a `Result` can be dropped. Use a Roslyn analyzer to flag unused `Result`s.
