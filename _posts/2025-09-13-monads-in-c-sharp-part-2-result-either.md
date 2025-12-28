---
title: "Monads in C# (Part 2): Result (Either)"
date: 2025-09-13
description: "Build a small Result type in C# and use `Map`/`Bind`/`Match` to compose short-circuiting workflows with explicit errors."
---

**Previously in the series**: [List is a monad (part 1)](https://alexyorke.github.io/2025/06/29/list-is-a-monad/)

> _Note_: rewritten 2025-12-21.

In **Part 1** (`List`), we contrasted `Map` (`Select`) vs `Bind` (`SelectMany`) on `List<T>`, then built `Maybe<T>`.

The Result monad lets you sequence computations that can fail. You return `Ok(value)` or `Fail(error)`, then compose with `Bind` to propagate the first failure (later steps don’t run; the failure just flows through).[^shortcircuit]

If you need to accumulate many errors (e.g., form validation), `Result` is not a great fit. You _can_ model “many errors” as `Result<T, List<TError>>`, but you have to define the aggregation rules yourself. If you have more than two meaningful outcomes (not strictly pass/fail), `Result` isn’t really idiomatic — consider a union/tagged type instead.

This post uses Result<TSuccess, TError>. Like Maybe<T>, it models a two-branch flow and composes cleanly with Bind; unlike Maybe, the non-success branch carries an explicit error value. (Maybe models absence; Result models failure with a reason.) Prefer to keep results within Result and compose with `Bind`; handle them at boundaries, or translate between layers (usually by `Match`-ing into a new shape, or mapping errors with a library helper). [^checked-exceptions]

If you're coming from an FP language, this could correspond to a right-biased `Either<TError, TSuccess>` (note the swapped type parameter order): `TError` is the failure branch and `TSuccess` is the success branch, by convention.

### TL;DR
What it looks like (this `Error` record is not built-in to `Result`, it can be whatever type you want for the error):

```csharp
public record Error(string Code, string Message);
IUserRepo repo = /* assume repo is in scope */;

// Creating results:
Result<User, Error> okUser = Result<User, Error>.Ok(user);
Result<User, Error> failed = Result<User, Error>.Fail(new Error("NotFound", "User not found"));

// Assume:
// Result<int, Error> ParseId(string inputIdFromRequest)
// Result<User, Error> DeactivateDecision(User user)

// Returning a Result from a function:
Result<User, Error> FindUserOrFail(IUserRepo repo, int id)
{
    User? user = repo.Find(id);
    return user is null
        ? Result<User, Error>.Fail(new Error("NotFound", $"User {id} not found"))
        : Result<User, Error>.Ok(user);
}

Result<User, Error> result =                   // Result<User, Error>
    ParseId(inputIdFromRequest)                // Result<int, Error>, first in chain, always runs
        .Bind(id => FindUserOrFail(repo, id))  // Result<User, Error>, only runs if ParseId succeeded
        .Bind(DeactivateDecision);             // Result<User, Error>, only runs if FindUser succeeded

// Handle at the boundary (or when translating between layers):
string message = result.Match(
    ok:  _ => "User deactivated",
    err: e => $"Deactivate failed: {e.Code} - {e.Message}");
```

On success, `Bind` passes the inner value to the next step; on failure, it forwards the `Error` and **doesn’t call** later steps, **the Result monad is responsible for not calling the later steps if it failed**. Short-circuiting here is literal: the remaining functions aren’t executed.

> **Aside:** So, yes, this example uses a repository (a .NET thing) and doesn't do IO at the boundary. That’s deliberate: it’s “real enough” to be motivating, without implying you should replace exceptions everywhere with `Result` and sort of become a long FP tutorial. You don't need to throw the baby out with the bathwater if you want to return a Result. Having said that, I don't want to publish misleading information, so feedback is always welcomed.

#### The problem: explicit vs. implicit

In C#, fallible work usually becomes either implicit control flow (exceptions) or explicit branching (guard clauses and status checks).

**Option A: Implicit Control Flow (Exceptions)**
Method signatures might not show failure.[^checked-exceptions] `DeactivateUser` (below) returns `void`, but it can throw while parsing/loading/saving, or due to business rules.

Option A (this one) shows a style where **expected failures are represented as exceptions** (“exceptions as control flow”, could be argued as an anti-pattern), and why that can get noisy.
This snippet is intentionally heavy-handed: it catches `Exception` and wraps at each step to keep the focus on the friction (in real code you’d often rely on boundary handlers or catch narrower exceptions).

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
    if (inputId is null) throw new ArgumentNullException(nameof(inputId));

    int id;
    try
    {
        id = int.Parse(inputId);
    }
    catch (FormatException ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: parse id", ex);
    }
    catch (OverflowException ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: parse id", ex);
    }

    User? user;
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
    try
    {
        _repo.Save(user);
    }
    catch (Exception ex)
    {
        throw new InvalidOperationException("DeactivateUser failed at: save user", ex);
    }
}
```

In small snippets, throw sites are obvious. In larger apps, `exceptions` can originate far from where you want context, so you rely on boundary handlers or add local `try/catch` for context/recovery.

**Main point: in the code above, you’re responsible for `null` checks, catching, initializing the user variable outside try/catch, and stopping the pipeline on failure. It’s easy to repeat, it's noisy, and easy to get wrong.**

**Option B: Explicit Validation (Guard Clauses)**
To reserve `exceptions` for, well, exceptional cases, you write guard clauses and early returns. It’s linear, but noisy.

```csharp
private readonly IUserRepo _repo;

public enum DeactivateUserResult
{
    Success,
    InvalidId,
    NotFound,
    AlreadyInactive,
    InfraError
}

public DeactivateUserResult DeactivateUser(string inputId)
{
    if (!int.TryParse(inputId, out var id)) return DeactivateUserResult.InvalidId;

    User? user;
    try
    {
        user = _repo.Find(id);
    }
    catch (Exception)
    {
        return DeactivateUserResult.InfraError;
    }
    if (user is null) return DeactivateUserResult.NotFound;

    if (!user.IsActive) return DeactivateUserResult.AlreadyInactive;

    // assuming an ORM that requires mutation
    user.IsActive = false;
    try
    {
        _repo.Save(user);
    }
    catch (Exception)
    {
        return DeactivateUserResult.InfraError;
    }
    return DeactivateUserResult.Success;
}
```

> **Note:** `User` is **mutable** here to keep focus on `Result` (and to show you don’t have to throw the baby out with the bathwater to adopt it). Prefer immutability in real domain code.[^immutability]

Enums don’t carry a *success payload* (only a status), so you reach for tuples and conventions (e.g., `(User? user, Error? errorMessage, Success? successMessage)` + “`error is null` means success”).
Conventions are easy to violate: nothing stops you from returning `(user: null, error: true, success: true)` or populating both. You’re back to ad-hoc checks and invalid combinations. Ka-blam-oh.

> **Aside:** You can fix the “invalid combinations” problem with an `OperationStatus` hierarchy (e.g., `OperationSuccess` / `OperationFailure`) or a private constructor + `Success(...)`/`Failure(...)` factories. That helps, but you still need good composition to avoid “check the status after every step.”

`Result` packages these conventions + combinators into a reusable shape: `Ok(...)`/`Fail(...)` plus common composition helpers (`Map`/`Bind`).

#### The solution: the Result monad

`Result` returns failure as data, not an `exception` jump. Expected failures stay on the return path (as long as your steps return `Result` rather than throwing); unexpected `exceptions` still escape.

Now, each step either produces the next value or stops with an `Error`.

LINQ query syntax, for those so inclined (like me). This requires `Select`/`SelectMany`; see the appendix:

```csharp
Result<User, Error> result =
    from id in ParseId(inputId)
    from user in FindUser(id)
    from deactivated in DeactivateDecision(user)
    select deactivated;
```

If method groups read weird, write the lambda: `ParseId(inputId).Bind(id => FindUser(id))`.

### A tiny `Result` implementation

> **Aside:** I'd encourage you to open your IDE and write a `Result` implementation without the use of AI. Think about its public API, then work backwards. Or you can peek at the code below, then write one the next day.

> **Aside 2:** Teaching implementation (don’t ship it; use *LanguageExt* or *CSharpFunctionalExtensions*). It’s intentionally minimalist and **intentionally unsafe around `default`/null** to avoid confusion with other symbols, such as like `?` that have a different meaning in Rust. Additionally, it stores a `default` in the unused slot (don’t read it), and it doesn’t prevent `Ok(null)` / `Fail(null)`. It also does not catch exceptions. I could add those checks, but then it might be unclear what Result is. Real implementations either forbid nulls or make invalid access impossible/throwing, and validate arguments/returns in combinators.

> Aside 3: Where is the “Unit” / “Return” / “Pure” method?
> For the monad `Result<_, TError>`, `Ok(...)` is **Unit/Return/Pure**. `Fail(...)` just constructs the error case.

Here's the implementation for Result:

```csharp
public sealed class Result<TSuccess, TError>
{
    private readonly TSuccess _value;
    private readonly TError _error;

    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;

    private Result(TSuccess value, TError error, bool isSuccess)
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

### Unwrap at the boundary
> **Boundary / application layer:** parse/validate inputs, call repos/services, run workflow/domain decisions, then `Match` into a public output (`DTO`s/status/`ProblemDetails`).
> Don’t ignore returned `Result`s; use an analyzer.[^unused-result]
See the TL;DR snippet above for a minimal `Match` example.

#### Why you shouldn’t serialize `Result`
Avoid serializing `Result` in **public contracts**: it leaks an internal control-flow wrapper into your schema. Prefer `Match` into a DTO / HTTP status / `ProblemDetails` (unless you *intentionally* standardize an envelope or add a custom converter).

Otherwise you can end up with confusing “wrapper JSON” like this (and depending on serializer settings you might even get **only** the flags, silently dropping the payload):

```json
// don't do this
{
  "isSuccess": false,
  "isFailure": true,
  "value": null,
  "error": {
    "code": "DbError",
    "details": {
      "provider": "SqlServer",
      "number": 2601
    }
  }
}
```

Eww. Now your public API exposes `isSuccess/isFailure`, potentially leaks internal error/value shapes, and still doesn’t clearly answer “what HTTP status should this be?”


### Why bother?
Why return `Result` instead of throwing or using enums?
*   **Explicit Signatures:** `Result<User, Error>` says failure is a outcome you must handle.
*   **Fewer sentinel values:** Avoid `-1` / `null` / “magic” return values used as control flow. (You still choose how to model errors.)
*   **Testability:** Assert success/failure and inspect error details without `try/catch` scaffolding.

### Where `Result` fits (and where it doesn’t)
Rule of thumb:

- Use nullable `T?` (or `Maybe<T>`) for expected absence (no reason needed). For reference types, `T?` is a static annotation, not a runtime guarantee.
- Use `Result<TSuccess, TError>` when you want an explicit reason (often typed) and fail-fast composition.

`Result` fits **domain logic** (expected failures you handle). It doesn’t replace `exceptions`.[^always-valid]

1.  **Infrastructure:** Either let infra throw and handle at boundaries, or catch/bridge exceptions into `Result` at repo/client boundaries for uniform composition.
2.  **Bugs:** Throw for programmer errors (null args, impossible states, broken invariants). Use `Result` for expected, user/domain-driven failures.
3.  **Accumulation:** `Bind` is fail-fast. Use validation/combine types to accumulate errors.

### Putting it together
#### Example: deactivate a user
We want to deactivate a user given a user's `id` from an HTTP request (received as a **string**, parsed to an `int`).[^id]

> **Note:** This HTTP API/user service thingy is just an example; `Result` works anywhere you want explicit, composable success/failure (CLI, jobs, message handlers, UI workflows, etc.).

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
        // Workflow composition; persistence happens at the boundary (see `HandleDeactivateRequest`).
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
                // If this throws, assume middleware/global handlers translate + log infra failures.
                _repo.Save(user);
                // This doesn't have to be a string, it could be some new status object that gets serialized
                // Also, this is at the boundary, so, this should go to the outside world as fast as possible
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

Compute `Result<User, Error>` internally, then `Match` at the boundary (`HandleDeactivateRequest`) — or earlier if you’re translating between layers.
If you’re refactoring Option A/B into this shape: you moved `_repo.Save(...)` into the boundary.

This example mutates `user.IsActive` to keep focus on the mechanics; prefer immutability in real domain code.[^immutability]

### Why is _repo.Save(user) inside Match?

Save is I/O. It can fail with expected outcomes (e.g., uniqueness conflicts) and unexpected exceptions (timeouts, outages). Here we model expected failures with Result and let unexpected infrastructure exceptions bubble to boundary handlers (logging/translation). If you want uniform composition, catch and map repo/client exceptions into Result at the boundary.

I should also be using the IO monad, but, I don't want to go down a rabbit hole with this tutorial. I’m using C# to demonstrate how Result fits typical application code—not to turn C# into Haskell.

### Async: the `Task<Result<...>>` nesting weirdness

Async note: once you mix Task and Result, you’ll quickly want async-aware combinators (MapAsync/BindAsync) so you can compose Task<Result<…>> without glue code. Rather than reimplement those helpers here, use a library that provides them.

### Recap

`Result` keeps “expected failure” in-band, as data.

- Chain with `Map`/`Bind`.
- `Match` at boundaries (or when translating layers).
- For async, either `await` between steps or use library-provided async combinators.

### Appendix: LINQ query syntax (`Select`/`SelectMany`)
If you want the simple `from`/`from`/`select` query syntax to compile, add these extension methods (or add the same methods directly to `Result`). (Other query keywords like `where` require additional methods.)

```csharp
public static class ResultLinqExtensions
{
    // Required for `select`
    public static Result<U, TError> Select<TSuccess, U, TError>(
        this Result<TSuccess, TError> result,
        Func<TSuccess, U> selector) =>
        result.Map(selector);

    // Required for multiple `from` clauses
    public static Result<V, TError> SelectMany<TSuccess, U, V, TError>(
        this Result<TSuccess, TError> result,
        Func<TSuccess, Result<U, TError>> bind,
        Func<TSuccess, U, V> project) =>
        result.Bind(val => bind(val).Map(next => project(val, next)));
}
```

**Next in the series**: [Monads in C# (Part 3): The Reader Monad](https://alexyorke.github.io/2025/12/20/monads-in-c-sharp-part-3-the-reader-monad/)

[^id]: In real systems, prefer a strongly typed ID (e.g., `UserId`) over primitives. Here I keep it simple: `string` at the boundary, parse to `int`, focus on `Result`.
[^checked-exceptions]: Java has *checked exceptions* (`throws` forces callers to catch/declare them), but unchecked exceptions still exist. C# has no checked exceptions, so “might throw” usually isn’t in the signature (unless documented).
[^immutability]: Mutation makes pipelines harder to reason about and test. Prefer immutability (`record` + `init`, or return a new value); I mutate here to keep focus on `Result` mechanics.
[^always-valid]: Vladimir Khorikov, [Always valid vs not always valid domain model](https://enterprisecraftsmanship.com/posts/always-valid-vs-not-always-valid-domain-model/).
[^unused-result]: C# lets you ignore return values, so a `Result` can be silently dropped. Use a Roslyn analyzer to flag unused `Result`s.
[^shortcircuit]: “Short-circuit” here: after the first failure, later steps aren’t called; the failure value just propagates.
